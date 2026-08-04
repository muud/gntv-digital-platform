"""Sprint 6.1 unencrypted HLS playback and signed-path services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import hmac
from time import time
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from app.modules.streaming.models import (
    ManifestFormat,
    PlaybackSession,
    PlaybackSessionStatus,
    UserWatchHistory,
)
from app.modules.streaming.repositories import StreamingRepository
from app.modules.streaming.schemas import (
    PlaybackAuthorizationResponse,
    PlaybackHeartbeatRequest,
    PlaybackHeartbeatResponse,
    PlaybackMode,
    PlaybackPathValidationResponse,
    PlaybackResolveQuery,
    PlaybackRevokeRequest,
    PlaybackRevokeResponse,
    PlaybackStopRequest,
    PlaybackStopResponse,
    PlaybackTokenRequest,
    PlaybackTokenResponse,
)
from app.modules.streaming.services.redis_session_store import RedisSessionStore


class PlaybackPathError(ValueError):
    """A controlled client or authorization failure while validating a signed path."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ValidatedPlaybackPath:
    path: str
    expires_at: datetime
    session_id: UUID
    policy_version: int


def normalize_playback_path(path: str) -> str:
    """Accept one origin-relative manifest path and reject redirect/path confusion."""

    parsed = urlsplit(path)
    normalized = parsed.path
    if (
        not normalized.startswith("/")
        or normalized.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or "\\" in normalized
        or any(part in {"", ".", ".."} for part in normalized.split("/")[1:])
    ):
        raise PlaybackPathError(400, "malformed_playback_path", "Playback path is malformed")
    if not normalized.lower().endswith(".m3u8"):
        raise PlaybackPathError(400, "unsupported_playback_type", "Only unencrypted HLS is supported")
    return normalized


def _canonical_payload(path: str, expires_at_epoch: int, session_id: UUID, policy_version: int) -> str:
    query = urlencode(
        (("exp", str(expires_at_epoch)), ("session_id", str(session_id)), ("pv", str(policy_version)))
    )
    return f"{path}?{query}"


def generate_signed_playback_path(
    path: str,
    *,
    secret: str,
    expires_at_epoch: int,
    session_id: UUID,
    policy_version: int = 1,
) -> str:
    """Return a deterministic HMAC-SHA256 signed origin-relative HLS path."""

    normalized = normalize_playback_path(path)
    if not secret:
        raise ValueError("playback signing secret must not be empty")
    if expires_at_epoch <= 0 or policy_version < 1:
        raise ValueError("playback signing metadata is invalid")
    payload = _canonical_payload(normalized, expires_at_epoch, session_id, policy_version)
    signature = hmac.new(secret.encode(), payload.encode(), sha256).hexdigest()
    return f"{payload}&sig={signature}"


def validate_signed_playback_path(
    path: str,
    *,
    expires_at: str,
    session_id: str,
    policy_version: str,
    signature: str,
    secret: str,
    now_epoch: int | None = None,
) -> ValidatedPlaybackPath:
    """Validate shape, expiry, and signature without regenerating a token."""

    normalized = normalize_playback_path(path)
    try:
        expiry = int(expires_at)
        parsed_session_id = UUID(session_id)
        parsed_policy_version = int(policy_version)
    except (TypeError, ValueError) as exc:
        raise PlaybackPathError(400, "malformed_playback_token", "Playback token is malformed") from exc
    if expiry <= 0 or parsed_policy_version < 1 or len(signature) != 64:
        raise PlaybackPathError(400, "malformed_playback_token", "Playback token is malformed")
    try:
        int(signature, 16)
    except ValueError as exc:
        raise PlaybackPathError(400, "malformed_playback_token", "Playback token is malformed") from exc
    current_epoch = int(time()) if now_epoch is None else now_epoch
    if expiry <= current_epoch:
        raise PlaybackPathError(403, "playback_token_expired", "Playback token has expired")
    payload = _canonical_payload(normalized, expiry, parsed_session_id, parsed_policy_version)
    expected = hmac.new(secret.encode(), payload.encode(), sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise PlaybackPathError(403, "invalid_playback_signature", "Playback signature is invalid")
    return ValidatedPlaybackPath(
        path=normalized,
        expires_at=datetime.fromtimestamp(expiry, tz=UTC),
        session_id=parsed_session_id,
        policy_version=parsed_policy_version,
    )


class PlaybackService:
    """Bind the two pre-existing streaming playback operations for Sprint 6.1."""

    def __init__(
        self,
        repository: StreamingRepository,
        *,
        signing_secret: str,
        token_ttl_seconds: int,
        public_base_url: str,
        redis_store: RedisSessionStore | None = None,
    ) -> None:
        self.repository = repository
        self.signing_secret = signing_secret
        self.token_ttl_seconds = token_ttl_seconds
        base = urlsplit(public_base_url)
        if base.scheme not in {"http", "https"} or not base.netloc or base.query or base.fragment:
            raise ValueError("PLAYBACK_PUBLIC_BASE_URL must be an HTTP(S) origin")
        self.public_base_url = urlunsplit((base.scheme, base.netloc, base.path.rstrip("/"), "", ""))
        self.redis_store = redis_store or RedisSessionStore()

    @staticmethod
    def _require_hls(protocol: ManifestFormat | None) -> None:
        if protocol not in {None, ManifestFormat.HLS}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "unsupported_playback_type", "message": "Sprint 6.1 supports HLS only"},
            )

    def _source(self, target_id: UUID) -> tuple[str, PlaybackMode, dict[str, UUID | None]]:
        channel = self.repository.channel(target_id)
        if channel is not None and channel.is_public:
            manifest = self.repository.ready_hls_manifest_for_channel(target_id)
            if manifest is not None:
                return manifest.cdn_path, PlaybackMode.LIVE, {
                    "live_channel_id": target_id,
                    "recording_id": None,
                    "catalog_item_id": None,
                }
        recording = self.repository.recording(target_id)
        if recording is not None:
            manifest = self.repository.ready_hls_manifest_for_recording(target_id)
            if manifest is not None:
                return manifest.cdn_path, PlaybackMode.VOD, {
                    "live_channel_id": None,
                    "recording_id": target_id,
                    "catalog_item_id": None,
                }
        catalog_channel = self.repository.public_channel_for_catalog_item(target_id)
        if catalog_channel is not None:
            manifest = self.repository.ready_hls_manifest_for_channel(catalog_channel.id)
            if manifest is not None:
                return manifest.cdn_path, PlaybackMode.LIVE, {
                    "live_channel_id": None,
                    "recording_id": None,
                    "catalog_item_id": target_id,
                }
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "playback_content_not_found", "message": "Playable content was not found"},
        )

    def _create(
        self,
        target_id: UUID,
        *,
        device_id: str,
        user_id: int | None,
        protocol: ManifestFormat | None,
        trusted_country_code: str | None,
    ) -> tuple[PlaybackSession, str, PlaybackMode, str]:
        self._require_hls(protocol)
        path, mode, targets = self._source(target_id)
        normalized_path = normalize_playback_path(path)
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self.token_ttl_seconds)
        session_id = uuid4()
        jti = uuid4().hex
        session = PlaybackSession(
            id=session_id,
            user_id=user_id,
            device_id=device_id,
            token_jti_hash=sha256(jti.encode()).hexdigest(),
            country_code=trusted_country_code,
            expires_at=expires_at,
            policy_version=1,
            **targets,
        )
        self.repository.add_playback_session(session)

        if user_id is not None:
            evicted_id = self.redis_store.acquire_slot(user_id, session_id, limit=3)
            if evicted_id is not None:
                evicted_session = self.repository.get_playback_session(evicted_id)
                if evicted_session is not None:
                    evicted_session.status = PlaybackSessionStatus.REVOKED

        signed_path = generate_signed_playback_path(
            normalized_path,
            secret=self.signing_secret,
            expires_at_epoch=int(expires_at.timestamp()),
            session_id=session_id,
            policy_version=session.policy_version,
        )
        return session, signed_path, mode, jti

    def resolve_playback(
        self, target_id: UUID, query: PlaybackResolveQuery, *, trusted_country_code: str | None
    ) -> PlaybackAuthorizationResponse:
        session, signed_path, mode, _ = self._create(
            target_id,
            device_id=query.device_id,
            user_id=None,
            protocol=query.protocol,
            trusted_country_code=trusted_country_code,
        )
        return PlaybackAuthorizationResponse(
            playback_session_id=session.id,
            playback_url=f"{self.public_base_url}{signed_path}",
            expires_at=session.expires_at,
            content_id=target_id,
            playback_mode=mode,
            heartbeat_interval_seconds=30,
            policy_version=session.policy_version,
        )

    def issue_playback_token(
        self,
        payload: PlaybackTokenRequest,
        *,
        user_id: int,
        trusted_country_code: str | None,
    ) -> PlaybackTokenResponse:
        target_id = payload.live_channel_id or payload.recording_id or payload.catalog_item_id
        if target_id is None:  # Pydantic enforces this; retain a controlled boundary.
            raise HTTPException(status_code=400, detail={"code": "missing_playback_target"})
        session, signed_path, _, token = self._create(
            target_id,
            device_id=payload.device_id,
            user_id=user_id,
            protocol=payload.requested_protocol,
            trusted_country_code=trusted_country_code,
        )
        return PlaybackTokenResponse(
            playback_session_id=session.id,
            token=token,
            expires_at=session.expires_at,
            protocol=ManifestFormat.HLS,
            policy_version=session.policy_version,
            heartbeat_interval_seconds=30,
            signed_url=f"{self.public_base_url}{signed_path}",
        )

    def validate_path(
        self,
        path: str,
        *,
        expires_at: str,
        session_id: str,
        policy_version: str,
        signature: str,
    ) -> PlaybackPathValidationResponse:
        try:
            result = validate_signed_playback_path(
                path,
                expires_at=expires_at,
                session_id=session_id,
                policy_version=policy_version,
                signature=signature,
                secret=self.signing_secret,
            )
        except PlaybackPathError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        return PlaybackPathValidationResponse(
            path=result.path,
            expires_at=result.expires_at,
            playback_session_id=result.session_id,
            policy_version=result.policy_version,
        )

    def heartbeat(
        self, session_id: UUID, payload: PlaybackHeartbeatRequest
    ) -> PlaybackHeartbeatResponse:
        session = self.repository.get_playback_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "session_not_found", "message": "Playback session was not found"},
            )
        if session.status in {PlaybackSessionStatus.REVOKED, PlaybackSessionStatus.EXPIRED}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "session_evicted", "message": "Playback session has been terminated"},
            )

        now = datetime.now(UTC)
        session.last_seen_at = now
        session.position_ms = payload.position_ms
        session.status = payload.state

        if session.user_id is not None:
            self.redis_store.record_heartbeat(session.user_id, session.id)
            history = UserWatchHistory(
                user_id=session.user_id,
                playback_session_id=session.id,
                live_channel_id=session.live_channel_id,
                recording_id=session.recording_id,
                catalog_item_id=session.catalog_item_id,
                device_id=session.device_id,
                watch_duration_ms=payload.position_ms,
                max_position_ms=payload.position_ms,
                completion_ratio=min(1.0, payload.position_ms / 3600000.0) if payload.position_ms else 0.0,
            )
            self.repository.add_watch_history(history)

        return PlaybackHeartbeatResponse(
            session_id=session.id,
            status=session.status,
            next_heartbeat_seconds=30,
            position_ms=session.position_ms,
        )

    def stop_session(self, session_id: UUID, payload: PlaybackStopRequest) -> PlaybackStopResponse:
        session = self.repository.get_playback_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "session_not_found", "message": "Playback session was not found"},
            )
        session.status = PlaybackSessionStatus.ENDED
        session.position_ms = payload.position_ms
        if session.user_id is not None:
            self.redis_store.release_slot(session.user_id, session.id)
        return PlaybackStopResponse(
            session_id=session.id,
            status="ended",
            final_position_ms=session.position_ms,
        )

    def revoke_session(self, session_id: UUID, payload: PlaybackRevokeRequest) -> PlaybackRevokeResponse:
        session = self.repository.get_playback_session(session_id)
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "session_not_found", "message": "Playback session was not found"},
            )
        session.status = PlaybackSessionStatus.REVOKED
        if session.user_id is not None:
            self.redis_store.release_slot(session.user_id, session.id)
        return PlaybackRevokeResponse(
            session_id=session.id,
            status="revoked",
        )


__all__ = [
    "PlaybackPathError",
    "PlaybackService",
    "ValidatedPlaybackPath",
    "generate_signed_playback_path",
    "normalize_playback_path",
    "validate_signed_playback_path",
]
