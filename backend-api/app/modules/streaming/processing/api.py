"""Authenticated Processing Operations Center REST API."""

from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis import get_redis
from app.models.user import User
from app.modules.streaming.permissions import require_streaming_scope
from app.modules.streaming.processing.dispatch import ProcessingDispatcher, dispatcher
from app.modules.streaming.processing.repository import ProcessingRepository
from app.modules.streaming.processing.schemas import (
    ManifestPage,
    ManifestStatusResponse,
    ManifestValidationRequest,
    ManifestValidationResponse,
    MetricsPage,
    ProcessingErrorResponse,
    ProcessingJobCancelResponse,
    ProcessingJobCreateRequest,
    ProcessingJobPage,
    ProcessingJobResponse,
    QueueTelemetryResponse,
    ThumbnailPage,
    ThumbnailStatusResponse,
    WorkerStatusResponse,
)
from app.modules.streaming.processing.service import (
    ProcessingConflictError,
    ProcessingNotFoundError,
    ProcessingService,
    RedisReadCommands,
)


router = APIRouter(prefix="/api/v1/processing", tags=["Processing Operations Center"])
ReadUser = Annotated[User, Depends(require_streaming_scope("channel:read-operations"))]
ControlUser = Annotated[User, Depends(require_streaming_scope("stream:control"))]

AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": ProcessingErrorResponse,
        "description": "Missing or invalid bearer access token.",
    },
    status.HTTP_403_FORBIDDEN: {
        "model": ProcessingErrorResponse,
        "description": "Authenticated user lacks the required processing permission.",
    },
}
NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {
        "model": ProcessingErrorResponse,
        "description": "The requested processing resource does not exist.",
    }
}
CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {
        "model": ProcessingErrorResponse,
        "description": "The requested processing operation conflicts with current state.",
    }
}


def get_processing_dispatcher() -> ProcessingDispatcher:
    return dispatcher


def processing_service(
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    producer: ProcessingDispatcher = Depends(get_processing_dispatcher),
) -> ProcessingService:
    return ProcessingService(
        ProcessingRepository(db),
        cast(RedisReadCommands, redis),
        producer,
    )


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProcessingNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "processing_not_found", "message": str(exc)},
        )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "processing_conflict", "message": str(exc)},
    )


@router.post(
    "/jobs",
    response_model=ProcessingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={**AUTH_RESPONSES, **CONFLICT_RESPONSE},
)
async def create_job(
    payload: ProcessingJobCreateRequest,
    user: ControlUser,
    service: ProcessingService = Depends(processing_service),
) -> ProcessingJobResponse:
    del user
    try:
        return await service.create_job(payload)
    except ProcessingConflictError as exc:
        raise _http_error(exc) from exc


@router.get("/jobs", response_model=ProcessingJobPage, responses=AUTH_RESPONSES)
async def list_jobs(
    user: ReadUser,
    service: ProcessingService = Depends(processing_service),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ProcessingJobPage:
    del user
    return await service.list_jobs(limit=limit, offset=offset)


@router.get(
    "/jobs/{job_id}",
    response_model=ProcessingJobResponse,
    responses={**AUTH_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def get_job(
    job_id: UUID,
    user: ReadUser,
    service: ProcessingService = Depends(processing_service),
) -> ProcessingJobResponse:
    del user
    try:
        return await service.get_job(job_id)
    except ProcessingNotFoundError as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/jobs/{job_id}",
    response_model=ProcessingJobCancelResponse,
    responses={**AUTH_RESPONSES, **NOT_FOUND_RESPONSE, **CONFLICT_RESPONSE},
)
async def cancel_job(
    job_id: UUID,
    user: ControlUser,
    service: ProcessingService = Depends(processing_service),
) -> ProcessingJobCancelResponse:
    del user
    try:
        return await service.cancel_job(job_id)
    except (ProcessingConflictError, ProcessingNotFoundError) as exc:
        raise _http_error(exc) from exc


@router.get(
    "/workers",
    response_model=list[WorkerStatusResponse],
    responses=AUTH_RESPONSES,
)
async def workers(
    user: ReadUser,
    service: ProcessingService = Depends(processing_service),
) -> list[WorkerStatusResponse]:
    del user
    return await service.workers()


@router.get("/queues", response_model=QueueTelemetryResponse, responses=AUTH_RESPONSES)
async def queues(
    user: ReadUser,
    service: ProcessingService = Depends(processing_service),
) -> QueueTelemetryResponse:
    del user
    return await service.queues()


@router.get("/manifests", response_model=ManifestPage, responses=AUTH_RESPONSES)
def manifests(
    user: ReadUser,
    service: ProcessingService = Depends(processing_service),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ManifestPage:
    del user
    return service.manifests(limit=limit, offset=offset)


@router.post(
    "/manifests/validate",
    response_model=ManifestValidationResponse,
    responses=AUTH_RESPONSES,
)
def validate_manifest(
    payload: ManifestValidationRequest,
    user: ReadUser,
    service: ProcessingService = Depends(processing_service),
) -> ManifestValidationResponse:
    del user
    return service.validate_manifest(payload.manifest_url)


@router.get(
    "/manifests/{manifest_id}",
    response_model=ManifestStatusResponse,
    responses={**AUTH_RESPONSES, **NOT_FOUND_RESPONSE},
)
def manifest(
    manifest_id: UUID,
    user: ReadUser,
    service: ProcessingService = Depends(processing_service),
) -> ManifestStatusResponse:
    del user
    try:
        return service.manifest(manifest_id)
    except ProcessingNotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/thumbnails", response_model=ThumbnailPage, responses=AUTH_RESPONSES)
def thumbnails(
    user: ReadUser,
    service: ProcessingService = Depends(processing_service),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ThumbnailPage:
    del user
    return service.thumbnails(limit=limit, offset=offset)


@router.get(
    "/thumbnails/{thumbnail_id}",
    response_model=ThumbnailStatusResponse,
    responses={**AUTH_RESPONSES, **NOT_FOUND_RESPONSE},
)
def thumbnail(
    thumbnail_id: UUID,
    user: ReadUser,
    service: ProcessingService = Depends(processing_service),
) -> ThumbnailStatusResponse:
    del user
    try:
        return service.thumbnail(thumbnail_id)
    except ProcessingNotFoundError as exc:
        raise _http_error(exc) from exc


@router.get("/metrics", response_model=MetricsPage, responses=AUTH_RESPONSES)
async def metrics(
    user: ReadUser,
    service: ProcessingService = Depends(processing_service),
    job_id: UUID | None = None,
) -> MetricsPage:
    del user
    return await service.metrics(job_id)
