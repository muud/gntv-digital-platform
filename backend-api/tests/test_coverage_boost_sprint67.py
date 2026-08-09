"""Coverage booster tests for Sprint 6.7 release hardening."""

from datetime import UTC, datetime
from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.streaming.models import (
    DRMKey,
    DRMPolicy,
    GeoPolicy,
    LiveChannel,
    RecordingPolicy,
    Stream,
    StreamKey,
    StreamProtocol,
    StreamStatus,
    ChannelStatus,
    RecordingStatus,
)
from app.modules.streaming.models.domain import QoESessionMetric
from app.modules.streaming.repositories import DRMRepository, StreamingRepository
from app.modules.streaming.repositories.telemetry import QoERepository
from app.modules.streaming.services import RedisSessionStore, QoEService
from app.modules.streaming.schemas.contracts import TelemetryBatchRequest, TelemetryEventItem


@pytest.fixture()
def boost_db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_streaming_repository_queries(boost_db: Session):
    repo = StreamingRepository(boost_db)
    
    ch = LiveChannel(
        id=uuid4(),
        channel_code="BOOST01",
        name="Boost Channel",
        slug="boost-channel",
        ingest_policy={},
        transcode_profile="hls-only",
        recording_policy=RecordingPolicy.NEVER,
        is_public=True,
        timezone="UTC",
        created_by=1,
        updated_by=1,
    )
    repo.add(ch)

    sk = StreamKey(
        id=uuid4(),
        live_channel_id=ch.id,
        key_prefix="boost_key",
        secret_hash="secret_hash_value",
        created_by=1,
    )
    repo.add(sk)

    st = Stream(
        id=uuid4(),
        live_channel_id=ch.id,
        stream_key_id=sk.id,
        protocol=StreamProtocol.RTMP,
        status=StreamStatus.LIVE,
        idempotency_key="boost-stream-1",
        created_by=1,
        updated_by=1,
    )
    repo.add(st)

    # Test queries with filters and cursors
    res_channels = repo.channels(limit=10, before_created_at=datetime.now(UTC), before_id=ch.id, status=ChannelStatus.DRAFT, public_only=True)
    assert isinstance(res_channels, list)

    res_streams = repo.streams(limit=10, before_created_at=datetime.now(UTC), before_id=st.id, channel_id=ch.id, status=StreamStatus.LIVE, protocol=StreamProtocol.RTMP)
    assert len(res_streams) == 1

    res_recs = repo.recordings(limit=10, before_created_at=datetime.now(UTC), before_id=uuid4(), stream_id=st.id, channel_id=ch.id, status=RecordingStatus.RECORDING)
    assert isinstance(res_recs, list)


def test_drm_repository_all_methods(boost_db: Session):
    repo = DRMRepository(boost_db)
    
    # 1. DRM Policy
    policy = DRMPolicy(
        name="Boost-Policy",
        provider="alibaba_kms",
    )
    repo.add_drm_policy(policy)
    assert repo.get_drm_policy(policy.id) is not None
    assert repo.get_drm_policy_by_name("Boost-Policy") is not None

    # 2. Geo Policy
    geo = GeoPolicy(
        name="Boost-Geo",
        country_allow_list=["US", "KE"],
        country_deny_list=[],
    )
    repo.add_geo_policy(geo)
    assert repo.get_geo_policy(geo.id) is not None

    # 3. DRM Key
    channel_id = uuid4()
    asset_id = uuid4()
    key = DRMKey(
        key_id=uuid4(),
        encrypted_key_envelope="encrypted_envelope_bytes",
        live_channel_id=channel_id,
        asset_id=asset_id,
    )
    repo.add_drm_key(key)
    assert repo.get_drm_key(key.key_id) is not None
    assert repo.get_drm_key_for_channel(channel_id) is not None
    assert repo.get_drm_key_for_asset(asset_id) is not None


class FakeRedisClient:
    def __init__(self):
        self.zsets = {}
        self.meta = {}

    def zadd(self, key, mapping, xx=False):
        if key not in self.zsets:
            if xx:
                return
            self.zsets[key] = {}
        for member, score in mapping.items():
            if xx and member not in self.zsets[key]:
                continue
            self.zsets[key][member] = float(score)

    def zcard(self, key):
        return len(self.zsets.get(key, {}))

    def zrange(self, key, start, stop):
        items = sorted(self.zsets.get(key, {}).items(), key=lambda x: x[1])
        stop_idx = len(items) if stop == -1 else stop + 1
        return [m.encode() for m, _ in items[start:stop_idx]]

    def zrem(self, key, member):
        if key in self.zsets and member in self.zsets[key]:
            del self.zsets[key][member]

    def delete(self, key):
        self.meta.pop(key, None)

    def zrangebyscore(self, key, min_score, max_score):
        items = self.zsets.get(key, {})
        res = []
        for m, score in items.items():
            if min_score <= score <= max_score:
                res.append(m.encode())
        return res


def test_redis_session_store_with_redis():
    fake_redis = FakeRedisClient()
    store = RedisSessionStore(redis_client=fake_redis)

    u_id = 55
    s1 = uuid4()
    s2 = uuid4()
    s3 = uuid4()

    assert store.acquire_slot(u_id, s1, limit=2, now_epoch=10.0) is None
    assert store.acquire_slot(u_id, s2, limit=2, now_epoch=20.0) is None
    evicted = store.acquire_slot(u_id, s3, limit=2, now_epoch=30.0)
    assert evicted == s1

    store.record_heartbeat(u_id, s2, now_epoch=40.0)
    store.release_slot(u_id, s2)

    s4 = uuid4()
    store.acquire_slot(u_id, s4, limit=2, now_epoch=10.0)
    expired = store.sweep_idle_sessions(u_id, idle_cutoff_seconds=5.0, now_epoch=20.0)
    assert s4 in expired


def test_telemetry_service_and_repo(boost_db: Session):
    repo = QoERepository(boost_db)
    service = QoEService(repo)

    sess_id = uuid4()
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    batch = TelemetryBatchRequest(
        session_id=sess_id,
        sequence_number=1,
        client_timestamp_ms=now_ms,
        events=[
            TelemetryEventItem(
                event_type="startup",
                timestamp_ms=now_ms,
                position_ms=0,
                bitrate_bps=3000000,
                metadata={"stall_duration_ms": 250},
            )
        ]
    )

    resp = service.ingest_batch(batch)
    assert resp.accepted_count == 1

    saved = repo.get_session_metric(sess_id)
    assert saved is not None
    assert saved.startup_latency_ms == 250

    # Test upsert
    metric = QoESessionMetric(
        playback_session_id=sess_id,
        startup_latency_ms=900,
        total_rebuffer_duration_ms=300,
        rebuffer_count=2,
        rebuffer_ratio=0.01,
        average_bitrate_bps=5000000,
        total_watch_duration_ms=60000,
        completion_ratio=0.9,
        has_error=False,
    )
    repo.upsert_session_metric(metric)
    updated = repo.get_session_metric(sess_id)
    assert updated.startup_latency_ms == 900
