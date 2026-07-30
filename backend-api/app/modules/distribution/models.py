"""SQLAlchemy models for distribution targets and geo-fencing policy."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    LargeBinary,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.streaming.models.domain import TimestampVersionMixin, enum_type


class DistributionTargetType(StrEnum):
    ALIBABA_CDN = "alibaba_cdn"
    RTMP_RELAY = "rtmp_relay"
    YOUTUBE_LIVE = "youtube_live"
    FACEBOOK_LIVE = "facebook_live"


class DistributionTargetStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"
    DEGRADED = "degraded"
    FAILED = "failed"


class GeoPolicyMode(StrEnum):
    ALLOWLIST = "allowlist"
    BLOCKLIST = "blocklist"
    GLOBAL = "global"


class GeoPolicyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"


class CDNSyncStatus(StrEnum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"


class DistributionTarget(Base, TimestampVersionMixin):
    __tablename__ = "distribution_targets"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    live_channel_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("live_channels.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    target_type: Mapped[DistributionTargetType] = mapped_column(
        enum_type(DistributionTargetType, "gntv_distribution_target_type"), nullable=False
    )
    status: Mapped[DistributionTargetStatus] = mapped_column(
        enum_type(DistributionTargetStatus, "gntv_distribution_target_status"),
        default=DistributionTargetStatus.DRAFT,
        nullable=False,
    )
    endpoint_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    credential_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    kms_key_id: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_data_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    public_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_detail: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    __table_args__ = (
        UniqueConstraint("live_channel_id", "name", name="uq_distribution_target_channel_name"),
        Index("idx_distribution_target_channel_status", "live_channel_id", "status"),
        Index("idx_distribution_target_type_status", "target_type", "status"),
    )


class GeoFencingPolicy(Base, TimestampVersionMixin):
    __tablename__ = "geofencing_policies"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    content_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("cms_content.id", ondelete="RESTRICT"))
    catalog_item_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("catalog_items.id", ondelete="RESTRICT")
    )
    live_channel_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("live_channels.id", ondelete="RESTRICT")
    )
    policy_mode: Mapped[GeoPolicyMode] = mapped_column(
        enum_type(GeoPolicyMode, "gntv_geo_policy_mode"), nullable=False
    )
    allowed_countries: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    blocked_countries: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[GeoPolicyStatus] = mapped_column(
        enum_type(GeoPolicyStatus, "gntv_geo_policy_status"),
        default=GeoPolicyStatus.DRAFT,
        nullable=False,
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    policy_version: Mapped[int] = mapped_column(default=1, nullable=False)
    cdn_sync_status: Mapped[CDNSyncStatus] = mapped_column(
        enum_type(CDNSyncStatus, "gntv_cdn_sync_status"),
        default=CDNSyncStatus.PENDING,
        nullable=False,
    )
    cdn_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN content_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN catalog_item_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN live_channel_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_geofence_exactly_one_target",
        ),
        CheckConstraint("ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at", name="ck_geofence_time_order"),
        CheckConstraint("policy_version > 0", name="ck_geofence_policy_version"),
        Index("idx_geofence_content_status", "content_id", "status"),
        Index("idx_geofence_catalog_status", "catalog_item_id", "status"),
        Index("idx_geofence_channel_status", "live_channel_id", "status"),
        Index("idx_geofence_sync", "cdn_sync_status", "updated_at"),
    )


__all__ = [
    "CDNSyncStatus",
    "DistributionTarget",
    "DistributionTargetStatus",
    "DistributionTargetType",
    "GeoFencingPolicy",
    "GeoPolicyMode",
    "GeoPolicyStatus",
]
