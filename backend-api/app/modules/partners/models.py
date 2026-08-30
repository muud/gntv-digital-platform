"""SQLAlchemy models for partner syndication and secure embeds."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


def enum_type(enum: type[StrEnum], name: str) -> Enum:
    return Enum(enum, name=name, values_callable=lambda values: [item.value for item in values])


class PartnerStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"


class PartnerDomainStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class PartnerEntitlementStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class PartnerContentType(StrEnum):
    VOD = "vod"
    LIVE_CHANNEL = "live_channel"


class PartnerCredentialStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class PartnerEmbedEventType(StrEnum):
    AUTHORIZE = "authorize"
    PLAYBACK_START = "playback_start"
    PLAYBACK_COMPLETE = "playback_complete"
    PLAYBACK_ERROR = "playback_error"


class Partner(Base):
    """B2B partner organization allowed to syndicate GNTV content."""

    __tablename__ = "partners"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    status: Mapped[PartnerStatus] = mapped_column(
        enum_type(PartnerStatus, "partner_status_enum"),
        nullable=False,
        default=PartnerStatus.PENDING,
    )
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    audit_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    domains: Mapped[list[PartnerDomain]] = relationship(
        "PartnerDomain", back_populates="partner", cascade="all, delete-orphan"
    )
    entitlements: Mapped[list[PartnerEntitlement]] = relationship(
        "PartnerEntitlement", back_populates="partner", cascade="all, delete-orphan"
    )
    credentials: Mapped[list[PartnerApiCredential]] = relationship(
        "PartnerApiCredential", back_populates="partner", cascade="all, delete-orphan"
    )
    branding: Mapped[PartnerBranding | None] = relationship(
        "PartnerBranding", back_populates="partner", cascade="all, delete-orphan", uselist=False
    )
    embed_events: Mapped[list[PartnerEmbedEvent]] = relationship("PartnerEmbedEvent", back_populates="partner")

    __table_args__ = (Index("ix_partners_status_created", "status", "created_at"),)


class PartnerDomain(Base):
    """Server-side domain and origin allow-list entry."""

    __tablename__ = "partner_domains"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    domain_pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    origin_pattern: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[PartnerDomainStatus] = mapped_column(
        enum_type(PartnerDomainStatus, "partner_domain_status_enum"),
        nullable=False,
        default=PartnerDomainStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    partner: Mapped[Partner] = relationship("Partner", back_populates="domains")

    __table_args__ = (
        UniqueConstraint("partner_id", "domain_pattern", name="uq_partner_domain_pattern"),
        Index("ix_partner_domains_partner_status", "partner_id", "status"),
    )


class PartnerEntitlement(Base):
    """Explicit content or live-channel permission granted to a partner."""

    __tablename__ = "partner_entitlements"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    content_type: Mapped[PartnerContentType] = mapped_column(
        enum_type(PartnerContentType, "partner_content_type_enum"),
        nullable=False,
    )
    content_id: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[PartnerEntitlementStatus] = mapped_column(
        enum_type(PartnerEntitlementStatus, "partner_entitlement_status_enum"),
        nullable=False,
        default=PartnerEntitlementStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    partner: Mapped[Partner] = relationship("Partner", back_populates="entitlements")

    __table_args__ = (
        UniqueConstraint("partner_id", "content_type", "content_id", name="uq_partner_content_entitlement"),
        Index("ix_partner_entitlements_content", "content_type", "content_id", "status"),
    )


class PartnerApiCredential(Base):
    """Hashed API credential metadata. Plaintext secrets are never persisted."""

    __tablename__ = "partner_api_credentials"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[PartnerCredentialStatus] = mapped_column(
        enum_type(PartnerCredentialStatus, "partner_credential_status_enum"),
        nullable=False,
        default=PartnerCredentialStatus.ACTIVE,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    partner: Mapped[Partner] = relationship("Partner", back_populates="credentials")

    __table_args__ = (Index("ix_partner_credentials_partner_status", "partner_id", "status"),)


class PartnerBranding(Base):
    """Server-authoritative white-label display configuration."""

    __tablename__ = "partner_branding"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    accent_color: Mapped[str] = mapped_column(String(32), nullable=False, default="#ff8a00")
    theme_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    show_gntv_attribution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    partner: Mapped[Partner] = relationship("Partner", back_populates="branding")


class PartnerEmbedEvent(Base):
    """Attribution stream for partner embed authorization and playback events."""

    __tablename__ = "partner_embed_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    content_type: Mapped[PartnerContentType] = mapped_column(
        enum_type(PartnerContentType, "partner_content_type_enum"),
        nullable=False,
    )
    content_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[PartnerEmbedEventType] = mapped_column(
        enum_type(PartnerEmbedEventType, "partner_embed_event_type_enum"),
        nullable=False,
    )
    playback_session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    viewer_session_id_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    origin: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    partner: Mapped[Partner] = relationship("Partner", back_populates="embed_events")

    __table_args__ = (
        Index("ix_partner_embed_events_partner_created", "partner_id", "created_at"),
        Index("ix_partner_embed_events_content_created", "content_type", "content_id", "created_at"),
    )
