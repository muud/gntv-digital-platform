"""Sprint 6.1 playback signing, validation, and FastAPI binding tests."""

from collections.abc import Generator
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
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
    PlaybackSession,
    RecordingPolicy,
    Stream,
    StreamKey,
    StreamProtocol,
)
from app.modules.streaming.repositories import StreamingRepository
from app.modules.streaming.schemas import PlaybackResolveQuery, PlaybackTokenRequest
from app.modules.streaming.services import (
    PlaybackPathError,
    PlaybackService,
    generate_signed_playback_path,
    validate_signed_playback_path,
)

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
    )
]
SIGNING_SECRET = "test-only-playback-secret-at-least-32-characters"


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


@pytest.fixture()
def playable_channel(playback_db: Session) -> UUID:
    repository = StreamingRepository(playback_db)
    target_id = uuid4()
    channel = repository.add(
        LiveChannel(
            id=target_id,
            channel_code="SPRINT61",
            name="Sprint 6.1",
            slug="sprint-61",
            ingest_policy={"allowed_protocols": ["rtmp"]},
            transcode_profile="hls-only",
            recording_policy=RecordingPolicy.NEVER,
            is_public=True,
            timezone="UTC",
            created_by=1,
            updated_by=1,
        )
    )
    key = repository.add(
        StreamKey(
            live_channel_id=channel.id,
            key_prefix="s61_key",
            secret_hash="hash-only",
            allowed_protocols=["rtmp"],
            allowed_cidrs=[],
            created_by=1,
        )
    )
    stream = repository.add(
        Stream(
            live_channel_id=channel.id,
            stream_key_id=key.id,
            protocol=StreamProtocol.RTMP,
            idempotency_key="sprint61-stream",
            created_by=1,
            updated_by=1,
        )
    )
    repository.add(
        Manifest(
            stream_id=stream.id,
            format=ManifestFormat.HLS,
            kind=ManifestKind.LIVE,
            status=ManifestStatus.READY,
            oss_object_key="live/sprint61/index.m3u8",
            cdn_path="/live/sprint61/index.m3u8",
            generation=1,
            renditions=[],
        )
    )
    return target_id


@pytest.fixture()
def playback_service(playback_db: Session) -> PlaybackService:
    return PlaybackService(
        StreamingRepository(playback_db),
        signing_secret=SIGNING_SECRET,
        token_ttl_seconds=600,
        public_base_url="https://stream.example.test",
    )


def signed_parts(*, expires_at: int) -> tuple[str, UUID, dict[str, list[str]]]:
    session_id = uuid4()
    signed_path = generate_signed_playback_path(
        "/live/news/index.m3u8",
        secret=SIGNING_SECRET,
        expires_at_epoch=expires_at,
        session_id=session_id,
    )
    parsed = urlsplit(signed_path)
    return parsed.path, session_id, parse_qs(parsed.query)


def test_valid_signed_hls_path() -> None:
    expiry = 2_000_000_000
    path, session_id, query = signed_parts(expires_at=expiry)
    result = validate_signed_playback_path(
        path,
        expires_at=query["exp"][0],
        session_id=query["session_id"][0],
        policy_version=query["pv"][0],
        signature=query["sig"][0],
        secret=SIGNING_SECRET,
        now_epoch=expiry - 1,
    )
    assert result.session_id == session_id
    assert result.path == "/live/news/index.m3u8"
    assert result.expires_at == datetime.fromtimestamp(expiry, tz=UTC)


def test_expired_and_invalid_key_are_forbidden() -> None:
    expiry = 2_000_000_000
    path, _, query = signed_parts(expires_at=expiry)
    with pytest.raises(PlaybackPathError) as expired:
        validate_signed_playback_path(
            path,
            expires_at=query["exp"][0],
            session_id=query["session_id"][0],
            policy_version=query["pv"][0],
            signature=query["sig"][0],
            secret=SIGNING_SECRET,
            now_epoch=expiry,
        )
    assert expired.value.status_code == 403

    with pytest.raises(PlaybackPathError) as invalid:
        validate_signed_playback_path(
            path,
            expires_at=query["exp"][0],
            session_id=query["session_id"][0],
            policy_version=query["pv"][0],
            signature=query["sig"][0],
            secret="wrong-key",
            now_epoch=expiry - 1,
        )
    assert invalid.value.status_code == 403


def test_malformed_tokens_and_paths_are_controlled() -> None:
    with pytest.raises(PlaybackPathError) as malformed:
        validate_signed_playback_path(
            "/live/news/index.m3u8",
            expires_at="not-an-epoch",
            session_id="not-a-uuid",
            policy_version="one",
            signature="not-a-signature",
            secret=SIGNING_SECRET,
        )
    assert malformed.value.status_code == 400

    with pytest.raises(PlaybackPathError) as unsupported:
        generate_signed_playback_path(
            "/vod/movie/manifest.mpd",
            secret=SIGNING_SECRET,
            expires_at_epoch=2_000_000_000,
            session_id=uuid4(),
        )
    assert unsupported.value.code == "unsupported_playback_type"


def test_playback_start_contract_and_no_generation_loop(
    playback_service: PlaybackService,
    playable_channel: UUID,
    playback_db: Session,
) -> None:
    app.dependency_overrides[get_playback_service] = lambda: playback_service
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.get(
            f"/api/v1/streaming/playback/{playable_channel}",
            params={"device_id": "web-test", "protocol": "hls"},
        )
        assert response.status_code == 200, response.text
        assert response.history == []
        body = response.json()
        assert body["content_id"] == str(playable_channel)
        assert body["manifest_type"] == "hls"
        assert body["playback_mode"] == "live"
        assert datetime.fromisoformat(body["expires_at"]) > datetime.now(UTC)
        assert "token_expires_at" not in body
        assert body["playback_url"].startswith(
            "https://stream.example.test/live/sprint61/index.m3u8?"
        )
        assert playback_db.scalar(select(func.count()).select_from(PlaybackSession)) == 1
    finally:
        app.dependency_overrides.clear()


def test_invalid_playback_inputs_never_return_500(
    playback_service: PlaybackService,
    playable_channel: UUID,
) -> None:
    app.dependency_overrides[get_playback_service] = lambda: playback_service
    try:
        client = TestClient(app)
        responses = (
            client.get(
                f"/api/v1/streaming/playback/{playable_channel}",
                params={"device_id": "web-test", "protocol": "dash"},
            ),
            client.get(
                f"/api/v1/streaming/playback/{uuid4()}",
                params={"device_id": "web-test", "protocol": "hls"},
            ),
            client.get(
                "/api/v1/streaming/playback/not-a-uuid",
                params={"device_id": "web-test"},
            ),
        )
        assert [response.status_code for response in responses] == [400, 404, 422]
        assert all(response.status_code < 500 for response in responses)
    finally:
        app.dependency_overrides.clear()


def test_validation_endpoint_returns_controlled_4xx(playback_service: PlaybackService) -> None:
    expiry = 2_000_000_000
    path, _, query = signed_parts(expires_at=expiry)
    app.dependency_overrides[get_playback_service] = lambda: playback_service
    try:
        client = TestClient(app)
        common = {
            "path": path,
            "exp": query["exp"][0],
            "session_id": query["session_id"][0],
            "pv": query["pv"][0],
        }
        valid = client.get(
            "/api/v1/streaming/playback/validate",
            params={**common, "sig": query["sig"][0]},
        )
        assert valid.status_code == 200

        invalid = client.get(
            "/api/v1/streaming/playback/validate",
            params={**common, "sig": "0" * 64},
        )
        assert invalid.status_code == 403

        malformed = client.get(
            "/api/v1/streaming/playback/validate",
            params={**common, "exp": "bad", "sig": "x" * 64},
        )
        assert malformed.status_code == 400

        expired_path, _, expired_query = signed_parts(expires_at=1)
        expired = client.get(
            "/api/v1/streaming/playback/validate",
            params={
                "path": expired_path,
                "exp": expired_query["exp"][0],
                "session_id": expired_query["session_id"][0],
                "pv": expired_query["pv"][0],
                "sig": expired_query["sig"][0],
            },
        )
        assert expired.status_code == 403
        assert all(response.status_code < 500 for response in (invalid, malformed, expired))
    finally:
        app.dependency_overrides.clear()


def test_resolve_query_rejects_non_hls_in_service(
    playback_service: PlaybackService,
    playable_channel: UUID,
) -> None:
    with pytest.raises(Exception) as error:
        playback_service.resolve_playback(
            playable_channel,
            PlaybackResolveQuery(device_id="tv", protocol=ManifestFormat.DASH),
            trusted_country_code=None,
        )
    assert getattr(error.value, "status_code", None) == 400


def test_existing_playback_token_contract_is_bound(
    playback_service: PlaybackService,
    playable_channel: UUID,
    playback_db: Session,
) -> None:
    catalog_item_id = uuid4()
    channel = playback_db.get(LiveChannel, playable_channel)
    assert channel is not None
    channel.catalog_item_id = catalog_item_id
    playback_db.flush()
    response = playback_service.issue_playback_token(
        PlaybackTokenRequest(catalog_item_id=catalog_item_id, device_id="mobile-test"),
        user_id=42,
        trusted_country_code="KE",
    )
    assert response.protocol == ManifestFormat.HLS
    assert response.signed_url.startswith("https://stream.example.test/live/sprint61/index.m3u8?")
    assert response.token


def test_playback_openapi_exposes_public_expiry_field() -> None:
    schema = app.openapi()
    response_schema = schema["components"]["schemas"]["PlaybackAuthorizationResponse"]
    properties = response_schema["properties"]
    assert "expires_at" in properties
    assert properties["expires_at"]["format"] == "date-time"
    assert "expires_at" in response_schema["required"]
    assert "token_expires_at" not in properties
