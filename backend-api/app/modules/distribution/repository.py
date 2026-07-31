"""Persistence repository for distribution and geo-fencing records."""

from collections.abc import Sequence
from typing import TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.distribution.models import (
    DistributionTarget,
    DistributionTargetStatus,
    DistributionTargetType,
    GeoFencingPolicy,
    GeoPolicyStatus,
)

ModelT = TypeVar("ModelT")


class DistributionRepository:
    def __init__(self, db: Session):
        self.db = db

    def add(self, item: ModelT) -> ModelT:
        self.db.add(item)
        self.db.flush()
        return item

    def target(self, target_id: UUID) -> DistributionTarget | None:
        return self.db.get(DistributionTarget, target_id)

    def policy(self, policy_id: UUID) -> GeoFencingPolicy | None:
        return self.db.get(GeoFencingPolicy, policy_id)

    def targets(
        self,
        *,
        limit: int,
        channel_id: UUID | None = None,
        target_type: DistributionTargetType | None = None,
        status: DistributionTargetStatus | None = None,
    ) -> Sequence[DistributionTarget]:
        query = select(DistributionTarget)
        if channel_id is not None:
            query = query.where(DistributionTarget.live_channel_id == channel_id)
        if target_type is not None:
            query = query.where(DistributionTarget.target_type == target_type)
        if status is not None:
            query = query.where(DistributionTarget.status == status)
        return self.db.execute(
            query.order_by(DistributionTarget.created_at.desc(), DistributionTarget.id.desc()).limit(limit)
        ).scalars().all()

    def active_policy_for(
        self,
        *,
        content_id: UUID | None = None,
        catalog_item_id: UUID | None = None,
        live_channel_id: UUID | None = None,
    ) -> GeoFencingPolicy | None:
        query = select(GeoFencingPolicy).where(GeoFencingPolicy.status == GeoPolicyStatus.ACTIVE)
        if content_id is not None:
            query = query.where(GeoFencingPolicy.content_id == content_id)
        elif catalog_item_id is not None:
            query = query.where(GeoFencingPolicy.catalog_item_id == catalog_item_id)
        elif live_channel_id is not None:
            query = query.where(GeoFencingPolicy.live_channel_id == live_channel_id)
        else:
            return None
        return self.db.execute(query.order_by(GeoFencingPolicy.policy_version.desc())).scalars().first()


__all__ = ["DistributionRepository"]
