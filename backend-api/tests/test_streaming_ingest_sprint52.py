"""Sprint 5.2 tests for the RTMP/SRT ingest control plane."""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Any
from uuid import UUID, uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, settings
from app.core.database import Base, get_db
from app.main import app
from app.modules.streaming.api.ingest_router import (
    coordination,
    get_ingest_dispatcher,
    rtmp_service,
    srt_service,
)
from app.modules.streaming.ingest.contracts import (
    EncoderRegistrationRequest,
    EncoderRegistrationResponse,
    IngestAdmissionResponse,
    IngestEventType,
    IngestHealthMetrics,
    IngestHeartbeatRequest,
    IngestStateEventRequest,
    RTMPAdmissionRequest,
    SRTAdmissionRequest,
)
from app.modules.streaming.ingest.coordination import RedisIngestCoordination
from app.modules.streaming.ingest.dispatch import CeleryIngestDispatcher
from app.modules.streaming.ingest.errors import IngestError
from app.modules.streaming.ingest.security import StreamKeyValidator
from app.modules.streaming.ingest.services import (
    EncoderRegistrationService,
    RTMPIngestService,
    SRTIngestService,
)
from app.modules.streaming.ingest.state_machine import IngestStateMachine
from app.modules.streaming.models import (
    ChannelStatus,
    LiveChannel,
    RecordingPolicy,
    StreamKey,
    StreamKeyStatus,
    StreamProtocol,
    StreamStatus,
)
from app.modules.streaming.repositories import StreamingRepository

STREAMING_TABLES = [
    Base.metadata.tables[name]
    for name in (
        "live_channels",
        "live_events",
        "stream_keys",
        "streams",
        "recordings",
        "playback_sessions",
        "transcoding_jobs",
        "manifests",
        "thumbnails",
    )
]


@pytest.fixture()
def ingest_db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=STREAMING_TABLES)
    local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = local()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine, tables=STREAMING_TABLES)
        engine.dispose()


class FakeCoordination:
    def __init__(self) -> None:
        self.registrations: dict[UUID, dict[str, Any]] = {}
        self.leases: dict[UUID, UUID] = {}
        self.health: dict[UUID, dict[str, Any]] = {}
        self.key_cache: dict[str, dict[str, Any]] = {}
        self.available = True

    async def register_encoder(self, registration_id: UUID, payload: dict[str, Any], ttl: int) -> bool:
        assert ttl > 0
        if registration_id in self.registrations:
            return False
        self.registrations[registration_id] = payload
        return True

    async def encoder(self, registration_id: UUID) -> dict[str, Any] | None:
        return self.registrations.get(registration_id)

    async def acquire_stream_lease(self, channel_id: UUID, stream_id: UUID, ttl: int) -> bool:
        assert ttl > 0
        if channel_id in self.leases:
            return False
        self.leases[channel_id] = stream_id
        return True

    async def renew_stream_lease(self, channel_id: UUID, stream_id: UUID, ttl: int) -> bool:
        assert ttl > 0
        return self.leases.get(channel_id) == stream_id

    async def release_stream_lease(self, channel_id: UUID, stream_id: UUID) -> bool:
        if self.leases.get(channel_id) != stream_id:
            return False
        del self.leases[channel_id]
        return True

    async def store_health(self, stream_id: UUID, health: dict[str, Any], ttl: int) -> None:
        assert ttl > 0
        self.health[stream_id] = health

    async def cached_key_validation(self, fingerprint: str) -> dict[str, Any] | None:
        return self.key_cache.get(fingerprint)

    async def cache_key_validation(
        self, fingerprint: str, payload: dict[str, Any], ttl: int
    ) -> None:
        assert ttl > 0
        self.key_cache[fingerprint] = payload

    async def ping(self) -> bool:
        return self.available


class FakeDispatcher:
    def __init__(self, *, available: bool = True, fail: bool = False) -> None:
        self.available = available
        self.fail = fail
        self.events: list[tuple[str, dict[str, Any], str]] = []

    async def dispatch(
        self, event_name: str, payload: dict[str, Any], *, idempotency_key: str
    ) -> str:
        if self.fail:
            raise RuntimeError("broker unavailable")
        self.events.append((event_name, payload, idempotency_key))
        return idempotency_key

    def configured(self) -> bool:
        return self.available


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.pong: Any = True

    async def get(self, name: str) -> str | None:
        return self.values.get(name)

    async def set(self, name: str, value: str, **kwargs: Any) -> bool:
        if kwargs.get("nx") and name in self.values:
            return False
        self.values[name] = value
        return True

    async def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> int:
        assert numkeys == 1
        key, expected = str(keys_and_args[0]), str(keys_and_args[1])
        if self.values.get(key) != expected:
            return 0
        if "DEL" in script:
            del self.values[key]
        return 1

    async def ping(self) -> Any:
        return self.pong


class FakeAsyncResult:
    id = "task-1"


class FakeCelery:
    def __init__(self) -> None:
        self.conf = type("Config", (), {"broker_url": "redis://test"})()
        self.calls: list[dict[str, Any]] = []

    def send_task(self, name: str, **kwargs: Any) -> FakeAsyncResult:
        self.calls.append({"name": name, **kwargs})
        return FakeAsyncResult()


def create_channel_and_key(
    db: Session,
    *,
    protocol: StreamProtocol,
    prefix: str,
    secret: str = "super-secret-stream-value",
    allowed_cidrs: list[str] | None = None,
    status: StreamKeyStatus = StreamKeyStatus.ACTIVE,
    expires_at: datetime | None = None,
) -> tuple[LiveChannel, StreamKey]:
    repository = StreamingRepository(db)
    channel = repository.add(
        LiveChannel(
            channel_code=f"GNTV-{prefix.upper()}",
            name=f"GNTV {prefix}",
            slug=f"gntv-{prefix}",
            status=ChannelStatus.READY,
            ingest_policy={"allowed_protocols": [protocol.value], "redundancy": "primary_only"},
            transcode_profile="future-profile-only",
            recording_policy=RecordingPolicy.NEVER,
            timezone="Africa/Nairobi",
            created_by=1,
            updated_by=1,
        )
    )
    key = repository.add(
        StreamKey(
            live_channel_id=channel.id,
            key_prefix=prefix,
            secret_hash=PasswordHasher().hash(secret),
            status=status,
            allowed_protocols=[protocol.value],
            allowed_cidrs=allowed_cidrs or [],
            expires_at=expires_at,
            created_by=1,
        )
    )
    db.commit()
    return channel, key


async def register_encoder(
    coordination_store: FakeCoordination,
    *,
    protocol: StreamProtocol,
    source_ip: str = "203.0.113.10",
) -> tuple[EncoderRegistrationRequest, EncoderRegistrationResponse]:
    request = EncoderRegistrationRequest(
        encoder_id=f"atem-{protocol.value}",
        connection_id=f"connection-{protocol.value}",
        gateway_node="gateway-1",
        protocol=protocol,
        source_ip=ip_address(source_ip),
        manufacturer="Blackmagic Design",
        model="ATEM Television Studio",
        capabilities=["video", "audio"],
    )
    response = await EncoderRegistrationService(coordination_store).register(request)
    return request, response


def rtmp_request(
    registration: EncoderRegistrationRequest,
    response: EncoderRegistrationResponse,
    *,
    key: str,
    tls: bool = True,
) -> RTMPAdmissionRequest:
    return RTMPAdmissionRequest(
        stream_key=SecretStr(key),
        encoder_registration_id=response.registration_id,
        encoder_id=registration.encoder_id,
        connection_id=registration.connection_id,
        gateway_node=registration.gateway_node,
        source_ip=registration.source_ip,
        application="live",
        stream_name="gntv-news",
        tls=tls,
    )


def test_ingest_contracts_reject_unsafe_or_ambiguous_values() -> None:
    with pytest.raises(ValidationError):
        EncoderRegistrationRequest.model_validate(
            {
                "encoder_id": "bad encoder",
                "connection_id": "connection-1",
                "gateway_node": "gateway-1",
                "protocol": "rtmp",
                "source_ip": "not-an-ip",
            }
        )

    with pytest.raises(ValidationError, match="INGEST_GATEWAY_TOKEN"):
        Settings(
            ENVIRONMENT="production",
            POSTGRES_USER="test",
            POSTGRES_PASSWORD="test",
            POSTGRES_DB="test",
            DATABASE_URL="sqlite://",
            REDIS_URL="redis://localhost:6379/0",
            INGEST_GATEWAY_TOKEN="development-ingest-gateway-token",
        )
    with pytest.raises(ValidationError):
        EncoderRegistrationRequest.model_validate(
            {
                "encoder_id": "atem-1",
                "connection_id": "connection-1",
                "gateway_node": "gateway-1",
                "protocol": "rtmp",
                "source_ip": "203.0.113.1",
                "capabilities": ["VIDEO", "video"],
            }
        )
    with pytest.raises(ValidationError):
        SRTAdmissionRequest.model_validate(
            {
                "stream_key": "key.secret",
                "encoder_registration_id": uuid4(),
                "encoder_id": "atem-1",
                "connection_id": "connection-1",
                "gateway_node": "gateway-1",
                "source_ip": "203.0.113.1",
                "stream_id": "channel-1",
                "mode": "listener",
                "encryption": "none",
                "latency_ms": 120,
            }
        )


def test_stream_key_validation_enforces_hash_status_expiry_protocol_and_cidr(ingest_db: Session) -> None:
    _, key = create_channel_and_key(
        ingest_db,
        protocol=StreamProtocol.RTMP,
        prefix="secure",
        allowed_cidrs=["203.0.113.0/24"],
    )
    validator = StreamKeyValidator(StreamingRepository(ingest_db))
    validated = validator.validate(
        "secure.super-secret-stream-value",
        protocol=StreamProtocol.RTMP,
        source_ip=__import__("ipaddress").ip_address("203.0.113.9"),
    )
    assert validated.record.id == key.id
    for candidate, protocol, source_ip, expected_code in (
        ("malformed", StreamProtocol.RTMP, "203.0.113.9", "invalid_stream_key"),
        ("secure.wrong", StreamProtocol.RTMP, "203.0.113.9", "invalid_stream_key"),
        ("secure.super-secret-stream-value", StreamProtocol.SRT, "203.0.113.9", "protocol_not_allowed"),
        ("secure.super-secret-stream-value", StreamProtocol.RTMP, "198.51.100.2", "source_not_allowed"),
    ):
        with pytest.raises(IngestError) as raised:
            validator.validate(
                candidate,
                protocol=protocol,
                source_ip=__import__("ipaddress").ip_address(source_ip),
            )
        assert raised.value.code == expected_code

    key.status = StreamKeyStatus.REVOKED
    ingest_db.commit()
    with pytest.raises(IngestError) as revoked:
        validator.validate(
            "secure.super-secret-stream-value",
            protocol=StreamProtocol.RTMP,
            source_ip=__import__("ipaddress").ip_address("203.0.113.9"),
        )
    assert revoked.value.code == "invalid_stream_key"

    key.status = StreamKeyStatus.ACTIVE
    key.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    ingest_db.commit()
    with pytest.raises(IngestError) as expired:
        validator.validate(
            "secure.super-secret-stream-value",
            protocol=StreamProtocol.RTMP,
            source_ip=__import__("ipaddress").ip_address("203.0.113.9"),
        )
    assert expired.value.code == "expired_stream_key"


def test_ingest_state_machine_allows_only_approved_transitions() -> None:
    machine = IngestStateMachine()
    assert machine.transition(StreamStatus.ADMITTED, IngestEventType.STARTED) == StreamStatus.LIVE
    assert machine.transition(StreamStatus.LIVE, IngestEventType.DEGRADED) == StreamStatus.DEGRADED
    assert machine.transition(StreamStatus.DEGRADED, IngestEventType.RECOVERED) == StreamStatus.LIVE
    assert machine.transition(StreamStatus.LIVE, IngestEventType.DISCONNECTED) == StreamStatus.STOPPED
    with pytest.raises(IngestError) as invalid:
        machine.transition(StreamStatus.STOPPED, IngestEventType.STARTED)
    assert invalid.value.status_code == 409


@pytest.mark.anyio
async def test_redis_coordination_uses_owned_compare_and_expire_leases() -> None:
    redis = FakeRedis()
    store = RedisIngestCoordination(redis)
    registration_id, channel_id, stream_id = uuid4(), uuid4(), uuid4()
    assert await store.register_encoder(registration_id, {"encoder_id": "atem-1"}, 60)
    assert not await store.register_encoder(registration_id, {"encoder_id": "other"}, 60)
    assert await store.encoder(registration_id) == {"encoder_id": "atem-1"}
    assert await store.acquire_stream_lease(channel_id, stream_id, 30)
    assert not await store.acquire_stream_lease(channel_id, uuid4(), 30)
    assert await store.renew_stream_lease(channel_id, stream_id, 30)
    assert not await store.renew_stream_lease(channel_id, uuid4(), 30)
    await store.store_health(stream_id, {"bitrate_kbps": 8000}, 30)
    fingerprint = store.key_fingerprint("secret", "rtmp", "203.0.113.1")
    assert len(fingerprint) == 64
    assert await store.cached_key_validation(fingerprint) is None
    await store.cache_key_validation(fingerprint, {"stream_key_id": str(uuid4())}, 30)
    assert await store.cached_key_validation(fingerprint) is not None
    assert await store.ping()
    assert await store.release_stream_lease(channel_id, stream_id)
    assert not await store.release_stream_lease(channel_id, stream_id)
    assert len(store.source_ip_hash("203.0.113.1")) == 64


@pytest.mark.anyio
async def test_celery_dispatcher_only_sends_allowlisted_control_messages() -> None:
    fake_celery = FakeCelery()
    producer = CeleryIngestDispatcher(fake_celery)
    task_id = await producer.dispatch(
        "streaming.ingest.admitted",
        {"stream_id": str(uuid4())},
        idempotency_key="admission-1",
    )
    assert task_id == "task-1"
    assert fake_celery.calls[0]["queue"] == "stream-control"
    assert fake_celery.calls[0]["task_id"] == "admission-1"
    assert producer.configured()
    with pytest.raises(ValueError):
        await producer.dispatch("streaming.transcode.start", {}, idempotency_key="forbidden")


@pytest.mark.anyio
async def test_rtmp_admission_lifecycle_is_idempotent_and_releases_lease(ingest_db: Session) -> None:
    channel, _ = create_channel_and_key(
        ingest_db,
        protocol=StreamProtocol.RTMP,
        prefix="rtmp1",
    )
    store = FakeCoordination()
    producer = FakeDispatcher()
    encoder, registration = await register_encoder(store, protocol=StreamProtocol.RTMP)
    service = RTMPIngestService(ingest_db, store, producer)
    request = rtmp_request(encoder, registration, key="rtmp1.super-secret-stream-value")

    admitted = await service.admit(request, idempotency_key="rtmp-admission-1")
    duplicate = await service.admit(request, idempotency_key="rtmp-admission-1")
    assert duplicate.stream_id == admitted.stream_id
    assert admitted.status == StreamStatus.ADMITTED
    stream = StreamingRepository(ingest_db).stream(admitted.stream_id)
    assert stream is not None
    assert stream.live_channel_id == channel.id
    assert "source_ip" not in stream.source_metadata
    assert "stream_key" not in stream.source_metadata
    assert "stream_name" not in stream.source_metadata
    assert stream.source_metadata["source_ip_hash"]
    assert producer.events[0][0] == "streaming.ingest.admitted"

    started = await service.apply_event(
        stream.id,
        IngestStateEventRequest(
            event=IngestEventType.STARTED,
            expected_version=1,
            health=IngestHealthMetrics(bitrate_kbps=8000),
        ),
    )
    assert started.status == StreamStatus.LIVE and started.lock_version == 2
    heartbeat = await service.heartbeat(
        stream.id,
        IngestHeartbeatRequest(
            expected_version=2,
            health=IngestHealthMetrics(bitrate_kbps=7900),
        ),
    )
    assert heartbeat.lock_version == 3
    assert store.health[stream.id]["bitrate_kbps"] == 7900
    degraded = await service.apply_event(
        stream.id,
        IngestStateEventRequest(
            event=IngestEventType.DEGRADED,
            expected_version=3,
            reason_code="packet_loss",
            health=IngestHealthMetrics(packet_loss_percent=4.2),
        ),
    )
    assert degraded.status == StreamStatus.DEGRADED
    recovered = await service.apply_event(
        stream.id,
        IngestStateEventRequest(
            event=IngestEventType.RECOVERED,
            expected_version=4,
            health=IngestHealthMetrics(packet_loss_percent=0.1),
        ),
    )
    assert recovered.status == StreamStatus.LIVE
    stopped = await service.apply_event(
        stream.id,
        IngestStateEventRequest(
            event=IngestEventType.DISCONNECTED,
            expected_version=5,
            reason_code="encoder_closed",
        ),
    )
    assert stopped.status == StreamStatus.STOPPED
    assert channel.id not in store.leases
    assert StreamingRepository(ingest_db).stream(stream.id).stopped_at is not None  # type: ignore[union-attr]


@pytest.mark.anyio
async def test_rtmp_rejects_unregistered_duplicate_insecure_and_dispatch_failure(ingest_db: Session) -> None:
    channel, _ = create_channel_and_key(
        ingest_db,
        protocol=StreamProtocol.RTMP,
        prefix="rtmp2",
    )
    store = FakeCoordination()
    encoder, registration = await register_encoder(store, protocol=StreamProtocol.RTMP)
    request = rtmp_request(encoder, registration, key="rtmp2.super-secret-stream-value")
    request.encoder_registration_id = uuid4()
    with pytest.raises(IngestError) as invalid_registration:
        await RTMPIngestService(ingest_db, store, FakeDispatcher()).admit(
            request, idempotency_key="rtmp-invalid-registration"
        )
    assert invalid_registration.value.code == "invalid_encoder_registration"

    request.encoder_registration_id = registration.registration_id
    request.tls = False
    with pytest.raises(IngestError) as insecure:
        await RTMPIngestService(ingest_db, store, FakeDispatcher()).admit(
            request, idempotency_key="rtmp-insecure"
        )
    assert insecure.value.code == "insecure_rtmp_not_allowed"

    request.tls = True
    admitted = await RTMPIngestService(ingest_db, store, FakeDispatcher()).admit(
        request, idempotency_key="rtmp-first"
    )
    with pytest.raises(IngestError) as duplicate:
        await RTMPIngestService(ingest_db, store, FakeDispatcher()).admit(
            request, idempotency_key="rtmp-second"
        )
    assert duplicate.value.code == "publisher_already_active"

    stream = StreamingRepository(ingest_db).stream(admitted.stream_id)
    assert stream is not None
    stream.status = StreamStatus.STOPPED
    ingest_db.commit()
    await store.release_stream_lease(channel.id, stream.id)
    with pytest.raises(IngestError) as dispatch_error:
        await RTMPIngestService(ingest_db, store, FakeDispatcher(fail=True)).admit(
            request, idempotency_key="rtmp-dispatch-failure"
        )
    assert dispatch_error.value.code == "ingest_dispatch_unavailable"
    failed = StreamingRepository(ingest_db).stream_by_idempotency_key("rtmp-dispatch-failure")
    assert failed is not None and failed.status == StreamStatus.FAILED


@pytest.mark.anyio
async def test_srt_admission_requires_matching_encrypted_registration(ingest_db: Session) -> None:
    create_channel_and_key(ingest_db, protocol=StreamProtocol.SRT, prefix="srt1")
    store = FakeCoordination()
    producer = FakeDispatcher()
    encoder, registration = await register_encoder(store, protocol=StreamProtocol.SRT)
    payload = SRTAdmissionRequest(
        stream_key=SecretStr("srt1.super-secret-stream-value"),
        encoder_registration_id=registration.registration_id,
        encoder_id=encoder.encoder_id,
        connection_id=encoder.connection_id,
        gateway_node=encoder.gateway_node,
        source_ip=encoder.source_ip,
        stream_id="#!::r=gntv-news,m=publish",
        mode="listener",
        encryption="aes256",
        latency_ms=120,
    )
    admitted = await SRTIngestService(ingest_db, store, producer).admit(
        payload, idempotency_key="srt-admission-1"
    )
    stream = StreamingRepository(ingest_db).stream(admitted.stream_id)
    assert stream is not None and stream.protocol == StreamProtocol.SRT
    assert stream.source_metadata["encryption"] == "aes256"
    assert "passphrase" not in stream.source_metadata
    assert "srt_stream_id" not in stream.source_metadata


class FakeRouteIngestService:
    async def admit(self, payload: Any, *, idempotency_key: str) -> IngestAdmissionResponse:
        assert payload.stream_key.get_secret_value().endswith("secret")
        assert idempotency_key == "route-request-1"
        return IngestAdmissionResponse(
            stream_id=uuid4(),
            live_channel_id=uuid4(),
            protocol=StreamProtocol.RTMP if isinstance(payload, RTMPAdmissionRequest) else StreamProtocol.SRT,
            status=StreamStatus.ADMITTED,
            lease_expires_at=datetime.now(UTC) + timedelta(seconds=30),
            status_url="/status",
        )

    async def heartbeat(self, stream_id: UUID, payload: IngestHeartbeatRequest) -> Any:
        raise IngestError("ingest_lease_lost", "Ingest lease is no longer owned", status_code=409)

    async def apply_event(self, stream_id: UUID, payload: IngestStateEventRequest) -> Any:
        raise IngestError("invalid_ingest_transition", "Invalid transition", status_code=409)


def test_ingest_routes_require_gateway_auth_and_expose_health(ingest_db: Session) -> None:
    fake = FakeRouteIngestService()
    store = FakeCoordination()
    producer = FakeDispatcher()

    def override_db() -> Generator[Session, None, None]:
        yield ingest_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[rtmp_service] = lambda: fake
    app.dependency_overrides[srt_service] = lambda: fake
    app.dependency_overrides[coordination] = lambda: store
    app.dependency_overrides[get_ingest_dispatcher] = lambda: producer
    client = TestClient(app)
    headers = {
        "X-GNTV-Gateway-Token": settings.INGEST_GATEWAY_TOKEN,
        "Idempotency-Key": "route-request-1",
    }
    payload = {
        "stream_key": "prefix.secret",
        "encoder_registration_id": str(uuid4()),
        "encoder_id": "atem-1",
        "connection_id": "connection-1",
        "gateway_node": "gateway-1",
        "source_ip": "203.0.113.1",
        "application": "live",
        "stream_name": "news",
        "tls": True,
    }
    try:
        assert client.post("/api/v1/streaming/ingest/rtmp/admit", json=payload).status_code == 422
        unauthorized = client.post(
            "/api/v1/streaming/ingest/rtmp/admit",
            headers={"X-GNTV-Gateway-Token": "invalid-gateway-token-value", "Idempotency-Key": "route-request-1"},
            json=payload,
        )
        assert unauthorized.status_code == 401
        admitted = client.post("/api/v1/streaming/ingest/rtmp/admit", headers=headers, json=payload)
        assert admitted.status_code == 201, admitted.text
        stream_id = uuid4()
        conflict = client.post(
            f"/api/v1/streaming/ingest/rtmp/sessions/{stream_id}/heartbeat",
            headers={"X-GNTV-Gateway-Token": settings.INGEST_GATEWAY_TOKEN},
            json={"expected_version": 1, "health": {}},
        )
        assert conflict.status_code == 409
        event_conflict = client.post(
            f"/api/v1/streaming/ingest/srt/sessions/{stream_id}/events",
            headers={"X-GNTV-Gateway-Token": settings.INGEST_GATEWAY_TOKEN},
            json={"event": "started", "expected_version": 1},
        )
        assert event_conflict.status_code == 409
        assert client.get("/api/v1/streaming/ingest/health/live").json()["status"] == "ok"
        ready = client.get("/api/v1/streaming/ingest/health/ready")
        assert ready.status_code == 200 and ready.json()["redis"] == "connected"
        producer.available = False
        degraded = client.get("/api/v1/streaming/ingest/health/ready")
        assert degraded.status_code == 503 and degraded.json()["status"] == "degraded"
    finally:
        app.dependency_overrides.clear()


def test_ingest_openapi_contains_only_control_plane_contracts() -> None:
    schema = app.openapi()
    expected = {
        "/api/v1/streaming/ingest/encoders/register",
        "/api/v1/streaming/ingest/rtmp/admit",
        "/api/v1/streaming/ingest/srt/admit",
        "/api/v1/streaming/ingest/rtmp/sessions/{stream_id}/heartbeat",
        "/api/v1/streaming/ingest/srt/sessions/{stream_id}/heartbeat",
        "/api/v1/streaming/ingest/rtmp/sessions/{stream_id}/events",
        "/api/v1/streaming/ingest/srt/sessions/{stream_id}/events",
        "/api/v1/streaming/ingest/sessions/{stream_id}",
        "/api/v1/streaming/ingest/health/live",
        "/api/v1/streaming/ingest/health/ready",
    }
    assert expected <= set(schema["paths"])
    serialized = str(schema).lower()
    assert "ffmpeg" not in serialized
    assert "transcode.start" not in serialized
