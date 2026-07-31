"""Contract-only FastAPI routes for distribution and geo-fencing."""

from typing import Annotated, Never
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.models.user import User
from app.modules.distribution.models import DistributionTargetStatus, DistributionTargetType
from app.modules.distribution.schemas import (
    DistributionTargetCreateRequest,
    DistributionTargetPageResponse,
    DistributionTargetResponse,
    GeoFencingPolicyResponse,
    GeoFencingPolicyUpsertRequest,
)
from app.modules.distribution.services import DistributionServiceInterface
from app.modules.streaming.api.router import ERROR_RESPONSES
from app.modules.streaming.permissions import require_streaming_scope

router = APIRouter(prefix="/api/v1/distribution", tags=["Streaming Distribution"])


def get_distribution_service() -> Never:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "distribution_service_unavailable",
            "message": "Distribution control-plane implementation is not enabled",
        },
    )


DistributionService = Annotated[DistributionServiceInterface, Depends(get_distribution_service)]
ReadUser = Annotated[User, Depends(require_streaming_scope("distribution:read"))]
WriteUser = Annotated[User, Depends(require_streaming_scope("distribution:write"))]
GeoAdminUser = Annotated[User, Depends(require_streaming_scope("geofence:admin"))]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


@router.get("/targets", response_model=DistributionTargetPageResponse, responses=ERROR_RESPONSES)
def list_targets(
    user: ReadUser,
    service: DistributionService,
    cursor: str | None = Query(default=None, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
    channel_id: UUID | None = None,
    target_type: DistributionTargetType | None = None,
    target_status: DistributionTargetStatus | None = Query(default=None, alias="status"),
) -> DistributionTargetPageResponse:
    del user
    return service.list_targets(
        cursor=cursor,
        limit=limit,
        channel_id=channel_id,
        target_type=target_type,
        status=target_status,
    )


@router.post(
    "/targets",
    response_model=DistributionTargetResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def create_target(
    payload: DistributionTargetCreateRequest,
    user: WriteUser,
    service: DistributionService,
    idempotency_key: IdempotencyKey,
) -> DistributionTargetResponse:
    return service.create_target(payload, actor_id=user.id, idempotency_key=idempotency_key)


@router.post(
    "/geofence",
    response_model=GeoFencingPolicyResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def upsert_geofence(
    payload: GeoFencingPolicyUpsertRequest,
    user: GeoAdminUser,
    service: DistributionService,
    idempotency_key: IdempotencyKey,
) -> GeoFencingPolicyResponse:
    return service.upsert_geofence(payload, actor_id=user.id, idempotency_key=idempotency_key)


__all__ = ["get_distribution_service", "router"]
