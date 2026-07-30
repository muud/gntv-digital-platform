"""Trusted gateway API for RTMP/SRT ingest control-plane operations."""

import secrets
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.modules.streaming.ingest.contracts import (
    EncoderRegistrationRequest,
    EncoderRegistrationResponse,
    IngestAdmissionResponse,
    IngestHealthResponse,
    IngestHeartbeatRequest,
    IngestSessionResponse,
    IngestStateEventRequest,
    RTMPAdmissionRequest,
    SRTAdmissionRequest,
)
from app.modules.streaming.ingest.coordination import RedisCommands, RedisIngestCoordination
from app.modules.streaming.ingest.dispatch import IngestDispatcherInterface, dispatcher
from app.modules.streaming.ingest.errors import IngestError
from app.modules.streaming.ingest.services import (
    EncoderRegistrationService,
    RTMPIngestService,
    SRTIngestService,
)
from app.modules.streaming.repositories import StreamingRepository

router = APIRouter(prefix="/api/v1/streaming/ingest", tags=["Streaming Ingest"])
GatewayToken = Annotated[str, Header(alias="X-GNTV-Gateway-Token", min_length=24, max_length=512)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


def require_gateway(token: GatewayToken) -> None:
    if not secrets.compare_digest(token, settings.INGEST_GATEWAY_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_ingest_gateway", "message": "Gateway authentication failed"},
        )


def get_ingest_dispatcher() -> IngestDispatcherInterface:
    return dispatcher


def coordination(redis: Redis = Depends(get_redis)) -> RedisIngestCoordination:
    return RedisIngestCoordination(cast(RedisCommands, redis))


def rtmp_service(
    db: Session = Depends(get_db),
    store: RedisIngestCoordination = Depends(coordination),
    producer: IngestDispatcherInterface = Depends(get_ingest_dispatcher),
) -> RTMPIngestService:
    return RTMPIngestService(db, store, producer)


def srt_service(
    db: Session = Depends(get_db),
    store: RedisIngestCoordination = Depends(coordination),
    producer: IngestDispatcherInterface = Depends(get_ingest_dispatcher),
) -> SRTIngestService:
    return SRTIngestService(db, store, producer)


def registration_service(
    store: RedisIngestCoordination = Depends(coordination),
) -> EncoderRegistrationService:
    return EncoderRegistrationService(store)


def as_http_error(error: IngestError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    )


@router.post(
    "/encoders/register",
    response_model=EncoderRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gateway)],
)
async def register_encoder(
    payload: EncoderRegistrationRequest,
    service: EncoderRegistrationService = Depends(registration_service),
) -> EncoderRegistrationResponse:
    try:
        return await service.register(payload)
    except IngestError as error:
        raise as_http_error(error) from error


@router.post(
    "/rtmp/admit",
    response_model=IngestAdmissionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gateway)],
)
async def admit_rtmp(
    payload: RTMPAdmissionRequest,
    idempotency_key: IdempotencyKey,
    service: RTMPIngestService = Depends(rtmp_service),
) -> IngestAdmissionResponse:
    try:
        return await service.admit(payload, idempotency_key=idempotency_key)
    except IngestError as error:
        raise as_http_error(error) from error


@router.post(
    "/srt/admit",
    response_model=IngestAdmissionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gateway)],
)
async def admit_srt(
    payload: SRTAdmissionRequest,
    idempotency_key: IdempotencyKey,
    service: SRTIngestService = Depends(srt_service),
) -> IngestAdmissionResponse:
    try:
        return await service.admit(payload, idempotency_key=idempotency_key)
    except IngestError as error:
        raise as_http_error(error) from error


@router.post(
    "/rtmp/sessions/{stream_id}/heartbeat",
    response_model=IngestSessionResponse,
    dependencies=[Depends(require_gateway)],
)
async def heartbeat_rtmp(
    stream_id: UUID,
    payload: IngestHeartbeatRequest,
    service: RTMPIngestService = Depends(rtmp_service),
) -> IngestSessionResponse:
    try:
        return await service.heartbeat(stream_id, payload)
    except IngestError as error:
        raise as_http_error(error) from error


@router.post(
    "/srt/sessions/{stream_id}/heartbeat",
    response_model=IngestSessionResponse,
    dependencies=[Depends(require_gateway)],
)
async def heartbeat_srt(
    stream_id: UUID,
    payload: IngestHeartbeatRequest,
    service: SRTIngestService = Depends(srt_service),
) -> IngestSessionResponse:
    try:
        return await service.heartbeat(stream_id, payload)
    except IngestError as error:
        raise as_http_error(error) from error


@router.post(
    "/rtmp/sessions/{stream_id}/events",
    response_model=IngestSessionResponse,
    dependencies=[Depends(require_gateway)],
)
async def event_rtmp(
    stream_id: UUID,
    payload: IngestStateEventRequest,
    service: RTMPIngestService = Depends(rtmp_service),
) -> IngestSessionResponse:
    try:
        return await service.apply_event(stream_id, payload)
    except IngestError as error:
        raise as_http_error(error) from error


@router.post(
    "/srt/sessions/{stream_id}/events",
    response_model=IngestSessionResponse,
    dependencies=[Depends(require_gateway)],
)
async def event_srt(
    stream_id: UUID,
    payload: IngestStateEventRequest,
    service: SRTIngestService = Depends(srt_service),
) -> IngestSessionResponse:
    try:
        return await service.apply_event(stream_id, payload)
    except IngestError as error:
        raise as_http_error(error) from error


@router.get(
    "/sessions/{stream_id}",
    response_model=IngestSessionResponse,
    dependencies=[Depends(require_gateway)],
)
def ingest_session(stream_id: UUID, db: Session = Depends(get_db)) -> IngestSessionResponse:
    stream = StreamingRepository(db).stream(stream_id)
    if stream is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ingest_session_not_found", "message": "Ingest session was not found"},
        )
    return IngestSessionResponse(
        stream_id=stream.id,
        status=stream.status,
        lock_version=stream.lock_version,
        last_heartbeat_at=stream.last_heartbeat_at,
    )


@router.get("/health/live", response_model=IngestHealthResponse)
def ingest_liveness() -> IngestHealthResponse:
    return IngestHealthResponse(
        status="ok",
        database="not_checked",
        redis="not_checked",
        dispatcher="not_checked",
    )


@router.get(
    "/health/ready",
    response_model=IngestHealthResponse,
    responses={503: {"model": IngestHealthResponse}},
)
async def ingest_readiness(
    response: Response,
    db: Session = Depends(get_db),
    store: RedisIngestCoordination = Depends(coordination),
    producer: IngestDispatcherInterface = Depends(get_ingest_dispatcher),
) -> IngestHealthResponse:
    database_status: Literal["connected", "unavailable", "not_checked"] = "connected"
    redis_status: Literal["connected", "unavailable", "not_checked"] = "connected"
    dispatcher_status: Literal["configured", "unavailable", "not_checked"] = "configured"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database_status = "unavailable"
    try:
        if not await store.ping():
            redis_status = "unavailable"
    except Exception:
        redis_status = "unavailable"
    if not producer.configured():
        dispatcher_status = "unavailable"
    healthy = all(
        value not in {"unavailable"}
        for value in (database_status, redis_status, dispatcher_status)
    )
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return IngestHealthResponse(
        status="ok" if healthy else "degraded",
        database=database_status,
        redis=redis_status,
        dispatcher=dispatcher_status,
    )


__all__ = [
    "get_ingest_dispatcher",
    "require_gateway",
    "router",
]
