"""Dedicated tests for Module 7 Sprint 7.5 - Executive Analytics & Broadcaster Control Panel."""

from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.user import Role, User
from app.modules.cdn.models import CDNEndpoint, CDNEndpointMetric, CDNFailoverEvent, CDNHealthStatus, CDNOrigin, CDNProviderType
from app.modules.monetization.models import AdCampaign, AdImpression, AdImpressionEventType
from app.modules.streaming.models.domain import ChannelStatus, LiveChannel, PlaybackSession, PlaybackSessionStatus, QoEAggregateHourly, QoESessionMetric
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
    user.roles.append(role)
    db.add(user)
    db.commit()
    return user


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


def test_broadcaster_analytics_unauthorized():
    """Test accessing analytics endpoints without authentication returns 401."""
    db = make_db()
    client = make_client(db)
    res = client.get("/api/v1/analytics/broadcaster/overview")
    assert res.status_code == 401

    res_c = client.get("/api/v1/analytics/broadcaster/concurrency")
    assert res_c.status_code == 401


def test_broadcaster_analytics_forbidden_role():
    """Test accessing analytics endpoints with a non-admin/non-operator role returns 403."""
    db = make_db()
    client = make_client(db)
    user = create_user(db, "creator")
    res = client.get("/api/v1/analytics/broadcaster/overview", headers=auth_headers(user))
    assert res.status_code == 403
    assert "Admin or operator role required" in res.json()["detail"]


def test_broadcaster_analytics_empty_data():
    """Test analytics endpoints return valid null/0 responses when persistence is empty."""
    db = make_db()
    client = make_client(db)
    admin = create_user(db, "admin")
    headers = auth_headers(admin)

    res = client.get("/api/v1/analytics/broadcaster/overview", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["summary"]["active_viewers"] == 0
    assert data["summary"]["peak_concurrency"] == 0
    assert data["summary"]["qoe_score"] is None
    assert data["summary"]["cdn_offload_ratio"] is None
    assert data["summary"]["total_failovers"] == 0
    assert data["summary"]["ad_impressions"] == 0
    assert data["summary"]["estimated_revenue_usd"] is None

    assert data["concurrency"]["total_active_viewers"] == 0
    assert data["concurrency"]["by_channel"] == []
    assert data["qoe"]["avg_startup_time_ms"] is None
    assert data["cdn"]["cache_hit_ratio"] is None
    assert data["monetization"]["estimated_revenue_usd"] is None


def test_broadcaster_analytics_invalid_date_range():
    """Test providing start_time > end_time returns 400 Bad Request."""
    db = make_db()
    client = make_client(db)
    op = create_user(db, "operator")
    headers = auth_headers(op)
    start = quote((datetime.now(UTC) + timedelta(days=1)).isoformat())
    end = quote(datetime.now(UTC).isoformat())

    res = client.get(f"/api/v1/analytics/broadcaster/overview?start_time={start}&end_time={end}", headers=headers)
    assert res.status_code == 400
    assert "Invalid date range" in res.json()["detail"]


def test_broadcaster_concurrency_analytics():
    """Test real-time concurrency metrics calculation and distribution breakdowns."""
    db = make_db()
    client = make_client(db)
    admin = create_user(db, "admin")
    headers = auth_headers(admin)

    # Create live channel
    channel = LiveChannel(
        channel_code="CH-SOM-01",
        name="GNTV Somalia News",
        slug="gntv-somalia-news",
        status=ChannelStatus.LIVE,
        transcode_profile="hls_720p",
        created_by=admin.id,
        updated_by=admin.id,
    )
    db.add(channel)
    db.commit()

    now = datetime.now(UTC)
    start_filter = quote((now - timedelta(hours=1)).isoformat())
    end_filter = quote((now + timedelta(hours=1)).isoformat())

    # Create active sessions
    s1 = PlaybackSession(
        live_channel_id=channel.id,
        device_id="mobile-iOS-16",
        country_code="SO",
        token_jti_hash=uuid4().hex,
        status=PlaybackSessionStatus.PLAYING,
        started_at=now - timedelta(minutes=10),
        last_seen_at=now,
        expires_at=now + timedelta(hours=1),
    )
    s2 = PlaybackSession(
        live_channel_id=channel.id,
        device_id="desktop-Chrome-Mac",
        country_code="KE",
        token_jti_hash=uuid4().hex,
        status=PlaybackSessionStatus.AUTHORIZED,
        started_at=now - timedelta(minutes=5),
        last_seen_at=now,
        expires_at=now + timedelta(hours=1),
    )
    db.add_all([s1, s2])
    db.commit()

    res = client.get("/api/v1/analytics/broadcaster/concurrency", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["total_active_viewers"] == 2
    assert data["peak_concurrency"] >= 2
    assert len(data["by_channel"]) >= 1
    assert data["by_channel"][0]["dimension"] == "GNTV Somalia News"
    assert data["by_channel"][0]["count"] == 2
    assert len(data["by_device"]) >= 1
    assert len(data["trend"]) >= 1

    # Filter by region, channel_id, device_category and date window
    url = f"/api/v1/analytics/broadcaster/concurrency?channel_id={channel.id}&region=SO&device_category=iOS&start_time={start_filter}&end_time={end_filter}"
    res_filt = client.get(url, headers=headers)
    assert res_filt.status_code == 200
    filt_data = res_filt.json()
    assert filt_data["total_active_viewers"] == 1


def test_broadcaster_qoe_analytics():
    """Test QoE metrics aggregation, percentiles, error rates, and score calculation."""
    db = make_db()
    client = make_client(db)
    admin = create_user(db, "admin")
    headers = auth_headers(admin)

    chan_id = uuid4()
    now = datetime.now(UTC)
    qoe1 = QoESessionMetric(
        playback_session_id=uuid4(),
        live_channel_id=chan_id,
        startup_latency_ms=450,
        rebuffer_ratio=0.01,
        average_bitrate_bps=4500000,
        has_error=False,
        country_code="SO",
        device_category="web",
        created_at=now - timedelta(minutes=20),
    )
    qoe2 = QoESessionMetric(
        playback_session_id=uuid4(),
        live_channel_id=chan_id,
        startup_latency_ms=650,
        rebuffer_ratio=0.03,
        average_bitrate_bps=3500000,
        has_error=True,
        country_code="KE",
        device_category="mobile",
        created_at=now - timedelta(minutes=10),
    )
    db.add_all([qoe1, qoe2])

    agg = QoEAggregateHourly(
        window_start=now - timedelta(hours=1),
        target_type="channel",
        target_id=chan_id,
        device_category="all",
        country_code="SO",
        total_sessions=2,
        p50_startup_latency_ms=500,
        avg_rebuffer_ratio=0.02,
        total_errors=1,
        avg_bitrate_bps=4000000,
    )
    db.add(agg)
    db.commit()

    res = client.get("/api/v1/analytics/broadcaster/qoe", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["total_sessions"] == 2
    assert data["avg_startup_time_ms"] == 550.0
    assert data["avg_rebuffer_ratio"] == 0.02
    assert data["total_playback_errors"] == 1
    assert data["qoe_score"] is not None
    assert data["qoe_score"] > 0
    assert len(data["trend"]) == 1

    # Test filters
    start_filter = quote((now - timedelta(hours=2)).isoformat())
    end_filter = quote((now + timedelta(hours=1)).isoformat())
    url = f"/api/v1/analytics/broadcaster/qoe?channel_id={chan_id}&region=SO&start_time={start_filter}&end_time={end_filter}"
    res_f = client.get(url, headers=headers)
    assert res_f.status_code == 200
    assert res_f.json()["total_sessions"] == 1


def test_broadcaster_cdn_analytics():
    """Test CDN executive metrics, cache hit ratio, origin offload, and failovers."""
    db = make_db()
    client = make_client(db)
    admin = create_user(db, "admin")
    headers = auth_headers(admin)

    origin = CDNOrigin(name="primary-origin-1", origin_hostname="origin.gntv.com")
    db.add(origin)
    db.commit()

    endpoint = CDNEndpoint(
        origin_id=origin.id,
        provider_type=CDNProviderType.ALIBABA_DCDN,
        edge_hostname="edge-ali.gntv.com",
        health_status=CDNHealthStatus.HEALTHY,
    )
    db.add(endpoint)
    db.commit()

    now = datetime.now(UTC)
    metric = CDNEndpointMetric(
        endpoint_id=endpoint.id,
        provider_type=CDNProviderType.ALIBABA_DCDN,
        region_code="ea-south",
        window_start=now - timedelta(hours=1),
        window_end=now,
        request_count=1000,
        bandwidth_bytes=500000000,
        cache_hit_count=900,
        cache_miss_count=100,
        origin_fetch_count=100,
        avg_latency_ms=25.5,
        p95_latency_ms=45.0,
    )
    db.add(metric)

    failover = CDNFailoverEvent(
        from_endpoint_id=endpoint.id,
        provider_type=CDNProviderType.ALIBABA_DCDN,
        region_code="ea-south",
        reason="Latency spike threshold exceeded",
        created_at=now - timedelta(minutes=10),
    )
    db.add(failover)
    db.commit()

    res = client.get("/api/v1/analytics/broadcaster/cdn", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["total_requests"] == 1000
    assert data["cache_hit_count"] == 900
    assert data["cache_hit_ratio"] == 0.9
    assert data["origin_offload_ratio"] == 0.9
    assert data["failover_count"] == 1
    assert data["endpoint_health_counts"]["HEALTHY"] == 1
    assert len(data["regional_performance"]) == 1
    assert data["regional_performance"][0]["region_code"] == "ea-south"
    assert len(data["traffic_allocation"]) == 1

    # Filter test
    start_filter = quote((now - timedelta(hours=2)).isoformat())
    end_filter = quote((now + timedelta(hours=1)).isoformat())
    url = f"/api/v1/analytics/broadcaster/cdn?provider=alibaba_dcdn&region=ea-south&start_time={start_filter}&end_time={end_filter}"
    res_f = client.get(url, headers=headers)
    assert res_f.status_code == 200


def test_broadcaster_monetization_analytics():
    """Test monetization analytics, ad impressions, completes, fill, and CPM revenue estimates."""
    db = make_db()
    client = make_client(db)
    admin = create_user(db, "admin")
    headers = auth_headers(admin)

    # Campaign with authoritative CPM in metadata_json
    now = datetime.now(UTC)
    c1 = AdCampaign(
        name="Global Ramadan Campaign 2026",
        status="active",
        metadata_json={"cpm": 15.0},
    )
    # Campaign without CPM rate
    c2 = AdCampaign(
        name="Community Announcement",
        status="active",
        metadata_json={},
    )
    db.add_all([c1, c2])
    db.commit()

    # Create impressions for c1
    imp1 = AdImpression(
        campaign_id=c1.id,
        session_id="sess-101",
        event_type=AdImpressionEventType.IMPRESSION,
        idempotency_key=uuid4().hex,
        occurred_at=now - timedelta(minutes=10),
    )
    imp2 = AdImpression(
        campaign_id=c1.id,
        session_id="sess-101",
        event_type=AdImpressionEventType.COMPLETE,
        idempotency_key=uuid4().hex,
        occurred_at=now - timedelta(minutes=5),
    )
    db.add_all([imp1, imp2])
    db.commit()

    res = client.get("/api/v1/analytics/broadcaster/monetization", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["total_ad_impressions"] == 1
    assert data["total_completed_ads"] == 1
    assert data["ad_fill_rate"] == 1.0
    assert data["estimated_revenue_usd"] == 0.01  # (1 / 1000) * 15.0 = 0.015 -> rounded 0.01

    # Verify campaign breakdown
    camps = data["campaign_performance"]
    assert len(camps) == 2
    c1_perf = next(c for c in camps if c["campaign_name"] == "Global Ramadan Campaign 2026")
    assert c1_perf["impressions"] == 1
    assert c1_perf["estimated_revenue_usd"] is not None

    c2_perf = next(c for c in camps if c["campaign_name"] == "Community Announcement")
    assert c2_perf["estimated_revenue_usd"] is None  # CPM missing, no fake revenue

    # Filter test
    start_filter = quote((now - timedelta(hours=1)).isoformat())
    end_filter = quote((now + timedelta(hours=1)).isoformat())
    url = f"/api/v1/analytics/broadcaster/monetization?campaign_id={c1.id}&start_time={start_filter}&end_time={end_filter}"
    res_f = client.get(url, headers=headers)
    assert res_f.status_code == 200


def test_broadcaster_regional_and_channel_analytics():
    """Test regional and channel analytics endpoint contracts."""
    db = make_db()
    client = make_client(db)
    op = create_user(db, "operator")
    headers = auth_headers(op)

    now = datetime.now(UTC)
    channel = LiveChannel(
        channel_code="CH-EA-02",
        name="GNTV East Africa Live",
        slug="gntv-east-africa-live",
        status=ChannelStatus.LIVE,
        transcode_profile="hls_1080p",
        created_by=op.id,
        updated_by=op.id,
    )
    db.add(channel)
    db.commit()

    s = PlaybackSession(
        live_channel_id=channel.id,
        device_id="smart-TV-Samsung",
        country_code="SO",
        token_jti_hash=uuid4().hex,
        status=PlaybackSessionStatus.PLAYING,
        started_at=now - timedelta(minutes=5),
        last_seen_at=now,
        expires_at=now + timedelta(hours=1),
    )
    db.add(s)
    db.commit()

    res_reg = client.get("/api/v1/analytics/broadcaster/regions", headers=headers)
    assert res_reg.status_code == 200
    reg_list = res_reg.json()
    assert len(reg_list) >= 1
    assert reg_list[0]["region_code"] == "SO"
    assert reg_list[0]["active_viewers"] == 1

    res_chan = client.get("/api/v1/analytics/broadcaster/channels", headers=headers)
    assert res_chan.status_code == 200
    chan_list = res_chan.json()
    assert len(chan_list) >= 1
    ch_data = next(c for c in chan_list if c["channel_name"] == "GNTV East Africa Live")
    assert ch_data["active_viewers"] == 1
