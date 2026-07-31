"""Service contracts for distribution and geo-fencing."""

from typing import Protocol
from uuid import UUID

from app.modules.distribution.models import DistributionTargetStatus, DistributionTargetType
from app.modules.distribution.schemas import (
    DistributionTargetCreateRequest,
    DistributionTargetPageResponse,
    DistributionTargetResponse,
    GeoFencingPolicyResponse,
    GeoFencingPolicyUpsertRequest,
)


class DistributionServiceInterface(Protocol):
    def list_targets(
        self,
        *,
        cursor: str | None,
        limit: int,
        channel_id: UUID | None,
        target_type: DistributionTargetType | None,
        status: DistributionTargetStatus | None,
    ) -> DistributionTargetPageResponse: ...

    def create_target(
        self,
        payload: DistributionTargetCreateRequest,
        *,
        actor_id: int,
        idempotency_key: str,
    ) -> DistributionTargetResponse: ...

    def upsert_geofence(
        self,
        payload: GeoFencingPolicyUpsertRequest,
        *,
        actor_id: int,
        idempotency_key: str,
    ) -> GeoFencingPolicyResponse: ...


__all__ = ["DistributionServiceInterface"]
