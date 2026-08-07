"""Contract-only FastAPI routes for the Module 5 streaming control plane."""

from typing import Annotated, Any, Never, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import redis_manager
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.streaming.models import ChannelStatus, RecordingStatus, StreamProtocol, StreamStatus
from app.modules.streaming.permissions import require_streaming_scope
from app.modules.streaming.repositories import DRMRepository, DVRRepository, QoERepository, StreamingRepository
from app.modules.streaming.schemas import (
    ApiErrorResponse,
    ApsaraCallbackEvent,
    CallbackAcceptedResponse,
    DRMTokenRequest,
    DRMTokenResponse,
    DVRSegmentIngestResponse,
    GeoCheckResponse,
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
    QoEAggregateQueryResponse,
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
    TelemetryBatchRequest,
    TelemetryBatchResponse,
)
from app.modules.streaming.services import (
    DRMService,
    DVRService,
    GeoFencingService,
    HLS_MEDIA_TYPE,
    InMemoryDVRTimelineStore,
    PlaybackService,
    QoEService,
    RedisDVRTimelineStore,
    StreamingServiceInterface,
)

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


def get_geo_service() -> GeoFencingService:
    return GeoFencingService()


def get_drm_service(db: Annotated[Session, Depends(get_db)]) -> DRMService:
    return DRMService(DRMRepository(db), GeoFencingService())


GeoServiceDependency = Annotated[GeoFencingService, Depends(get_geo_service)]
DRMServiceDependency = Annotated[DRMService, Depends(get_drm_service)]


def get_qoe_service(db: Annotated[Session, Depends(get_db)]) -> QoEService:
    return QoEService(QoERepository(db))


QoEServiceDependency = Annotated[QoEService, Depends(get_qoe_service)]

CreateUser = Annotated[User, Depends(require_streaming_scope("stream:create"))]
ReadUser = Annotated[User, Depends(require_streaming_scope("stream:read"))]
WriteUser = Annotated[User, Depends(require_streaming_scope("stream:write"))]
ControlUser = Annotated[User, Depends(require_streaming_scope("stream:control"))]
AdminUser = Annotated[User, Depends(require_streaming_scope("stream:admin"))]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]

fallback_dvr_timeline = InMemoryDVRTimelineStore()


def trusted_country(request: Request) -> str | None:
    value = getattr(request.state, "country_code", None)
    return value if isinstance(value, str) else None


def get_dvr_timeline_store() -> RedisDVRTimelineStore | InMemoryDVRTimelineStore:
    try:
        client: Redis = redis_manager.get_client()
    except RuntimeError:
        return fallback_dvr_timeline
    return RedisDVRTimelineStore(client)


def get_dvr_service(
    db: Annotated[Session, Depends(get_db)],
    timeline_store: Annotated[
        RedisDVRTimelineStore | InMemoryDVRTimelineStore,
        Depends(get_dvr_timeline_store),
    ],
) -> DVRService:
    return DVRService(DVRRepository(db), timeline_store)


DVRServiceDependency = Annotated[DVRService, Depends(get_dvr_service)]


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
    response_model=CallbackAcceptedResponse | DVRSegmentIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERROR_RESPONSES,
)
async def apsara_callback(
    request: Request,
    payload: ApsaraCallbackEvent,
    dvr_service: DVRServiceDependency,
    signature: Annotated[str | None, Header(alias="X-Apsara-Signature")] = None,
    timestamp_header: Annotated[str | None, Header(alias="X-Apsara-Timestamp")] = None,
    nonce: Annotated[str | None, Header(alias="X-Apsara-Nonce")] = None,
    key_id: Annotated[str | None, Header(alias="X-Apsara-Key-Id")] = None,
    signature_version: Annotated[str | None, Header(alias="X-Apsara-Signature-Version")] = None,
) -> CallbackAcceptedResponse | DVRSegmentIngestResponse:
    service_override = request.app.dependency_overrides.get(get_streaming_service)
    if service_override is not None and all(
        value is not None for value in (signature, timestamp_header, nonce, key_id, signature_version)
    ):
        legacy_service = service_override()
        return cast(
            CallbackAcceptedResponse,
            legacy_service.accept_apsara_callback(
                payload,
                raw_body=await request.body(),
                signature=signature or "",
                timestamp=timestamp_header or "",
                nonce=nonce or "",
                key_id=key_id or "",
                signature_version=signature_version or "",
            ),
        )
    return await dvr_service.ingest_apsara_segment(payload)


@router.get(
    "/live/{channel_id}/dvr.m3u8",
    response_class=Response,
    responses=ERROR_RESPONSES,
)
def live_dvr_manifest(
    channel_id: UUID,
    service: DVRServiceDependency,
    time_shift: int = Query(default=0, ge=0, alias="time_shift"),
    rendition: str = Query(default="source", min_length=1, max_length=80),
) -> Response:
    return Response(
        content=service.live_dvr_manifest(
            channel_id,
            time_shift_seconds=time_shift,
            rendition=rendition,
        ),
        media_type=HLS_MEDIA_TYPE,
    )


@router.get(
    "/catchup/{live_event_id}/playlist.m3u8",
    response_class=Response,
    responses=ERROR_RESPONSES,
)
def catchup_playlist(
    live_event_id: UUID,
    service: DVRServiceDependency,
    rendition: str = Query(default="source", min_length=1, max_length=80),
) -> Response:
    return Response(
        content=service.catchup_playlist(live_event_id, rendition=rendition),
        media_type=HLS_MEDIA_TYPE,
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


@router.post(
    "/playback/{target_id}/drm-token",
    response_model=DRMTokenResponse,
    status_code=status.HTTP_200_OK,
    responses=ERROR_RESPONSES,
)
def issue_drm_token(
    target_id: UUID,
    payload: DRMTokenRequest,
    drm_service: DRMServiceDependency,
    user: AuthenticatedUser,
) -> DRMTokenResponse:
    token, license_url, expires_at = drm_service.issue_drm_token(
        target_id=target_id,
        user_id=user.id,
        device_id=payload.device_id,
        drm_system=payload.drm_system,
        session_id=payload.session_id,
    )
    return DRMTokenResponse(
        drm_token=token,
        license_server_url=license_url,
        expires_at=expires_at,
    )


@router.get("/drm/fairplay/cert", response_class=Response, responses=ERROR_RESPONSES)
def get_fairplay_cert(drm_service: DRMServiceDependency) -> Response:
    cert_bytes = drm_service.get_fairplay_cert()
    return Response(content=cert_bytes, media_type="application/octet-stream")


@router.post("/drm/{drm_system}/license", response_class=Response, responses=ERROR_RESPONSES)
async def process_drm_license(
    drm_system: str,
    request: Request,
    drm_service: DRMServiceDependency,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "missing_drm_authorization_header"},
        )
    token = authorization.split("Bearer ", 1)[1]
    token_payload = drm_service.validate_drm_token(token)

    challenge_bytes = await request.body()
    if not challenge_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "empty_license_challenge"},
        )

    license_bytes = drm_service.process_license_challenge(
        drm_system=drm_system,
        challenge_bytes=challenge_bytes,
        token_payload=token_payload,
    )
    return Response(content=license_bytes, media_type="application/octet-stream")


@router.get("/geo/check", response_model=GeoCheckResponse, responses=ERROR_RESPONSES)
def check_geo_status(
    request: Request,
    geo_service: GeoServiceDependency,
) -> GeoCheckResponse:
    client_ip = request.client.host if request.client else "127.0.0.1"
    country, is_vpn, is_proxy = geo_service.resolve_ip_metadata(client_ip, dict(request.headers))
    return GeoCheckResponse(
        allowed=True,
        country_code=country,
        is_vpn=is_vpn,
        is_proxy=is_proxy,
    )


@router.post("/telemetry/batch", response_model=TelemetryBatchResponse, responses=ERROR_RESPONSES)
def ingest_telemetry_batch(
    request: Request,
    payload: TelemetryBatchRequest,
    qoe_service: QoEServiceDependency,
) -> TelemetryBatchResponse:
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent")
    return qoe_service.ingest_batch(
        request=payload,
        client_ip=client_ip,
        user_agent=user_agent,
    )


@router.get("/telemetry/metrics/summary", response_model=QoEAggregateQueryResponse, responses=ERROR_RESPONSES)
def get_qoe_metrics_summary(
    target_id: UUID,
    qoe_service: QoEServiceDependency,
    _: ReadUser,
) -> QoEAggregateQueryResponse:
    res = qoe_service.get_metrics_summary(target_id)
    return QoEAggregateQueryResponse(
        target_id=UUID(res["target_id"]),
        total_sessions=res["total_sessions"],
        p50_startup_latency_ms=res["p50_startup_latency_ms"],
        p95_startup_latency_ms=res["p95_startup_latency_ms"],
        avg_rebuffer_ratio=res["avg_rebuffer_ratio"],
        total_errors=res["total_errors"],
        status=res["status"],
    )


__all__ = [
    "get_drm_service",
    "get_geo_service",
    "get_playback_service",
    "get_qoe_service",
    "get_streaming_service",
    "router",
]
