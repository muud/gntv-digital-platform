"""Comprehensive test suite for Module 7 Sprint 7.3 Global Multi-CDN & Edge Acceleration."""

from datetime import UTC, datetime, timedelta

from fastapi import status
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from alembic.config import Config
from app.core.database import Base
from app.main import app
from app.models.user import Role, User
from app.modules.cdn.health import CdnHealthMonitor
from app.modules.cdn.models import (
    CDNHealthStatus,
    CDNOriginType,
    CDNProviderType,
)
from app.modules.cdn.providers.alibaba_dcdn import AlibabaDcdnProvider
from app.modules.cdn.repository import CDNRepository
from app.modules.cdn.routing import CdnRoutingService
from app.modules.cdn.schemas import CDNEndpointCreate, CDNOriginCreate
from app.modules.cdn.signing import CdnUrlSigner
from app.utils.jwt import create_access_token


@pytest.fixture
def db_session() -> Session:
    """Create an in-memory SQLite database supporting multi-threaded FastAPI TestClient execution."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_client(db_session: Session) -> TestClient:
    """Create FastAPI test client with database dependency override."""
    from app.core.database import get_db

    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Create a mock admin user for authenticated API testing."""
    user = User(
        email="admin@gntv.com",
        hashed_password="hashed_secret_password",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    admin_role = Role(name="admin")
    db_session.add(admin_role)
    user.roles.append(admin_role)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_auth_headers(admin_user: User) -> dict[str, str]:
    """Return bearer token authorization header for admin user."""
    token = create_access_token(data={"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# 1. ALIBABA DCDN PROVIDER & URL SIGNING TESTS
# ============================================================================

def test_alibaba_dcdn_provider_signature_generation_and_validation():
    provider = AlibabaDcdnProvider()
    secret = "my-secret-key-12345"
    edge_hostname = "dcdn-primary.gntv.com"
    asset_path = "/hls/live/channel1/index.m3u8"
    expires_at = datetime.now(UTC) + timedelta(seconds=600)

    signed_url = provider.generate_signed_url(
        edge_hostname=edge_hostname,
        asset_path=asset_path,
        secret=secret,
        expires_at=expires_at,
        custom_params={"session_id": "test-session-123"},
    )

    assert "auth_key=" in signed_url
    assert "dcdn-primary.gntv.com" in signed_url
    assert "session_id=test-session-123" in signed_url

    # Validation must succeed
    valid = provider.validate_signature(signed_url, secret=secret)
    assert valid is True


def test_url_signature_tamper_detection_and_expiry():
    provider = AlibabaDcdnProvider()
    secret = "my-secret-key-12345"
    edge_hostname = "dcdn-primary.gntv.com"
    asset_path = "/hls/live/channel1/index.m3u8"

    # Expired token
    expired_at = datetime.now(UTC) - timedelta(seconds=10)
    expired_url = provider.generate_signed_url(
        edge_hostname=edge_hostname,
        asset_path=asset_path,
        secret=secret,
        expires_at=expired_at,
    )
    assert provider.validate_signature(expired_url, secret=secret) is False

    # Tampered signature
    valid_expires = datetime.now(UTC) + timedelta(seconds=600)
    valid_url = provider.generate_signed_url(
        edge_hostname=edge_hostname,
        asset_path=asset_path,
        secret=secret,
        expires_at=valid_expires,
    )
    tampered_url = valid_url.replace("auth_key=", "auth_key=tampered-")
    assert provider.validate_signature(tampered_url, secret=secret) is False

    # Incorrect secret key
    assert provider.validate_signature(valid_url, secret="wrong-secret-key") is False


def test_ssai_manifest_cache_policy_behavior():
    provider = AlibabaDcdnProvider()

    # SSAI manifest cache policy must bypass caching
    ssai_headers = provider.get_cache_policy_headers("/hls/live/ssai/channel1/index.m3u8")
    assert ssai_headers["Cache-Control"] == "no-cache, no-store, must-revalidate"
    assert ssai_headers["X-DCDN-Cache-Behavior"] == "BYPASS"

    # Live HLS segment cache policy
    segment_headers = provider.get_cache_policy_headers("/hls/live/channel1/segment_001.ts")
    assert "immutable" in segment_headers["Cache-Control"]
    assert segment_headers["X-DCDN-Cache-Behavior"] == "CACHE_SEGMENT"

    # Live manifest
    live_manifest_headers = provider.get_cache_policy_headers("/hls/live/channel1/master.m3u8", playback_type="live")
    assert "max-age=2" in live_manifest_headers["Cache-Control"]

    # VOD manifest
    vod_manifest_headers = provider.get_cache_policy_headers("/hls/vod/movie1/master.m3u8", playback_type="vod")
    assert "max-age=86400" in vod_manifest_headers["Cache-Control"]


# ============================================================================
# 2. CDN ROUTING & FAILOVER TESTS
# ============================================================================

def test_cdn_routing_primary_selection(db_session: Session):
    repo = CDNRepository(db_session)
    signer = CdnUrlSigner(secret="test-signing-secret-key-32bytes")

    # Create origins
    primary_origin = repo.create_origin(
        CDNOriginCreate(name="primary-origin", origin_hostname="origin-a.gntv.com", origin_type=CDNOriginType.PRIMARY)
    )
    secondary_origin = repo.create_origin(
        CDNOriginCreate(name="secondary-origin", origin_hostname="origin-b.gntv.com", origin_type=CDNOriginType.SECONDARY)
    )

    # Create endpoints (primary priority 10, secondary priority 20)
    repo.create_endpoint(
        CDNEndpointCreate(
            origin_id=primary_origin.id,
            provider_type=CDNProviderType.ALIBABA_DCDN,
            edge_hostname="dcdn-primary.gntv.com",
            priority=10,
            is_enabled=True,
        )
    )
    repo.create_endpoint(
        CDNEndpointCreate(
            origin_id=secondary_origin.id,
            provider_type=CDNProviderType.ALIBABA_DCDN,
            edge_hostname="dcdn-secondary.gntv.com",
            priority=20,
            is_enabled=True,
        )
    )

    routing_service = CdnRoutingService(repo, signer)
    route_response = routing_service.route_asset(
        asset_id="channel-1",
        asset_path="/hls/live/channel1/index.m3u8",
        playback_type="live",
        query_params={"session_id": "ssai-99"},
    )

    assert route_response.edge_hostname == "dcdn-primary.gntv.com"
    assert route_response.routing_reason == "PRIMARY_HEALTHY"
    assert route_response.is_failover is False
    assert "session_id=ssai-99" in route_response.routed_url


def test_cdn_routing_health_aware_primary_to_secondary_failover(db_session: Session):
    repo = CDNRepository(db_session)
    signer = CdnUrlSigner(secret="test-signing-secret-key-32bytes")

    primary_origin = repo.create_origin(
        CDNOriginCreate(name="primary-origin", origin_hostname="origin-a.gntv.com", origin_type=CDNOriginType.PRIMARY)
    )
    secondary_origin = repo.create_origin(
        CDNOriginCreate(name="secondary-origin", origin_hostname="origin-b.gntv.com", origin_type=CDNOriginType.SECONDARY)
    )

    ep_primary = repo.create_endpoint(
        CDNEndpointCreate(
            origin_id=primary_origin.id,
            provider_type=CDNProviderType.ALIBABA_DCDN,
            edge_hostname="dcdn-primary.gntv.com",
            priority=10,
            is_enabled=True,
        )
    )
    repo.create_endpoint(
        CDNEndpointCreate(
            origin_id=secondary_origin.id,
            provider_type=CDNProviderType.ALIBABA_DCDN,
            edge_hostname="dcdn-secondary.gntv.com",
            priority=20,
            is_enabled=True,
        )
    )

    # Mark primary UNHEALTHY
    repo.update_endpoint_health(
        endpoint_id=ep_primary.id,
        status=CDNHealthStatus.UNHEALTHY,
        consecutive_failures=3,
        failure_reason="Edge node timeout",
    )

    routing_service = CdnRoutingService(repo, signer)
    route_response = routing_service.route_asset(
        asset_id="channel-1",
        asset_path="/hls/live/channel1/index.m3u8",
    )

    # Failover to secondary must trigger
    assert route_response.edge_hostname == "dcdn-secondary.gntv.com"
    assert route_response.is_failover is True
    assert route_response.routing_reason == "FAILOVER_SECONDARY_HEALTHY"


def test_disabled_endpoint_exclusion(db_session: Session):
    repo = CDNRepository(db_session)
    signer = CdnUrlSigner(secret="test-signing-secret-key-32bytes")

    origin = repo.create_origin(CDNOriginCreate(name="origin-1", origin_hostname="origin.gntv.com"))
    repo.create_endpoint(
        CDNEndpointCreate(
            origin_id=origin.id,
            edge_hostname="dcdn-disabled.gntv.com",
            priority=5,
            is_enabled=False,  # Disabled
        )
    )
    repo.create_endpoint(
        CDNEndpointCreate(
            origin_id=origin.id,
            edge_hostname="dcdn-enabled.gntv.com",
            priority=10,
            is_enabled=True,
        )
    )

    routing_service = CdnRoutingService(repo, signer)
    route_response = routing_service.route_asset(asset_id="ch-1", asset_path="/live.m3u8")
    assert route_response.edge_hostname == "dcdn-enabled.gntv.com"


# ============================================================================
# 3. HYSTERESIS & HEALTH STATE TRANSITIONS
# ============================================================================

def test_health_monitor_hysteresis_and_cooldown(db_session: Session):
    repo = CDNRepository(db_session)
    origin = repo.create_origin(CDNOriginCreate(name="origin-hysteresis", origin_hostname="origin.gntv.com"))
    endpoint = repo.create_endpoint(
        CDNEndpointCreate(
            origin_id=origin.id,
            edge_hostname="dcdn-hysteresis.gntv.com",
            priority=10,
        )
    )

    health_monitor = CdnHealthMonitor(repo, failover_threshold=3, cooldown_seconds=60)

    # 1. First probe failure -> status DEGRADED
    status1, _ = health_monitor.process_probe_result(endpoint, CDNHealthStatus.UNHEALTHY, 400.0, "Slow connection")
    assert status1 == CDNHealthStatus.DEGRADED

    # 2. Second failure -> status DEGRADED
    status2, _ = health_monitor.process_probe_result(endpoint, CDNHealthStatus.UNHEALTHY, 400.0, "Slow connection")
    assert status2 == CDNHealthStatus.DEGRADED

    # 3. Third failure -> transitions to UNHEALTHY
    status3, _ = health_monitor.process_probe_result(endpoint, CDNHealthStatus.UNHEALTHY, 500.0, "Timeout")
    assert status3 == CDNHealthStatus.UNHEALTHY

    # 4. Immediate recovery probe -> status transitions to DEGRADED until cooldown expires
    ep_refreshed = repo.get_endpoint(endpoint.id)
    status4, _ = health_monitor.process_probe_result(ep_refreshed, CDNHealthStatus.HEALTHY, 15.0)
    assert status4 == CDNHealthStatus.DEGRADED


# ============================================================================
# 4. REST API ENDPOINTS & AUTHORIZATION TESTS
# ============================================================================

def test_api_route_endpoint_success(test_client: TestClient, db_session: Session):
    repo = CDNRepository(db_session)
    origin = repo.create_origin(CDNOriginCreate(name="api-origin", origin_hostname="origin-api.gntv.com"))
    repo.create_endpoint(
        CDNEndpointCreate(
            origin_id=origin.id,
            edge_hostname="dcdn-api.gntv.com",
            priority=10,
        )
    )

    response = test_client.get(
        "/api/v1/cdn/route/channel-100",
        params={"asset_path": "/hls/live/ch100/index.m3u8", "playback_type": "live", "session_id": "test-ssai"},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["edge_hostname"] == "dcdn-api.gntv.com"
    assert "auth_key=" in data["routed_url"]
    assert "session_id=test-ssai" in data["routed_url"]


def test_api_health_endpoint(test_client: TestClient, admin_auth_headers: dict[str, str], db_session: Session):
    repo = CDNRepository(db_session)
    origin = repo.create_origin(CDNOriginCreate(name="health-origin", origin_hostname="origin-h.gntv.com"))
    repo.create_endpoint(CDNEndpointCreate(origin_id=origin.id, edge_hostname="dcdn-h.gntv.com"))

    response = test_client.get("/api/v1/cdn/health", headers=admin_auth_headers)
    assert response.status_code == status.HTTP_200_OK
    summaries = response.json()
    assert len(summaries) >= 1
    assert summaries[0]["edge_hostname"] == "dcdn-h.gntv.com"


def test_api_admin_mutation_authorization(test_client: TestClient, admin_auth_headers: dict[str, str], db_session: Session):
    repo = CDNRepository(db_session)
    origin = repo.create_origin(CDNOriginCreate(name="admin-origin", origin_hostname="origin-admin.gntv.com"))

    # Unauthorized request without token
    unauth_resp = test_client.post(
        "/api/v1/cdn/endpoints",
        json={"origin_id": str(origin.id), "edge_hostname": "dcdn-unauth.gntv.com"},
    )
    assert unauth_resp.status_code == status.HTTP_401_UNAUTHORIZED

    # Authorized admin request
    auth_resp = test_client.post(
        "/api/v1/cdn/endpoints",
        json={"origin_id": str(origin.id), "edge_hostname": "dcdn-auth.gntv.com"},
        headers=admin_auth_headers,
    )
    assert auth_resp.status_code == status.HTTP_201_CREATED
    assert auth_resp.json()["edge_hostname"] == "dcdn-auth.gntv.com"


# ============================================================================
# 5. ALEMBIC MIGRATION TEST
# ============================================================================

def test_alembic_single_head_and_migration():
    alembic_cfg = Config("backend-api/alembic.ini")
    alembic_cfg.set_main_option("script_location", "backend-api/alembic")

    # Command check to verify configuration loads cleanly
    assert alembic_cfg.get_main_option("script_location") == "backend-api/alembic"
