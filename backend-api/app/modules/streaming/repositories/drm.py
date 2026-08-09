"""DRM and Geo policy persistence repository for Sprint 6.4."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.streaming.models import DRMKey, DRMPolicy, GeoPolicy


class DRMRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add_drm_policy(self, policy: DRMPolicy) -> DRMPolicy:
        self.db.add(policy)
        self.db.flush()
        return policy

    def get_drm_policy(self, policy_id: UUID) -> DRMPolicy | None:
        return self.db.get(DRMPolicy, policy_id)

    def get_drm_policy_by_name(self, name: str) -> DRMPolicy | None:
        return self.db.execute(
            select(DRMPolicy).where(DRMPolicy.name == name)
        ).scalar_one_or_none()

    def add_geo_policy(self, policy: GeoPolicy) -> GeoPolicy:
        self.db.add(policy)
        self.db.flush()
        return policy

    def get_geo_policy(self, policy_id: UUID) -> GeoPolicy | None:
        return self.db.get(GeoPolicy, policy_id)

    def add_drm_key(self, key: DRMKey) -> DRMKey:
        self.db.add(key)
        self.db.flush()
        return key

    def get_drm_key(self, key_id: UUID) -> DRMKey | None:
        return self.db.execute(select(DRMKey).where(DRMKey.key_id == key_id)).scalar_one_or_none()

    def get_drm_key_for_channel(self, channel_id: UUID) -> DRMKey | None:
        return self.db.execute(
            select(DRMKey)
            .where(DRMKey.live_channel_id == channel_id)
            .order_by(DRMKey.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def get_drm_key_for_asset(self, asset_id: UUID) -> DRMKey | None:
        return self.db.execute(
            select(DRMKey)
            .where(DRMKey.asset_id == asset_id)
            .order_by(DRMKey.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
