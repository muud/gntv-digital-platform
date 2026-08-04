"""Contract-only FastAPI routes for the Module 5 streaming control plane."""

from typing import Annotated, Any, Never
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.dependencies.auth import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.modules.streaming.models import ChannelStatus, RecordingStatus, StreamProtocol, StreamStatus
from app.modules.streaming.permissions import require_streaming_scope
from app.modules.streaming.schemas import (
    ApiErrorResponse,
    ApsaraCallbackEvent,
    CallbackAcceptedResponse,
    LiveChannelCreateRequest,
    LiveChannelPageResponse,
    LiveChannelResponse,
    PlaybackAuthorizationResponse,
    PlaybackHeartbeatRequest,
    PlaybackHeartbeatResponse,
    PlaybackPathValidationResponse,
    PlaybackResolveQuery,
    PlaybackRevokeRequest,
    PlaybackRevokeResponse,
    PlaybackStopRequest,
    PlaybackStopResponse,
    PlaybackTokenRequest,
    PlaybackTokenResponse,
    RecordingPageResponse,
    StopMode,
    StreamAcceptedResponse,
    StreamCommandAcceptedResponse,
    StreamCreateRequest,
    StreamKeyCreatedResponse,
    StreamKeyRotateRequest,
    StreamPageResponse,
    StreamStartRequest,
    StreamStopRequest,
)
from app.modules.streaming.repositories import StreamingRepository
from app.modules.streaming.services import PlaybackService, StreamingServiceInterface
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/streaming", tags=["Streaming Platform"])

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ApiErrorResponse}
    for code in (400, 401, 403, 404, 409, 422, 429, 503)
}


def get_streaming_service() -> Never:
    """Fail closed until an approved Sprint implementation binds a service."""

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "streaming_service_unavailable",
            "message": "Streaming control-plane implementation is not enabled",
        },
    )


StreamingService = Annotated[StreamingServiceInterface, Depends(get_streaming_service)]


def get_playback_service(db: Annotated[Session, Depends(get_db)]) -> PlaybackService:
    return PlaybackService(
        StreamingRepository(db),
        signing_secret=settings.PLAYBACK_SIGNING_SECRET.get_secret_value(),
        token_ttl_seconds=settings.PLAYBACK_TOKEN_TTL_SECONDS,
        public_base_url=settings.PLAYBACK_PUBLIC_BASE_URL,
    )


PlaybackServiceDependency = Annotated[PlaybackService, Depends(get_playback_service)]
CreateUser = Annotated[User, Depends(require_streaming_scope("stream:create"))]
ReadUser = Annotated[User, Depends(require_streaming_scope("stream:read"))]
WriteUser = Annotated[User, Depends(require_streaming_scope("stream:write"))]
ControlUser = Annotated[User, Depends(require_streaming_scope("stream:control"))]
AdminUser = Annotated[User, Depends(require_streaming_scope("stream:admin"))]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


def trusted_country(request: Request) -> str | None:
    value = getattr(request.state, "country_code", None)
    return value if isinstance(value, str) else None


@router.post(
    "/streams",
    response_model=StreamAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERROR_RESPONSES,
)
def create_stream(
    payload: StreamCreateRequest,
    user: CreateUser,
    service: StreamingService,
    idempotency_key: IdempotencyKey,
) -> StreamAcceptedResponse:
    return service.create_stream(payload, actor_id=user.id, idempotency_key=idempotency_key)


@router.get("/streams", response_model=StreamPageResponse, responses=ERROR_RESPONSES)
def list_streams(
    user: ReadUser,
    service: StreamingService,
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    channel_id: UUID | None = None,
    stream_status: StreamStatus | None = Query(default=None, alias="status"),
    protocol: StreamProtocol | None = None,
) -> StreamPageResponse:
    del user
    return service.list_streams(
        cursor=cursor,
        limit=limit,
        channel_id=channel_id,
        status=stream_status,
        protocol=protocol,
    )


@router.post(
    "/streams/start",
    response_model=StreamCommandAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERROR_RESPONSES,
)
def start_stream(
    payload: StreamStartRequest,
    user: ControlUser,
    service: StreamingService,
    idempotency_key: IdempotencyKey,
) -> StreamCommandAcceptedResponse:
    return service.start_stream(payload, actor_id=user.id, idempotency_key=idempotency_key)


@router.post(
    "/streams/stop",
    response_model=StreamCommandAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERROR_RESPONSES,
)
def stop_stream(
    payload: StreamStopRequest,
    user: ControlUser,
    service: StreamingService,
    idempotency_key: IdempotencyKey,
) -> StreamCommandAcceptedResponse:
    if payload.mode == StopMode.EMERGENCY and "stream:emergency-stop" not in user.permission_names:
        from app.modules.streaming.permissions import has_scope

        if not has_scope(roles=user.role_names, required_scope="stream:emergency-stop"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "streaming_emergency_stop_forbidden"},
            )
    return service.stop_stream(payload, actor_id=user.id, idempotency_key=idempotency_key)


@router.post(
    "/channels",
    response_model=LiveChannelResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def create_channel(
    payload: LiveChannelCreateRequest,
    user: WriteUser,
    service: StreamingService,
) -> LiveChannelResponse:
    return service.create_channel(payload, actor_id=user.id)


@router.get("/channels", response_model=LiveChannelPageResponse, responses=ERROR_RESPONSES)
def list_channels(
    service: StreamingService,
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    channel_status: ChannelStatus | None = Query(default=None, alias="status"),
) -> LiveChannelPageResponse:
    return service.list_channels(cursor=cursor, limit=limit, status=channel_status, public_only=True)


@router.get("/channels/{channel_id}", response_model=LiveChannelResponse, responses=ERROR_RESPONSES)
def get_channel(channel_id: UUID, user: ReadUser, service: StreamingService) -> LiveChannelResponse:
    del user
    return service.get_channel(channel_id, operational=True)


@router.post(
    "/channels/{channel_id}/rotate-key",
    response_model=StreamKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def rotate_stream_key(
    channel_id: UUID,
    payload: StreamKeyRotateRequest,
    user: AdminUser,
    service: StreamingService,
    idempotency_key: IdempotencyKey,
) -> StreamKeyCreatedResponse:
    return service.rotate_stream_key(
        channel_id,
        payload,
        actor_id=user.id,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/callbacks/apsara",
    response_model=CallbackAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERROR_RESPONSES,
)
async def apsara_callback(
    request: Request,
    payload: ApsaraCallbackEvent,
    service: StreamingService,
    signature: Annotated[str, Header(alias="X-Apsara-Signature")],
    timestamp_header: Annotated[str, Header(alias="X-Apsara-Timestamp")],
    nonce: Annotated[str, Header(alias="X-Apsara-Nonce")],
    key_id: Annotated[str, Header(alias="X-Apsara-Key-Id")],
    signature_version: Annotated[str, Header(alias="X-Apsara-Signature-Version")],
) -> CallbackAcceptedResponse:
    return service.accept_apsara_callback(
        payload,
        raw_body=await request.body(),
        signature=signature,
        timestamp=timestamp_header,
        nonce=nonce,
        key_id=key_id,
        signature_version=signature_version,
    )


@router.get(
    "/playback/validate",
    response_model=PlaybackPathValidationResponse,
    responses=ERROR_RESPONSES,
)
def validate_playback_path(
    service: PlaybackServiceDependency,
    path: str = Query(min_length=1, max_length=1024),
    exp: str = Query(min_length=1, max_length=20),
    session_id: str = Query(min_length=1, max_length=36),
    pv: str = Query(min_length=1, max_length=10),
    sig: str = Query(min_length=1, max_length=128),
) -> PlaybackPathValidationResponse:
    return service.validate_path(
        path,
        expires_at=exp,
        session_id=session_id,
        policy_version=pv,
        signature=sig,
    )


@router.get("/playback/{target_id}", response_model=PlaybackAuthorizationResponse, responses=ERROR_RESPONSES)
def resolve_playback(
    target_id: UUID,
    request: Request,
    service: PlaybackServiceDependency,
    device_id: str = Query(min_length=1, max_length=160),
    protocol: str | None = Query(default=None, pattern="^(hls|dash)$"),
) -> PlaybackAuthorizationResponse:
    from app.modules.streaming.models import ManifestFormat

    query = PlaybackResolveQuery(
        device_id=device_id,
        protocol=ManifestFormat(protocol) if protocol is not None else None,
    )
    return service.resolve_playback(target_id, query, trusted_country_code=trusted_country(request))


@router.post(
    "/playback-token",
    response_model=PlaybackTokenResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def issue_playback_token(
    payload: PlaybackTokenRequest,
    request: Request,
    user: AuthenticatedUser,
    service: PlaybackServiceDependency,
) -> PlaybackTokenResponse:
    return service.issue_playback_token(
        payload,
        user_id=user.id,
        trusted_country_code=trusted_country(request),
    )


@router.post(
    "/playback/{session_id}/heartbeat",
    response_model=PlaybackHeartbeatResponse,
    responses=ERROR_RESPONSES,
)
def playback_heartbeat(
    session_id: UUID,
    payload: PlaybackHeartbeatRequest,
    service: PlaybackServiceDependency,
) -> PlaybackHeartbeatResponse:
    return service.heartbeat(session_id, payload)


@router.post(
    "/playback/{session_id}/stop",
    response_model=PlaybackStopResponse,
    responses=ERROR_RESPONSES,
)
def stop_playback_session(
    session_id: UUID,
    payload: PlaybackStopRequest,
    service: PlaybackServiceDependency,
) -> PlaybackStopResponse:
    return service.stop_session(session_id, payload)


@router.post(
    "/playback/{session_id}/revoke",
    response_model=PlaybackRevokeResponse,
    responses=ERROR_RESPONSES,
)
def revoke_playback_session(
    session_id: UUID,
    payload: PlaybackRevokeRequest,
    service: PlaybackServiceDependency,
) -> PlaybackRevokeResponse:
    return service.revoke_session(session_id, payload)


@router.get("/recordings", response_model=RecordingPageResponse, responses=ERROR_RESPONSES)
def list_recordings(
    service: StreamingService,
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    stream_id: UUID | None = None,
    channel_id: UUID | None = None,
    recording_status: RecordingStatus | None = Query(default=None, alias="status"),
) -> RecordingPageResponse:
    return service.list_recordings(
        cursor=cursor,
        limit=limit,
        stream_id=stream_id,
        channel_id=channel_id,
        status=recording_status,
        public_only=True,
    )


__all__ = ["get_playback_service", "get_streaming_service", "router"]
