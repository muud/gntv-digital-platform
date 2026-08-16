"""SQLAlchemy models for Global Multi-CDN & Edge Acceleration (Module 7 Sprint 7.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


def enum_type(enum: type[StrEnum], name: str) -> Enum:
    return Enum(enum, name=name, values_callable=lambda values: [item.value for item in values])


class CDNHealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class CDNProviderType(StrEnum):
    ALIBABA_DCDN = "alibaba_dcdn"
    FASTLY = "fastly"
    CLOUDFRONT = "cloudfront"
    GENERIC_CDN = "generic_cdn"


class CDNOriginType(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    BACKUP = "backup"


class CDNOrigin(Base):
    """Represents an origin server target configuration."""

    __tablename__ = "cdn_origins"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    origin_hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    origin_type: Mapped[CDNOriginType] = mapped_column(
        enum_type(CDNOriginType, "cdn_origin_type_enum"),
        nullable=False,
        default=CDNOriginType.PRIMARY,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    health_check_path: Mapped[str] = mapped_column(String(255), nullable=False, default="/health")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    endpoints: Mapped[list[CDNEndpoint]] = relationship(
        "CDNEndpoint", back_populates="origin", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_cdn_origins_active_type", "is_active", "origin_type"),
    )


class CDNEndpoint(Base):
    """Represents an edge CDN distribution endpoint target."""

    __tablename__ = "cdn_endpoints"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    origin_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("cdn_origins.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_type: Mapped[CDNProviderType] = mapped_column(
        enum_type(CDNProviderType, "cdn_provider_type_enum"),
        nullable=False,
        default=CDNProviderType.ALIBABA_DCDN,
    )
    edge_hostname: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    signing_key_ref: Mapped[str] = mapped_column(String(100), nullable=False, default="PLAYBACK_SIGNING_SECRET")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    health_status: Mapped[CDNHealthStatus] = mapped_column(
        enum_type(CDNHealthStatus, "cdn_health_status_enum"),
        nullable=False,
        default=CDNHealthStatus.HEALTHY,
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cache_policy_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    origin: Mapped[CDNOrigin] = relationship("CDNOrigin", back_populates="endpoints")
    health_checks: Mapped[list[CDNHealthCheck]] = relationship(
        "CDNHealthCheck", back_populates="endpoint", cascade="all, delete-orphan"
    )
    routing_events: Mapped[list[CDNRoutingEvent]] = relationship(
        "CDNRoutingEvent", back_populates="endpoint"
    )

    __table_args__ = (
        Index("ix_cdn_endpoints_routing", "is_enabled", "health_status", "priority"),
    )


class CDNHealthCheck(Base):
    """Historical record of health probes performed on CDN endpoints."""

    __tablename__ = "cdn_health_checks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    endpoint_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("cdn_endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[CDNHealthStatus] = mapped_column(
        enum_type(CDNHealthStatus, "cdn_health_check_status_enum"),
        nullable=False,
    )
    response_latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    endpoint: Mapped[CDNEndpoint] = relationship("CDNEndpoint", back_populates="health_checks")


class CDNRoutingEvent(Base):
    """Audit log of CDN routing selection and failover decisions."""

    __tablename__ = "cdn_routing_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    asset_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    endpoint_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("cdn_endpoints.id", ondelete="SET NULL"), nullable=True, index=True)
    routing_reason: Mapped[str] = mapped_column(String(100), nullable=False)
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    decision_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    endpoint: Mapped[CDNEndpoint | None] = relationship("CDNEndpoint", back_populates="routing_events")
