from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.user import Role, User
from app.modules.cdn.health import CdnHealthMonitor
from app.modules.cdn.models import (
    CDNEndpoint,
    CDNHealthStatus,
    CDNOrigin,
    CDNOriginType,
    CDNProviderType,
    CDNRoutingEvent,
)
from app.modules.cdn.providers.alibaba_dcdn import AlibabaDcdnProvider
from app.modules.cdn.repository import CDNRepository
from app.modules.cdn.routing import CdnRoutingService
from app.modules.cdn.signing import CdnUrlSigner
from app.utils.jwt import create_access_token


@pytest.fixture
def cdn_db() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def cdn_client(cdn_db: Session) -> TestClient:
    def override_get_db():
        try:
            yield cdn_db
        finally:
            cdn_db.rollback()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def create_user(db: Session, role_name: str) -> User:
    role = db.query(Role).filter_by(name=role_name).one_or_none()
    if role is None:
        role = Role(name=role_name, description=role_name)
        db.add(role)
        db.flush()
    user = User(email=f"{role_name}@gntv.test", hashed_password="hash", is_active=True, is_verified=True)
    user.name = role_name
    user.roles.append(role)
    db.add(user)
    db.commit()
    return user


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


def origin(name: str) -> CDNOrigin:
    return CDNOrigin(name=name, origin_hostname=f"{name}.origin.gntv.test", origin_type=CDNOriginType.PRIMARY)


def endpoint(
    name: str,
    priority: int,
    origin_id=None,
    health: CDNHealthStatus = CDNHealthStatus.HEALTHY,
    enabled: bool = True,
    failures: int = 0,
    last_health_check_at: datetime | None = None,
) -> CDNEndpoint:
    return CDNEndpoint(
        origin_id=origin_id,
        provider_type=CDNProviderType.ALIBABA_DCDN,
        edge_hostname=f"{name}.edge.gntv.test",
        cache_policy_json={"manifests": "private,no-store", "segments": "public,max-age=31536000", "beacons": "no-store"},
        priority=priority,
        health_status=health,
        is_enabled=enabled,
        consecutive_failures=failures,
        last_health_check_at=last_health_check_at,
    )


def seed_endpoints(db: Session) -> tuple[CDNEndpoint, CDNEndpoint]:
    primary_origin = origin("primary")
    secondary_origin = origin("secondary")
    db.add_all([primary_origin, secondary_origin])
    db.flush()
    primary = endpoint("primary", 10, primary_origin.id)
    secondary = endpoint("secondary", 20, secondary_origin.id)
    db.add_all([primary, secondary])
    db.commit()
    return primary, secondary


def test_cdn_routing_selection_primary_success(cdn_db: Session) -> None:
    primary, _secondary = seed_endpoints(cdn_db)
    result = CdnRoutingService(CDNRepository(cdn_db)).route_asset(asset_id="live-1", asset_path="/live/live-1/index.m3u8")
    assert result.endpoint_id == primary.id
    assert result.provider_type == CDNProviderType.ALIBABA_DCDN
    assert result.routing_reason == "PRIMARY_HEALTHY"
    assert cdn_db.query(CDNRoutingEvent).count() == 1


def test_primary_failure_routes_to_secondary(cdn_db: Session) -> None:
    primary, secondary = seed_endpoints(cdn_db)
    primary.health_status = CDNHealthStatus.UNHEALTHY
    cdn_db.commit()
    result = CdnRoutingService(CDNRepository(cdn_db)).route_asset(asset_id="live-2", asset_path="/live/live-2/index.m3u8")
    assert result.endpoint_id == secondary.id
    assert result.routing_reason == "FAILOVER_SECONDARY_HEALTHY"


def test_unhealthy_and_disabled_endpoints_excluded(cdn_db: Session) -> None:
    o1, o2, o3 = origin("disabled"), origin("unhealthy"), origin("good")
    cdn_db.add_all([o1, o2, o3])
    cdn_db.flush()
    disabled = endpoint("disabled", 1, o1.id, enabled=False)
    unhealthy = endpoint("unhealthy", 2, o2.id, health=CDNHealthStatus.UNHEALTHY)
    good = endpoint("good", 3, o3.id)
    cdn_db.add_all([disabled, unhealthy, good])
    cdn_db.commit()
    result = CdnRoutingService(CDNRepository(cdn_db)).route_asset(asset_id="a", asset_path="/live/a.m3u8")
    assert result.endpoint_id == good.id


def test_routing_priority_and_latency_are_deterministic() -> None:
    slow = endpoint("slow", 10)
    fast = endpoint("fast", 11)
    selected = sorted([fast, slow], key=lambda item: (item.priority, item.created_at))[0]
    assert selected.edge_hostname.startswith("slow.")


def test_edge_url_signing_expiry_and_tampering() -> None:
    signer = CdnUrlSigner(secret="secret")
    signed, _expires = signer.sign_url("edge.gntv.test", "/live/a/index.m3u8?quality=hd", ttl_seconds=60)
    expired = AlibabaDcdnProvider().generate_signed_url(
        "edge.gntv.test",
        "/live/a/index.m3u8",
        "secret",
        datetime.now(UTC) - timedelta(seconds=1),
    )
    assert signer.validate_url(signed)
    assert not signer.validate_url(expired)
    assert not signer.validate_url(signed.replace("/live/a/", "/live/b/"))
    assert not signer.validate_url(signed.replace("auth_key=", "auth_key=broken"))


def test_failover_hysteresis_cooldown(cdn_db: Session) -> None:
    primary, secondary = seed_endpoints(cdn_db)
    monitor = CdnHealthMonitor(CDNRepository(cdn_db), failover_threshold=1, cooldown_seconds=60)
    status, changed = monitor.process_probe_result(primary, CDNHealthStatus.UNHEALTHY, 3000, "timeout")
    result = CdnRoutingService(CDNRepository(cdn_db)).route_asset(asset_id="live-3", asset_path="/live/live-3/index.m3u8")
    assert status == CDNHealthStatus.UNHEALTHY
    assert changed is True
    assert result.endpoint_id == secondary.id


def test_alibaba_provider_abstraction_mockable() -> None:
    provider = AlibabaDcdnProvider()
    assert provider.generate_signed_url("edge.gntv.test", "/live/a.m3u8", "secret", datetime.now(UTC) + timedelta(seconds=60))
    assert provider.probe_health("slow.edge.gntv.test")[0] == CDNHealthStatus.DEGRADED


def test_ssai_url_query_preservation(cdn_db: Session) -> None:
    seed_endpoints(cdn_db)
    result = CdnRoutingService(CDNRepository(cdn_db)).route_asset(
        asset_id="gntv-fast",
        asset_path="/api/v1/monetization/manifest/gntv-fast/ssai.m3u8?ad_break=midroll&session=s1",
        playback_type="fast",
    )
    parsed = urlsplit(result.routed_url)
    params = parse_qs(parsed.query)
    assert parsed.path.endswith("/api/v1/monetization/manifest/gntv-fast/ssai.m3u8")
    assert params["ad_break"] == ["midroll"]
    assert params["session"] == ["s1"]
    assert "auth_key" in params


def test_health_state_transitions(cdn_db: Session) -> None:
    primary, _secondary = seed_endpoints(cdn_db)
    monitor = CdnHealthMonitor(CDNRepository(cdn_db), failover_threshold=2)
    degraded, _ = monitor.process_probe_result(primary, CDNHealthStatus.DEGRADED, 800, "slow")
    healthy, _ = monitor.process_probe_result(primary, CDNHealthStatus.HEALTHY, 90)
    assert degraded == CDNHealthStatus.DEGRADED
    assert healthy == CDNHealthStatus.HEALTHY


def test_api_authorization_and_secret_leakage(cdn_client: TestClient, cdn_db: Session) -> None:
    seed_endpoints(cdn_db)
    viewer = create_user(cdn_db, "viewer")
    admin = create_user(cdn_db, "admin")
    unauth = cdn_client.get("/api/v1/cdn/endpoints")
    forbidden = cdn_client.get("/api/v1/cdn/endpoints", headers=auth_headers(viewer))
    allowed = cdn_client.get("/api/v1/cdn/endpoints", headers=auth_headers(admin))
    assert unauth.status_code in (401, 403)
    assert forbidden.status_code == 403
    assert allowed.status_code == 200
    assert "secret" not in allowed.text.lower()
    assert "signing_key" not in allowed.text


def test_api_route_and_admin_health_update(cdn_client: TestClient, cdn_db: Session) -> None:
    primary, _secondary = seed_endpoints(cdn_db)
    admin = create_user(cdn_db, "admin")
    route = cdn_client.get("/api/v1/cdn/route/asset-1?playback_type=fast&asset_path=/fast/asset-1/index.m3u8")
    health = cdn_client.post(
        f"/api/v1/cdn/endpoints/{primary.id}/health",
        json={"status": "DEGRADED", "response_latency_ms": 321, "failure_reason": "slow"},
        headers=auth_headers(admin),
    )
    assert route.status_code == 200
    assert route.json()["cache_control"]
    assert health.status_code == 200
    assert health.json()["health_status"] == "DEGRADED"


def test_sprint73_migration_upgrade_and_downgrade_on_isolated_database() -> None:
    migration_path = Path(__file__).parents[1] / "alembic/versions/202608161200_module7_sprint73_global_cdn.py"
    spec = importlib.util.spec_from_file_location("sprint73_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    connection = engine.connect()
    context = MigrationContext.configure(connection)
    original_op = module.op
    module.op = Operations(context)
    try:
        module.upgrade()
        tables = set(inspect(connection).get_table_names())
        assert {"cdn_origins", "cdn_endpoints", "cdn_health_checks", "cdn_routing_events"} <= tables
        connection.execute(text("SELECT COUNT(*) FROM cdn_endpoints"))
        module.downgrade()
        remaining = set(inspect(connection).get_table_names())
        assert "cdn_endpoints" not in remaining
    finally:
        module.op = original_op
        connection.close()
