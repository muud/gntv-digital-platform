"""SSAI and FAST monetization domain models for Module 7 Sprint 7.2."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


def enum_type(enum: type[StrEnum], name: str) -> Enum:
    return Enum(enum, name=name, values_callable=lambda values: [item.value for item in values])


class AdCampaignStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class AdCreativeType(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"


class AdBreakType(StrEnum):
    PREROLL = "preroll"
    MIDROLL = "midroll"
    POSTROLL = "postroll"


class AdImpressionEventType(StrEnum):
    IMPRESSION = "impression"
    START = "start"
    FIRST_QUARTILE = "firstQuartile"
    MIDPOINT = "midpoint"
    THIRD_QUARTILE = "thirdQuartile"
    COMPLETE = "complete"
    ERROR = "error"


AdEventType = AdImpressionEventType


class TrackingEventStatus(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class AdCampaign(Base, TimestampMixin):
    __tablename__ = "ad_campaigns"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[AdCampaignStatus] = mapped_column(
        enum_type(AdCampaignStatus, "gntv_ad_campaign_status"),
        default=AdCampaignStatus.ACTIVE,
        nullable=False,
    )
    vast_tag_url: Mapped[str | None] = mapped_column(String(1024))
    vmap_tag_url: Mapped[str | None] = mapped_column(String(1024))
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("end_at IS NULL OR start_at IS NULL OR end_at >= start_at", name="ck_ad_campaign_time_order"),
        Index("idx_ad_campaigns_owner_status", "owner_user_id", "status"),
    )


class AdCreative(Base, TimestampMixin):
    __tablename__ = "ad_creatives"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("ad_campaigns.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    creative_type: Mapped[AdCreativeType] = mapped_column(
        enum_type(AdCreativeType, "gntv_ad_creative_type"),
        default=AdCreativeType.VIDEO,
        nullable=False,
    )
    media_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), default="video/mp2t", nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    tracking_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("duration_seconds > 0", name="ck_ad_creatives_duration"),
        Index("idx_ad_creatives_campaign", "campaign_id"),
    )


class AdBreak(Base, TimestampMixin):
    __tablename__ = "ad_breaks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("ad_campaigns.id", ondelete="SET NULL"))
    target_id: Mapped[str] = mapped_column(String(160), nullable=False)
    break_type: Mapped[AdBreakType] = mapped_column(
        enum_type(AdBreakType, "gntv_ad_break_type"),
        default=AdBreakType.MIDROLL,
        nullable=False,
    )
    time_offset_seconds: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    scte35_event_id: Mapped[str | None] = mapped_column(String(120))
    scte35_cue: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("time_offset_seconds >= 0", name="ck_ad_break_offset"),
        CheckConstraint("duration_seconds > 0", name="ck_ad_break_duration"),
        Index("idx_ad_breaks_target_offset", "target_id", "time_offset_seconds"),
        Index("idx_ad_breaks_campaign", "campaign_id"),
    )


class AdImpression(Base):
    __tablename__ = "ad_impressions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    campaign_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("ad_campaigns.id", ondelete="SET NULL"))
    creative_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("ad_creatives.id", ondelete="SET NULL"))
    break_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("ad_breaks.id", ondelete="SET NULL"))
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_type: Mapped[AdImpressionEventType] = mapped_column(
        enum_type(AdImpressionEventType, "gntv_ad_impression_event_type"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_ad_impressions_idempotency"),
        Index("idx_ad_impressions_campaign_event", "campaign_id", "event_type"),
        Index("idx_ad_impressions_session", "session_id"),
    )


class AdTrackingEvent(Base):
    __tablename__ = "ad_tracking_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    impression_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("ad_impressions.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[AdImpressionEventType] = mapped_column(
        enum_type(AdImpressionEventType, "gntv_ad_tracking_event_type"),
        nullable=False,
    )
    tracking_url: Mapped[str | None] = mapped_column(String(2048))
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[TrackingEventStatus] = mapped_column(
        enum_type(TrackingEventStatus, "gntv_ad_tracking_event_status"),
        default=TrackingEventStatus.ACCEPTED,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        Index("idx_ad_tracking_events_impression", "impression_id"),
        Index("idx_ad_tracking_events_type_status", "event_type", "status"),
    )
