"""Sprint 5.1 tests for the Module 5 domain and contract foundation."""

import importlib.util
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.user import Role, User
from app.modules.distribution.api import get_distribution_service
from app.modules.distribution.models import (
    CDNSyncStatus,
    DistributionTarget,
    DistributionTargetStatus,
    DistributionTargetType,
    GeoFencingPolicy,
    GeoPolicyMode,
    GeoPolicyStatus,
)
from app.modules.distribution.repository import DistributionRepository
from app.modules.distribution.schemas import (
    DistributionTargetResponse,
    GeoFencingPolicyUpsertRequest,
)
from app.modules.streaming.api import get_streaming_service
from app.modules.streaming.models import (
    ChannelStatus,
    LiveChannel,
    PlaybackSession,
    RecordingPolicy,
    Stream,
    StreamKey,
    StreamProtocol,
    StreamStatus,
)
from app.modules.streaming.permissions import ALL_SCOPES, has_scope, scopes_for_roles
from app.modules.streaming.repositories import StreamingRepository
from app.modules.streaming.schemas import (
    CallbackAcceptedResponse,
    CursorPageMeta,
    IngestPolicy,
    LiveChannelCreateRequest,
    LiveChannelPageResponse,
    LiveChannelResponse,
    PlaybackTokenRequest,
    StopMode,
    StreamStopRequest,
)

MODULE5_TABLES = [
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
        "distribution_targets",
        "geofencing_policies",
    )
]


@pytest.fixture()
def module5_db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=MODULE5_TABLES)
    local_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = local_session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine, tables=MODULE5_TABLES)
        engine.dispose()


def user_with_role(role_name: str, user_id: int = 700) -> User:
    user = User(
        id=user_id,
        email=f"{role_name}-{user_id}@example.test",
        hashed_password="not-used",
        is_active=True,
        is_verified=True,
    )
    user.roles.append(Role(name=role_name))
    return user


def channel_response() -> LiveChannelResponse:
    now = datetime.now(UTC)
    return LiveChannelResponse(
        id=uuid4(),
        catalog_item_id=None,
        channel_code="GNTV-NEWS",
        name="GNTV News",
        slug="gntv-news",
        status=ChannelStatus.DRAFT,
        ingest_policy={"allowed_protocols": ["rtmp"], "redundancy": "primary_only"},
        transcode_profile="east-africa-abr-v1",
        recording_policy=RecordingPolicy.MANUAL,
        fallback_media_id=None,
        is_public=False,
        timezone="Africa/Nairobi",
        current_event_id=None,
        primary_ingest_host="rtmps://ingest.example.test/live",
        backup_ingest_host=None,
        created_at=now,
        updated_at=now,
        lock_version=1,
    )


class FakeStreamingService:
    def __init__(self) -> None:
        self.callback_raw_body: bytes | None = None

    def create_channel(self, payload: LiveChannelCreateRequest, *, actor_id: int) -> LiveChannelResponse:
        assert payload.channel_code == "GNTV-NEWS"
        assert actor_id == 700
        return channel_response()

    def list_channels(
        self, *, cursor: str | None, limit: int, status: ChannelStatus | None, public_only: bool
    ) -> LiveChannelPageResponse:
        assert cursor is None and limit == 50 and status is None and public_only
        return LiveChannelPageResponse(
            items=[channel_response()],
            page=CursorPageMeta(limit=limit, has_more=False),
        )

    def accept_apsara_callback(
        self,
        payload: Any,
        *,
        raw_body: bytes,
        signature: str,
        timestamp: str,
        nonce: str,
        key_id: str,
        signature_version: str,
    ) -> CallbackAcceptedResponse:
        assert payload.event_id == "evt-1"
        assert signature == "signed" and timestamp and nonce and key_id and signature_version == "v1"
        self.callback_raw_body = raw_body
        return CallbackAcceptedResponse(
            provider_event_id=payload.event_id,
            idempotency_outcome="accepted",
            correlation_id="corr-1",
        )


class FakeDistributionService:
    def create_target(
        self, payload: Any, *, actor_id: int, idempotency_key: str
    ) -> DistributionTargetResponse:
        assert payload.credential.get_secret_value() == "test-credential-1234"
        assert actor_id == 700 and idempotency_key == "request-1234"
        now = datetime.now(UTC)
        return DistributionTargetResponse(
            id=uuid4(),
            live_channel_id=payload.live_channel_id,
            name=payload.name,
            target_type=payload.target_type,
            status=DistributionTargetStatus.DRAFT,
            masked_endpoint="rtmps://relay.example.test/***",
            credentials_configured=True,
            public_config={},
            last_health_at=None,
            last_success_at=None,
            failure_code=None,
            failure_detail=None,
            created_at=now,
            updated_at=now,
            lock_version=1,
        )


def test_module5_metadata_contains_exact_foundation_tables_and_constraints() -> None:
    assert {table.name for table in MODULE5_TABLES} == {
        "live_channels",
        "live_events",
        "stream_keys",
        "streams",
        "recordings",
        "playback_sessions",
        "transcoding_jobs",
        "manifests",
        "thumbnails",
        "distribution_targets",
        "geofencing_policies",
    }
    assert "stream_key" not in Base.metadata.tables["live_channels"].columns
    assert "session_token" not in Base.metadata.tables["playback_sessions"].columns
    assert {"endpoint_ciphertext", "credential_ciphertext", "encrypted_data_key"} <= {
        column.name for column in Base.metadata.tables["distribution_targets"].columns
    }
    assert "ck_playback_exactly_one_target" in {
        constraint.name for constraint in Base.metadata.tables["playback_sessions"].constraints
    }
    assert "ck_geofence_exactly_one_target" in {
        constraint.name for constraint in Base.metadata.tables["geofencing_policies"].constraints
    }


def test_streaming_and_distribution_schema_validation() -> None:
    valid = LiveChannelCreateRequest(
        channel_code="GNTV-NEWS",
        name="GNTV News",
        slug="gntv-news",
        ingest_policy=IngestPolicy(allowed_protocols={StreamProtocol.RTMP}, redundancy="primary_backup"),
        transcode_profile="east-africa-abr-v1",
        timezone="Africa/Nairobi",
        backup_ingest_host="srt://backup.example.test:9000",
    )
    assert valid.timezone == "Africa/Nairobi"
    with pytest.raises(ValidationError):
        LiveChannelCreateRequest(
            channel_code="GNTV-NEWS",
            name="GNTV News",
            slug="gntv-news",
            ingest_policy=IngestPolicy(allowed_protocols={StreamProtocol.RTMP}, redundancy="primary_backup"),
            transcode_profile="east-africa-abr-v1",
        )
    with pytest.raises(ValidationError):
        StreamStopRequest(stream_id=uuid4(), expected_version=1, mode=StopMode.EMERGENCY)
    with pytest.raises(ValidationError):
        PlaybackTokenRequest(live_channel_id=uuid4(), recording_id=uuid4(), device_id="device-1")

    policy = GeoFencingPolicyUpsertRequest(
        live_channel_id=uuid4(),
        policy_mode=GeoPolicyMode.ALLOWLIST,
        allowed_countries=["ke", "so"],
        reason="Licensed territories",
    )
    assert policy.allowed_countries == ["KE", "SO"]
    with pytest.raises(ValidationError):
        GeoFencingPolicyUpsertRequest(
            live_channel_id=uuid4(),
            policy_mode=GeoPolicyMode.BLOCKLIST,
            blocked_countries=["XX"],
            reason="Invalid country",
        )
    with pytest.raises(ValidationError):
        GeoFencingPolicyUpsertRequest(
            live_channel_id=uuid4(),
            policy_mode=GeoPolicyMode.ALLOWLIST,
            allowed_countries=["KE"],
            blocked_countries=["KE"],
            reason="Overlap",
        )


def test_rbac_scope_matrix_is_fail_closed() -> None:
    assert scopes_for_roles(["admin"]) == ALL_SCOPES
    assert has_scope(roles=["producer"], required_scope="stream:control")
    assert has_scope(roles=["chief_editor"], required_scope="geofence:admin")
    assert not has_scope(roles=["viewer"], required_scope="stream:control")
    assert not has_scope(roles=["unknown-role"], required_scope="stream:read")


def test_repository_round_trip_and_database_target_constraint(module5_db: Session) -> None:
    repository = StreamingRepository(module5_db)
    distribution_repository = DistributionRepository(module5_db)
    actor_id = 1
    channel = repository.add(
        LiveChannel(
            channel_code="GNTV-NEWS",
            name="GNTV News",
            slug="gntv-news",
            ingest_policy={"allowed_protocols": ["rtmp"]},
            transcode_profile="east-africa-abr-v1",
            recording_policy=RecordingPolicy.MANUAL,
            timezone="Africa/Nairobi",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    key = repository.add(
        StreamKey(
            live_channel_id=channel.id,
            key_prefix="gntv_test",
            secret_hash="hash-only",
            allowed_protocols=["rtmp"],
            allowed_cidrs=[],
            created_by=actor_id,
        )
    )
    stream = repository.add(
        Stream(
            live_channel_id=channel.id,
            stream_key_id=key.id,
            protocol=StreamProtocol.RTMP,
            status=StreamStatus.REQUESTED,
            idempotency_key="stream-request-1",
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    module5_db.commit()

    assert repository.channel(channel.id) is channel
    assert repository.stream(stream.id) is stream
    assert list(repository.channels(limit=10)) == [channel]
    assert list(repository.streams(limit=10, channel_id=channel.id)) == [stream]

    target = distribution_repository.add(
        DistributionTarget(
            live_channel_id=channel.id,
            name="Primary relay",
            target_type=DistributionTargetType.RTMP_RELAY,
            endpoint_ciphertext=b"encrypted-endpoint",
            credential_ciphertext=b"encrypted-credential",
            kms_key_id="kms-test-key",
            encrypted_data_key=b"wrapped-data-key",
            public_config={},
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    policy = distribution_repository.add(
        GeoFencingPolicy(
            live_channel_id=channel.id,
            policy_mode=GeoPolicyMode.ALLOWLIST,
            allowed_countries=["KE", "SO"],
            blocked_countries=[],
            status=GeoPolicyStatus.ACTIVE,
            created_by=actor_id,
            updated_by=actor_id,
        )
    )
    module5_db.commit()
    assert list(distribution_repository.targets(limit=10, channel_id=channel.id)) == [target]
    assert distribution_repository.active_policy_for(live_channel_id=channel.id) is policy

    module5_db.add(
        PlaybackSession(
            device_id="device-1",
            token_jti_hash="token-hash",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
    )
    with pytest.raises(IntegrityError):
        module5_db.commit()
    module5_db.rollback()


def test_registered_contract_routes_delegate_and_enforce_rbac() -> None:
    streaming_service = FakeStreamingService()
    distribution_service = FakeDistributionService()
    app.dependency_overrides[get_streaming_service] = lambda: streaming_service
    app.dependency_overrides[get_distribution_service] = lambda: distribution_service
    app.dependency_overrides[get_current_user] = lambda: user_with_role("producer")
    client = TestClient(app)
    try:
        created = client.post(
            "/api/v1/streaming/channels",
            json={
                "channel_code": "GNTV-NEWS",
                "name": "GNTV News",
                "slug": "gntv-news",
                "ingest_policy": {"allowed_protocols": ["rtmp"]},
                "transcode_profile": "east-africa-abr-v1",
                "timezone": "Africa/Nairobi",
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["channel_code"] == "GNTV-NEWS"
        assert client.get("/api/v1/streaming/channels").status_code == 200

        channel_id = uuid4()
        target = client.post(
            "/api/v1/distribution/targets",
            headers={"Idempotency-Key": "request-1234"},
            json={
                "live_channel_id": str(channel_id),
                "name": "Primary relay",
                "target_type": "rtmp_relay",
                "endpoint": "rtmps://relay.example.test/live",
                "credential": "test-credential-1234",
            },
        )
        assert target.status_code == 201, target.text
        assert "credential" not in target.json()
        assert target.json()["masked_endpoint"].endswith("/***")

        app.dependency_overrides[get_current_user] = lambda: user_with_role("viewer", 701)
        forbidden = client.post(
            "/api/v1/streaming/channels",
            json={
                "channel_code": "GNTV-TWO",
                "name": "GNTV Two",
                "slug": "gntv-two",
                "ingest_policy": {"allowed_protocols": ["rtmp"]},
                "transcode_profile": "east-africa-abr-v1",
            },
        )
        assert forbidden.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_callback_forwards_raw_body_and_signature_metadata() -> None:
    service = FakeStreamingService()
    app.dependency_overrides[get_streaming_service] = lambda: service
    client = TestClient(app)
    try:
        response = client.post(
            "/api/v1/streaming/callbacks/apsara",
            headers={
                "X-Apsara-Signature": "signed",
                "X-Apsara-Timestamp": "2026-07-21T10:00:00Z",
                "X-Apsara-Nonce": "nonce-1",
                "X-Apsara-Key-Id": "key-1",
                "X-Apsara-Signature-Version": "v1",
            },
            json={
                "event_id": "evt-1",
                "event_type": "stream.started",
                "event_time": "2026-07-21T10:00:00Z",
                "application": "gntv-live",
                "channel_code": "GNTV-NEWS",
                "stream_identifier": "stream-1",
                "payload_version": "1",
            },
        )
        assert response.status_code == 202, response.text
        assert response.json()["idempotency_outcome"] == "accepted"
        assert service.callback_raw_body is not None and b'"event_id":"evt-1"' in service.callback_raw_body
    finally:
        app.dependency_overrides.clear()


def test_unbound_services_fail_closed() -> None:
    app.dependency_overrides.clear()
    response = TestClient(app).get("/api/v1/streaming/channels")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "streaming_service_unavailable"


def test_streaming_openapi_contract_is_complete_and_valid() -> None:
    schema = app.openapi()
    expected_paths = {
        "/api/v1/streaming/streams",
        "/api/v1/streaming/streams/start",
        "/api/v1/streaming/streams/stop",
        "/api/v1/streaming/channels",
        "/api/v1/streaming/channels/{channel_id}",
        "/api/v1/streaming/channels/{channel_id}/rotate-key",
        "/api/v1/streaming/callbacks/apsara",
        "/api/v1/streaming/playback/{target_id}",
        "/api/v1/streaming/playback-token",
        "/api/v1/streaming/recordings",
        "/api/v1/distribution/targets",
        "/api/v1/distribution/geofence",
    }
    assert expected_paths <= set(schema["paths"])
    assert "/api/v1/streams" not in schema["paths"]
    methods = {"get", "post", "put", "patch", "delete"}
    for path in expected_paths:
        for method, operation in schema["paths"][path].items():
            if method not in methods:
                continue
            assert operation["tags"] in (["Streaming Platform"], ["Streaming Distribution"])
            success_responses = [
                response for code, response in operation["responses"].items() if code.startswith("2")
            ]
            assert success_responses
            for response in success_responses:
                content = response.get("content", {})
                if content:
                    assert "schema" in content["application/json"]
            assert "503" in operation["responses"]

    callback_parameters = schema["paths"]["/api/v1/streaming/callbacks/apsara"]["post"]["parameters"]
    assert {parameter["name"] for parameter in callback_parameters} >= {
        "X-Apsara-Signature",
        "X-Apsara-Timestamp",
        "X-Apsara-Nonce",
        "X-Apsara-Key-Id",
        "X-Apsara-Signature-Version",
    }

    components = schema["components"]["schemas"]
    for name in (
        "ApiErrorResponse",
        "ApsaraCallbackEvent",
        "DistributionTargetCreateRequest",
        "GeoFencingPolicyUpsertRequest",
        "LiveChannelCreateRequest",
        "PlaybackTokenRequest",
        "StreamCreateRequest",
    ):
        assert name in components


def test_module5_migration_upgrade_and_downgrade_on_isolated_database() -> None:
    migration_path = Path(__file__).parents[1] / "alembic/versions/202607211200_cms_module_5_distribution.py"
    spec = importlib.util.spec_from_file_location("module5_migration_test", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "202607211200"
    assert migration.down_revision == "202607131200"

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        migration.upgrade()
        assert set(inspect(connection).get_table_names()) == {table.name for table in MODULE5_TABLES}
        migration.downgrade()
        assert inspect(connection).get_table_names() == []
    engine.dispose()


def test_distribution_enum_contracts_are_stable() -> None:
    assert set(DistributionTargetType) == {
        DistributionTargetType.ALIBABA_CDN,
        DistributionTargetType.RTMP_RELAY,
        DistributionTargetType.YOUTUBE_LIVE,
        DistributionTargetType.FACEBOOK_LIVE,
    }
    assert GeoPolicyStatus.ACTIVE.value == "active"
    assert CDNSyncStatus.PENDING.value == "pending"


def test_legacy_pipeline_orchestrator_syntax_gate() -> None:
    orchestrator = Path(__file__).parents[2] / "pipeline/pipeline_orchestrator.py"
    source = orchestrator.read_text(encoding="utf-8")
    compile(source, str(orchestrator), "exec")
    assert "class GNTVPipeline:" in source
    assert "pipeline = GNTVPipeline()" in source
    assert "GNTV DIGITAL, ALL EVERYWHEREPipeline" not in source
