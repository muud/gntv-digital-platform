"""Tests for Sprint 6.2 playback session lifecycle, heartbeats, and Redis concurrency control."""

from collections.abc import Generator
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.main import app
from app.modules.streaming.api import get_playback_service
from app.modules.streaming.models import (
    LiveChannel,
    Manifest,
    ManifestFormat,
    ManifestKind,
    ManifestStatus,
    PlaybackSessionStatus,
    RecordingPolicy,
    Stream,
    StreamKey,
    StreamProtocol,
)
from app.modules.streaming.repositories import StreamingRepository
from app.modules.streaming.schemas import (
    PlaybackHeartbeatRequest,
    PlaybackStopRequest,
)
from app.modules.streaming.services import PlaybackService, RedisSessionStore

PLAYBACK_TABLES = [
    Base.metadata.tables[name]
    for name in (
        "live_channels",
        "live_events",
        "stream_keys",
        "streams",
        "recordings",
        "playback_sessions",
        "manifests",
        "user_watch_history",
    )
]


@pytest.fixture()
def playback_db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=PLAYBACK_TABLES)
    local_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = local_session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine, tables=PLAYBACK_TABLES)
        engine.dispose()


def create_playable_channel(repo: StreamingRepository, code: str, name: str, slug: str) -> LiveChannel:
    channel = repo.add(
        LiveChannel(
            id=uuid4(),
            channel_code=code,
            name=name,
            slug=slug,
            ingest_policy={"allowed_protocols": ["rtmp"]},
            transcode_profile="hls-only",
            recording_policy=RecordingPolicy.NEVER,
            is_public=True,
            timezone="UTC",
            created_by=1,
            updated_by=1,
        )
    )
    key = repo.add(
        StreamKey(
            live_channel_id=channel.id,
            key_prefix=f"{code.lower()}_key",
            secret_hash="hash-only",
            allowed_protocols=["rtmp"],
            allowed_cidrs=[],
            created_by=1,
        )
    )
    stream = repo.add(
        Stream(
            live_channel_id=channel.id,
            stream_key_id=key.id,
            protocol=StreamProtocol.RTMP,
            idempotency_key=f"stream-{code.lower()}",
            created_by=1,
            updated_by=1,
        )
    )
    repo.add(
        Manifest(
            stream_id=stream.id,
            format=ManifestFormat.HLS,
            kind=ManifestKind.LIVE,
            status=ManifestStatus.READY,
            oss_object_key=f"live/{slug}/index.m3u8",
            cdn_path=f"/live/{slug}/index.m3u8",
            generation=1,
            renditions=[],
        )
    )
    return channel


def test_redis_session_store_concurrency_and_eviction():
    store = RedisSessionStore()
    user_id = 101

    s1 = uuid4()
    s2 = uuid4()
    s3 = uuid4()
    s4 = uuid4()

    # Acquire slots for 3 streams (limit = 3)
    assert store.acquire_slot(user_id, s1, limit=3, now_epoch=100.0) is None
    assert store.acquire_slot(user_id, s2, limit=3, now_epoch=105.0) is None
    assert store.acquire_slot(user_id, s3, limit=3, now_epoch=110.0) is None

    # Acquiring 4th stream should evict the oldest (s1)
    evicted = store.acquire_slot(user_id, s4, limit=3, now_epoch=115.0)
    assert evicted == s1


def test_redis_session_store_idle_sweep():
    store = RedisSessionStore()
    user_id = 202

    s1 = uuid4()
    s2 = uuid4()

    store.acquire_slot(user_id, s1, limit=3, now_epoch=100.0)
    store.acquire_slot(user_id, s2, limit=3, now_epoch=180.0)

    # Sweep idle sessions with 90s cutoff at timestamp 200.0
    # s1 score 100.0 < 200.0 - 90 = 110.0 -> evicted
    # s2 score 180.0 >= 110.0 -> active
    expired = store.sweep_idle_sessions(user_id, idle_cutoff_seconds=90.0, now_epoch=200.0)
    assert expired == [s1]


def test_playback_service_heartbeat_and_stop(playback_db: Session):
    repo = StreamingRepository(playback_db)
    channel = create_playable_channel(repo, "MAIN01", "GNTV Live Main", "gntv-live-main")

    service = PlaybackService(
        repo,
        signing_secret="test-secret-sprint62-at-least-32-chars",
        token_ttl_seconds=3600,
        public_base_url="http://localhost:8000",
    )

    # Create session for user
    user_id = 42
    session, _, _, _ = service._create(
        channel.id,
        device_id="device-web-01",
        user_id=user_id,
        protocol=ManifestFormat.HLS,
        trusted_country_code="US",
    )

    # Dispatch heartbeat
    hb_req = PlaybackHeartbeatRequest(position_ms=45000, state=PlaybackSessionStatus.PLAYING)
    res = service.heartbeat(session.id, hb_req)
    assert res.session_id == session.id
    assert res.status == PlaybackSessionStatus.PLAYING
    assert res.position_ms == 45000

    # Verify session updated in DB
    updated = repo.get_playback_session(session.id)
    assert updated is not None
    assert updated.position_ms == 45000
    assert updated.status == PlaybackSessionStatus.PLAYING

    # Stop session
    stop_req = PlaybackStopRequest(position_ms=120000)
    stop_res = service.stop_session(session.id, stop_req)
    assert stop_res.status == "ended"
    assert stop_res.final_position_ms == 120000


def test_concurrency_lease_eviction_revokes_oldest_session(playback_db: Session):
    repo = StreamingRepository(playback_db)
    channel = create_playable_channel(repo, "CONC01", "GNTV Live Concurrency", "gntv-live-concurrency")

    store = RedisSessionStore()
    service = PlaybackService(
        repo,
        signing_secret="test-secret-concurrency-at-least-32-chars",
        token_ttl_seconds=3600,
        public_base_url="http://localhost:8000",
        redis_store=store,
    )

    user_id = 999
    s1, _, _, _ = service._create(channel.id, device_id="dev-1", user_id=user_id, protocol=ManifestFormat.HLS, trusted_country_code="US")
    s2, _, _, _ = service._create(channel.id, device_id="dev-2", user_id=user_id, protocol=ManifestFormat.HLS, trusted_country_code="US")
    s3, _, _, _ = service._create(channel.id, device_id="dev-3", user_id=user_id, protocol=ManifestFormat.HLS, trusted_country_code="US")

    # All 3 active
    assert repo.get_playback_session(s1.id).status == PlaybackSessionStatus.AUTHORIZED

    # Create 4th stream -> s1 should be evicted and revoked
    s4, _, _, _ = service._create(channel.id, device_id="dev-4", user_id=user_id, protocol=ManifestFormat.HLS, trusted_country_code="US")

    assert repo.get_playback_session(s1.id).status == PlaybackSessionStatus.REVOKED

    # Subsequent heartbeat on evicted s1 fails with 409 session_evicted
    with pytest.raises(Exception) as exc_info:
        service.heartbeat(s1.id, PlaybackHeartbeatRequest(position_ms=1000))
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "session_evicted"


def test_router_heartbeat_stop_revoke_endpoints(playback_db: Session):
    repo = StreamingRepository(playback_db)
    channel = create_playable_channel(repo, "ROUT01", "GNTV Router Test", "gntv-router-test")

    service = PlaybackService(
        repo,
        signing_secret="test-secret-router-at-least-32-chars",
        token_ttl_seconds=3600,
        public_base_url="http://localhost:8000",
    )

    app.dependency_overrides[get_playback_service] = lambda: service
    client = TestClient(app)

    try:
        session, _, _, _ = service._create(
            channel.id,
            device_id="device-router",
            user_id=12,
            protocol=ManifestFormat.HLS,
            trusted_country_code="US",
        )

        # 1. Heartbeat endpoint
        hb_resp = client.post(
            f"/api/v1/streaming/playback/{session.id}/heartbeat",
            json={"position_ms": 30000, "state": "playing"},
        )
        assert hb_resp.status_code == 200
        assert hb_resp.json()["position_ms"] == 30000
        assert hb_resp.json()["status"] == "playing"

        # 2. Stop endpoint
        stop_resp = client.post(
            f"/api/v1/streaming/playback/{session.id}/stop",
            json={"position_ms": 60000},
        )
        assert stop_resp.status_code == 200
        assert stop_resp.json()["status"] == "ended"
        assert stop_resp.json()["final_position_ms"] == 60000

        # 3. Revoke endpoint
        rev_resp = client.post(
            f"/api/v1/streaming/playback/{session.id}/revoke",
            json={"reason": "security override"},
        )
        assert rev_resp.status_code == 200
        assert rev_resp.json()["status"] == "revoked"
    finally:
        app.dependency_overrides.clear()
