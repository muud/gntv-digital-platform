from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
from uuid import uuid4

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.user import Role, User
from app.modules.cdn.analytics import CDNObservabilityService
from app.modules.cdn.models import (
    CDNEndpoint,
    CDNEndpointMetric,
    CDNFailoverEvent,
    CDNHealthStatus,
    CDNMetricGranularity,
    CDNOrigin,
    CDNOriginType,
    CDNProviderMetric,
    CDNProviderType,
)
from app.modules.cdn.repository import CDNRepository
from app.modules.cdn.schemas import (
    CDNEndpointMetricCreate,
    CDNFailoverEventCreate,
    CDNTrafficAllocationOverrideCreate,
)
from app.utils.jwt import create_access_token


def make_db() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine)
    return testing_session()


def make_client(db: Session) -> TestClient:
    def override_get_db():
        try:
            yield db
        finally:
            db.rollback()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def create_user(db: Session, role_name: str) -> User:
    role = db.query(Role).filter_by(name=role_name).one_or_none()
    if role is None:
        role = Role(name=role_name, description=role_name)
        db.add(role)
        db.flush()
    user = User(
        email=f"{role_name}-{uuid4()}@gntv.test",
        hashed_password="hash",
        is_active=True,
        is_verified=True,
    )
    user.name = role_name
    user.roles.append(role)
    db.add(user)
    db.commit()
    return user


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


def seed_endpoint(
    db: Session,
    name: str,
    provider: CDNProviderType,
    priority: int,
    health: CDNHealthStatus = CDNHealthStatus.HEALTHY,
) -> CDNEndpoint:
    origin = CDNOrigin(
        name=f"{name}-origin",
        origin_hostname=f"{name}.origin.gntv.test",
        origin_type=CDNOriginType.PRIMARY,
        is_active=True,
    )
    db.add(origin)
    db.flush()
    endpoint = CDNEndpoint(
        origin_id=origin.id,
        provider_type=provider,
        edge_hostname=f"{name}.edge.gntv.test",
        priority=priority,
        is_enabled=True,
        health_status=health,
        consecutive_failures=0 if health == CDNHealthStatus.HEALTHY else 3,
    )
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)
    return endpoint


def metric_payload(
    endpoint: CDNEndpoint,
    region: str,
    requests: int,
    latency: float,
    errors: int = 0,
    misses: int = 10,
    health: CDNHealthStatus = CDNHealthStatus.HEALTHY,
) -> CDNEndpointMetricCreate:
    now = datetime.now(UTC)
    return CDNEndpointMetricCreate(
        endpoint_id=endpoint.id,
        region_code=region,
        granularity=CDNMetricGranularity.RAW,
        window_start=now - timedelta(minutes=5),
        window_end=now,
        request_count=requests,
        bandwidth_bytes=requests * 1024,
        cache_hit_count=max(requests - misses, 0),
        cache_miss_count=misses,
        origin_fetch_count=misses,
        avg_latency_ms=latency,
        p95_latency_ms=latency * 1.5,
        http_4xx_count=errors,
        http_5xx_count=0,
        health_status=health,
    )


def test_sprint74_analytics_persistence_and_aggregation() -> None:
    db = make_db()
    try:
        endpoint = seed_endpoint(db, "alibaba-nairobi", CDNProviderType.ALIBABA_DCDN, 10)
        service = CDNObservabilityService(CDNRepository(db))
        response = service.ingest_endpoint_metric(metric_payload(endpoint, "EA", 1000, 80, errors=10, misses=100))
        overview = service.overview(region_code="EA")
        providers = service.provider_analytics(region_code="EA")
        assert response.provider_type == CDNProviderType.ALIBABA_DCDN
        assert db.query(CDNEndpointMetric).count() == 1
        assert db.query(CDNProviderMetric).count() == 1
        assert overview.metrics.request_count == 1000
        assert overview.metrics.cache_hit_ratio == 0.9
        assert overview.metrics.origin_offload_ratio == 0.9
        assert overview.metrics.http_error_rate == 0.01
        assert providers[0].metrics.bandwidth_bytes == 1024000
    finally:
        db.close()


def test_sprint74_scoring_excludes_unhealthy_provider_from_recommendations() -> None:
    db = make_db()
    try:
        healthy = seed_endpoint(db, "fastly-healthy", CDNProviderType.FASTLY, 10)
        unhealthy = seed_endpoint(db, "cloudfront-unhealthy", CDNProviderType.CLOUDFRONT, 1, CDNHealthStatus.UNHEALTHY)
        service = CDNObservabilityService(CDNRepository(db))
        service.ingest_endpoint_metric(metric_payload(healthy, "EA", 900, 60, misses=45))
        service.ingest_endpoint_metric(
            metric_payload(unhealthy, "EA", 1200, 30, misses=20, health=CDNHealthStatus.UNHEALTHY)
        )
        endpoint_scores = {item.endpoint_id: item.score for item in service.endpoint_analytics(region_code="EA")}
        recommendations = service.traffic_allocation_recommendations(region_code="EA").recommendations
        assert endpoint_scores[unhealthy.id] == 0.0
        assert [item.endpoint_id for item in recommendations] == [healthy.id]
        assert recommendations[0].allocation_percent == 100.0
    finally:
        db.close()


def test_sprint74_failover_history_and_regional_metrics() -> None:
    db = make_db()
    try:
        primary = seed_endpoint(db, "primary-ea", CDNProviderType.ALIBABA_DCDN, 10)
        secondary = seed_endpoint(db, "secondary-wa", CDNProviderType.FASTLY, 20)
        service = CDNObservabilityService(CDNRepository(db))
        service.ingest_endpoint_metric(metric_payload(primary, "EA", 500, 70, misses=30))
        service.ingest_endpoint_metric(metric_payload(secondary, "WA", 250, 95, misses=50))
        service.record_failover_event(
            CDNFailoverEventCreate(
                from_endpoint_id=primary.id,
                to_endpoint_id=secondary.id,
                provider_type=CDNProviderType.FASTLY,
                region_code="EA",
                asset_id="live-news",
                reason="primary_latency_threshold",
                decision_metadata_json={"latency_ms": 2500},
            )
        )
        regions = {item.region_code: item.metrics.request_count for item in service.region_analytics()}
        history = service.failover_history()
        assert regions == {"EA": 500, "WA": 250}
        assert db.query(CDNFailoverEvent).count() == 1
        assert history[0].reason == "primary_latency_threshold"
    finally:
        db.close()


def test_sprint74_operator_override_controls_allocation() -> None:
    db = make_db()
    try:
        endpoint_a = seed_endpoint(db, "edge-a", CDNProviderType.ALIBABA_DCDN, 10)
        endpoint_b = seed_endpoint(db, "edge-b", CDNProviderType.FASTLY, 20)
        operator = create_user(db, "operator")
        service = CDNObservabilityService(CDNRepository(db))
        service.ingest_endpoint_metric(metric_payload(endpoint_a, "EA", 1000, 50, misses=50))
        service.ingest_endpoint_metric(metric_payload(endpoint_b, "EA", 1000, 80, misses=50))
        override = service.create_operator_override(
            CDNTrafficAllocationOverrideCreate(
                endpoint_id=endpoint_b.id,
                region_code="EA",
                allocation_percent=70.0,
                reason="operator_capacity_test",
            ),
            created_by_user_id=operator.id,
        )
        recommendations = service.traffic_allocation_recommendations(region_code="EA").recommendations
        by_endpoint = {item.endpoint_id: item for item in recommendations}
        assert override.created_by_user_id == operator.id
        assert by_endpoint[endpoint_b.id].operator_override is True
        assert by_endpoint[endpoint_b.id].allocation_percent == 70.0
        assert by_endpoint[endpoint_a.id].allocation_percent == 30.0
    finally:
        db.close()


def test_sprint74_monitoring_api_authorization_and_contracts() -> None:
    db = make_db()
    client = make_client(db)
    try:
        endpoint = seed_endpoint(db, "api-edge", CDNProviderType.ALIBABA_DCDN, 10)
        viewer = create_user(db, "viewer")
        operator = create_user(db, "operator")
        payload = metric_payload(endpoint, "EA", 300, 75).model_dump(mode="json")
        forbidden = client.get("/api/v1/cdn/observability/overview", headers=auth_headers(viewer))
        created = client.post("/api/v1/cdn/observability/metrics", json=payload, headers=auth_headers(operator))
        overview = client.get("/api/v1/cdn/observability/overview?region_code=EA", headers=auth_headers(operator))
        endpoints = client.get("/api/v1/cdn/observability/endpoints?region_code=EA", headers=auth_headers(operator))
        providers = client.get("/api/v1/cdn/observability/providers?region_code=EA", headers=auth_headers(operator))
        regions = client.get("/api/v1/cdn/observability/regions", headers=auth_headers(operator))
        allocation = client.get(
            "/api/v1/cdn/observability/traffic-allocation?region_code=EA",
            headers=auth_headers(operator),
        )
        metrics = client.get("/api/v1/cdn/metrics", headers=auth_headers(operator))
        assert forbidden.status_code == 403
        assert created.status_code == 201
        assert overview.json()["metrics"]["request_count"] == 300
        assert endpoints.json()[0]["edge_hostname"] == "api-edge.edge.gntv.test"
        assert providers.status_code == 200
        assert regions.status_code == 200
        assert allocation.json()["recommendations"][0]["allocation_percent"] == 100.0
        assert metrics.json()["cdn_endpoint_health"]["healthy"] == 1
        assert "signing_key" not in overview.text
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint74_routing_and_failover_api_history() -> None:
    db = make_db()
    client = make_client(db)
    try:
        primary = seed_endpoint(db, "history-a", CDNProviderType.ALIBABA_DCDN, 10)
        secondary = seed_endpoint(db, "history-b", CDNProviderType.FASTLY, 20)
        operator = create_user(db, "operator")
        repo = CDNRepository(db)
        repo.log_routing_event(
            asset_id="asset-history",
            endpoint_id=primary.id,
            routing_reason="PRIMARY_HEALTHY",
            decision_metadata_json={"score": 92},
        )
        failover = client.post(
            "/api/v1/cdn/observability/failover-history",
            json={
                "from_endpoint_id": str(primary.id),
                "to_endpoint_id": str(secondary.id),
                "provider_type": "fastly",
                "region_code": "EA",
                "asset_id": "asset-history",
                "reason": "manual_drill",
            },
            headers=auth_headers(operator),
        )
        routing_history = client.get("/api/v1/cdn/observability/routing-events", headers=auth_headers(operator))
        failover_history = client.get("/api/v1/cdn/observability/failover-history", headers=auth_headers(operator))
        assert failover.status_code == 201
        assert routing_history.json()[0]["asset_id"] == "asset-history"
        assert failover_history.json()[0]["reason"] == "manual_drill"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_sprint74_migration_upgrade_and_downgrade_on_isolated_database() -> None:
    migration_path = Path(__file__).parents[1] / "alembic/versions/202608191200_module7_sprint74_cdn_observability.py"
    spec = importlib.util.spec_from_file_location("sprint74_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    connection = engine.connect()
    connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
    connection.execute(text("CREATE TABLE cdn_endpoints (id CHAR(32) PRIMARY KEY)"))
    context = MigrationContext.configure(connection)
    original_op = module.op
    module.op = Operations(context)
    try:
        module.upgrade()
        tables = set(inspect(connection).get_table_names())
        assert {
            "cdn_endpoint_metrics",
            "cdn_provider_metrics",
            "cdn_failover_events",
            "cdn_traffic_allocation_overrides",
        } <= tables
        connection.execute(text("SELECT COUNT(*) FROM cdn_endpoint_metrics"))
        module.downgrade()
        remaining = set(inspect(connection).get_table_names())
        assert "cdn_endpoint_metrics" not in remaining
        assert "cdn_provider_metrics" not in remaining
    finally:
        module.op = original_op
        connection.close()
