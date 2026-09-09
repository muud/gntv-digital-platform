"""SQLAlchemy models for partner syndication and secure embeds."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid
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


class PartnerLifecycleStatus(StrEnum):
    PROSPECT = "prospect"
    INVITED = "invited"
    ONBOARDING = "onboarding"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class PartnerOrganizationType(StrEnum):
    BROADCASTER = "broadcaster"
    MEDIA_NETWORK = "media_network"
    COMMUNITY_ORGANIZATION = "community_organization"
    EDUCATION = "education"
    BUSINESS = "business"
    OTHER = "other"


class PartnerPayoutReadinessStatus(StrEnum):
    NOT_STARTED = "not_started"
    CONFIGURED = "configured"
    VERIFIED = "verified"
    BLOCKED = "blocked"


class PartnerOnboardingChecklistKey(StrEnum):
    ORGANIZATION_PROFILE_COMPLETE = "organization_profile_complete"
    BUSINESS_CONTACT_VERIFIED = "business_contact_verified"
    TECHNICAL_CONTACT_VERIFIED = "technical_contact_verified"
    DOMAINS_REVIEWED = "domains_reviewed"
    SYNDICATION_ENTITLEMENTS_APPROVED = "syndication_entitlements_approved"
    API_EMBED_ACCESS_APPROVED = "api_embed_access_approved"
    REVENUE_SHARE_AGREEMENT_CONFIGURED = "revenue_share_agreement_configured"
    PAYOUT_ACCOUNT_CONFIGURED = "payout_account_configured"
    PAYOUT_ACCOUNT_VERIFIED = "payout_account_verified"
    PORTAL_ACCESS_PROVISIONED = "portal_access_provisioned"


class PartnerInvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class PartnerLifecycleAuditAction(StrEnum):
    INVITATION_CREATED = "invitation_created"
    INVITATION_ACCEPTED = "invitation_accepted"
    ONBOARDING_SUBMITTED = "onboarding_submitted"
    ONBOARDING_RETURNED = "onboarding_returned"
    PARTNER_APPROVED = "partner_approved"
    PARTNER_ACTIVATED = "partner_activated"
    PARTNER_SUSPENDED = "partner_suspended"
    PARTNER_REACTIVATED = "partner_reactivated"
    PARTNER_TERMINATED = "partner_terminated"
    ACCESS_PROVISIONED = "access_provisioned"
    ACCESS_REVOKED = "access_revoked"
    PROFILE_UPDATED = "profile_updated"


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


class PartnerUsageEventType(StrEnum):
    PLAYBACK_START = "playback_start"
    PLAYBACK_COMPLETE = "playback_complete"
    AD_IMPRESSION = "ad_impression"
    AD_COMPLETE = "ad_complete"
    AD_REVENUE = "ad_revenue"
    ADJUSTMENT = "adjustment"


class RevenueShareRuleType(StrEnum):
    FIXED_PERCENTAGE = "fixed_percentage"
    TIERED_PERCENTAGE = "tiered_percentage"


class SettlementStatus(StrEnum):
    DRAFT = "draft"
    FINALIZED = "finalized"
    PAID = "paid"
    DISPUTED = "disputed"
    VOID = "void"


class PartnerFinancialAuditAction(StrEnum):
    USAGE_RECORDED = "usage_recorded"
    AGREEMENT_CREATED = "agreement_created"
    SETTLEMENT_GENERATED = "settlement_generated"
    SETTLEMENT_STATUS_CHANGED = "settlement_status_changed"


class PartnerPayoutAccountStatus(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class PartnerPayoutVerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"


class PartnerPayoutProviderType(StrEnum):
    MOCK = "mock"
    EXTERNAL_REFERENCE = "external_reference"


class PartnerPayoutStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    PROCESSING = "processing"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REVERSED = "reversed"


class PartnerPayoutReconciliationOutcome(StrEnum):
    MATCHED = "matched"
    DUPLICATE_PROVIDER_TRANSACTION = "duplicate_provider_transaction"
    AMOUNT_MISMATCH = "amount_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    UNKNOWN_TRANSACTION = "unknown_transaction"
    FAILED_OR_RETURNED = "failed_or_returned"


class PartnerPayoutAuditAction(StrEnum):
    PAYOUT_ACCOUNT_CREATED = "payout_account_created"
    PAYOUT_ACCOUNT_UPDATED = "payout_account_updated"
    PAYOUT_CREATED = "payout_created"
    PAYOUT_APPROVED = "payout_approved"
    PAYOUT_EXECUTED = "payout_executed"
    PAYOUT_FAILED = "payout_failed"
    PAYOUT_CANCELLED = "payout_cancelled"
    PAYOUT_REVERSED = "payout_reversed"
    PAYOUT_RECONCILED = "payout_reconciled"


class PartnerPortalEventType(StrEnum):
    SETTLEMENT_FINALIZED = "settlement_finalized"
    PAYOUT_APPROVED = "payout_approved"
    PAYOUT_PROCESSING = "payout_processing"
    PAYOUT_PAID = "payout_paid"
    PAYOUT_FAILED = "payout_failed"
    RECONCILIATION_EXCEPTION = "reconciliation_exception"
    ONBOARDING_SUBMITTED = "onboarding_submitted"
    ONBOARDING_RETURNED = "onboarding_returned"
    PARTNER_APPROVED = "partner_approved"
    PARTNER_ACTIVATED = "partner_activated"
    PARTNER_SUSPENDED = "partner_suspended"
    PARTNER_REACTIVATED = "partner_reactivated"
    PARTNER_TERMINATED = "partner_terminated"


class PartnerPortalUserRole(StrEnum):
    VIEWER = "partner_viewer"
    FINANCE = "partner_finance"
    ADMIN = "partner_admin"



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
    lifecycle_status: Mapped[PartnerLifecycleStatus] = mapped_column(
        enum_type(PartnerLifecycleStatus, "partner_lifecycle_status_enum"),
        nullable=False,
        default=PartnerLifecycleStatus.PROSPECT,
    )
    lifecycle_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    revenue_share_agreements: Mapped[list[PartnerRevenueShareAgreement]] = relationship(
        "PartnerRevenueShareAgreement", back_populates="partner", cascade="all, delete-orphan"
    )
    usage_metering: Mapped[list[PartnerUsageMeter]] = relationship(
        "PartnerUsageMeter", back_populates="partner", cascade="all, delete-orphan"
    )
    settlement_statements: Mapped[list[PartnerSettlementStatement]] = relationship(
        "PartnerSettlementStatement", back_populates="partner", cascade="all, delete-orphan"
    )
    payout_accounts: Mapped[list[PartnerPayoutAccount]] = relationship(
        "PartnerPayoutAccount", back_populates="partner", cascade="all, delete-orphan"
    )
    payouts: Mapped[list[PartnerPayout]] = relationship(
        "PartnerPayout", back_populates="partner", cascade="all, delete-orphan"
    )
    portal_events: Mapped[list[PartnerPortalEvent]] = relationship(
        "PartnerPortalEvent", back_populates="partner", cascade="all, delete-orphan"
    )
    portal_users: Mapped[list[PartnerPortalUser]] = relationship(
        "PartnerPortalUser", back_populates="partner", cascade="all, delete-orphan"
    )
    onboarding_profile: Mapped[PartnerOnboardingProfile | None] = relationship(
        "PartnerOnboardingProfile", back_populates="partner", cascade="all, delete-orphan", uselist=False
    )
    onboarding_checklist: Mapped[list[PartnerOnboardingChecklistItem]] = relationship(
        "PartnerOnboardingChecklistItem", back_populates="partner", cascade="all, delete-orphan"
    )
    invitations: Mapped[list[PartnerInvitation]] = relationship(
        "PartnerInvitation", back_populates="partner", cascade="all, delete-orphan"
    )
    lifecycle_audits: Mapped[list[PartnerLifecycleAuditLog]] = relationship(
        "PartnerLifecycleAuditLog", back_populates="partner", cascade="all, delete-orphan"
    )

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


class PartnerRevenueShareAgreement(Base):
    """Configurable financial agreement for partner settlement calculations."""

    __tablename__ = "partner_revenue_share_agreements"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    rule_type: Mapped[RevenueShareRuleType] = mapped_column(
        enum_type(RevenueShareRuleType, "partner_revenue_share_rule_type_enum"),
        nullable=False,
    )
    fixed_partner_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    tiers_json: Mapped[list[dict[str, str]] | None] = mapped_column(JSON, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    partner: Mapped[Partner] = relationship("Partner", back_populates="revenue_share_agreements")

    __table_args__ = (
        Index("ix_partner_revshare_partner_active", "partner_id", "is_active", "starts_at", "ends_at"),
    )


class PartnerUsageMeter(Base):
    """Persisted usage and monetization input used for billing."""

    __tablename__ = "partner_usage_metering"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    content_type: Mapped[PartnerContentType] = mapped_column(
        enum_type(PartnerContentType, "partner_content_type_enum"),
        nullable=False,
    )
    content_id: Mapped[str] = mapped_column(String(255), nullable=False)
    usage_event_type: Mapped[PartnerUsageEventType] = mapped_column(
        enum_type(PartnerUsageEventType, "partner_usage_event_type_enum"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    gross_revenue_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    source_event_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    partner: Mapped[Partner] = relationship("Partner", back_populates="usage_metering")

    __table_args__ = (
        UniqueConstraint("partner_id", "idempotency_key", name="uq_partner_usage_idempotency"),
        Index("ix_partner_usage_partner_period", "partner_id", "occurred_at"),
        Index("ix_partner_usage_content_period", "content_type", "content_id", "occurred_at"),
    )


class PartnerSettlementStatement(Base):
    """Immutable billing-period statement once finalized."""

    __tablename__ = "partner_settlement_statements"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    agreement_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partner_revenue_share_agreements.id", ondelete="RESTRICT"), nullable=False
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gross_revenue_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    platform_share_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    partner_share_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    adjustment_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    net_settlement_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    status: Mapped[SettlementStatus] = mapped_column(
        enum_type(SettlementStatus, "partner_settlement_status_enum"),
        nullable=False,
        default=SettlementStatus.DRAFT,
    )
    calculation_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    generated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    partner: Mapped[Partner] = relationship("Partner", back_populates="settlement_statements")
    agreement: Mapped[PartnerRevenueShareAgreement] = relationship("PartnerRevenueShareAgreement")

    __table_args__ = (
        UniqueConstraint("partner_id", "period_start", "period_end", "currency", name="uq_partner_settlement_period"),
        UniqueConstraint("partner_id", "idempotency_key", name="uq_partner_settlement_idempotency"),
        Index("ix_partner_settlement_status_period", "status", "period_start", "period_end"),
    )


class PartnerFinancialAuditLog(Base):
    """Audit trail for financial state changes."""

    __tablename__ = "partner_financial_audit_logs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    statement_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("partner_settlement_statements.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[PartnerFinancialAuditAction] = mapped_column(
        enum_type(PartnerFinancialAuditAction, "partner_financial_audit_action_enum"),
        nullable=False,
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (Index("ix_partner_financial_audit_partner_created", "partner_id", "created_at"),)


class PartnerPayoutAccount(Base):
    """Provider-neutral payout destination with sealed non-sensitive metadata."""

    __tablename__ = "partner_payout_accounts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    provider_type: Mapped[PartnerPayoutProviderType] = mapped_column(
        enum_type(PartnerPayoutProviderType, "partner_payout_provider_type_enum"),
        nullable=False,
    )
    destination_label: Mapped[str] = mapped_column(String(160), nullable=False)
    destination_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_provider_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PartnerPayoutAccountStatus] = mapped_column(
        enum_type(PartnerPayoutAccountStatus, "partner_payout_account_status_enum"),
        nullable=False,
        default=PartnerPayoutAccountStatus.ENABLED,
    )
    verification_status: Mapped[PartnerPayoutVerificationStatus] = mapped_column(
        enum_type(PartnerPayoutVerificationStatus, "partner_payout_verification_status_enum"),
        nullable=False,
        default=PartnerPayoutVerificationStatus.UNVERIFIED,
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    partner: Mapped[Partner] = relationship("Partner", back_populates="payout_accounts")
    payouts: Mapped[list[PartnerPayout]] = relationship("PartnerPayout", back_populates="payout_account")

    __table_args__ = (
        UniqueConstraint("partner_id", "idempotency_key", name="uq_partner_payout_account_idempotency"),
        Index("ix_partner_payout_accounts_partner_status", "partner_id", "status", "verification_status"),
    )


class PartnerPayout(Base):
    """Controlled payout instruction derived from a finalized settlement statement."""

    __tablename__ = "partner_payouts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    settlement_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partner_settlement_statements.id", ondelete="RESTRICT"), nullable=False
    )
    payout_account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partner_payout_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PartnerPayoutStatus] = mapped_column(
        enum_type(PartnerPayoutStatus, "partner_payout_status_enum"),
        nullable=False,
        default=PartnerPayoutStatus.PENDING,
    )
    provider_type: Mapped[PartnerPayoutProviderType] = mapped_column(
        enum_type(PartnerPayoutProviderType, "partner_payout_provider_type_enum"),
        nullable=False,
    )
    provider_payout_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provider_transaction_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provider_execution_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    partner: Mapped[Partner] = relationship("Partner", back_populates="payouts")
    settlement: Mapped[PartnerSettlementStatement] = relationship("PartnerSettlementStatement")
    payout_account: Mapped[PartnerPayoutAccount] = relationship("PartnerPayoutAccount", back_populates="payouts")

    __table_args__ = (
        UniqueConstraint("partner_id", "idempotency_key", name="uq_partner_payout_idempotency"),
        UniqueConstraint("settlement_id", name="uq_partner_payout_settlement"),
        UniqueConstraint("provider_type", "provider_transaction_id", name="uq_partner_payout_provider_transaction"),
        Index("ix_partner_payouts_partner_status", "partner_id", "status", "created_at"),
    )


class PartnerPayoutReconciliation(Base):
    """Deterministic reconciliation result for provider payout transactions."""

    __tablename__ = "partner_payout_reconciliations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    payout_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("partner_payouts.id", ondelete="SET NULL"), nullable=True
    )
    provider_type: Mapped[PartnerPayoutProviderType] = mapped_column(
        enum_type(PartnerPayoutProviderType, "partner_payout_provider_type_enum"),
        nullable=False,
    )
    provider_transaction_id: Mapped[str] = mapped_column(String(160), nullable=False)
    reported_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    reported_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    provider_status: Mapped[str] = mapped_column(String(80), nullable=False)
    outcome: Mapped[PartnerPayoutReconciliationOutcome] = mapped_column(
        enum_type(PartnerPayoutReconciliationOutcome, "partner_payout_reconciliation_outcome_enum"),
        nullable=False,
    )
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    reconciled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    payout: Mapped[PartnerPayout | None] = relationship("PartnerPayout")

    __table_args__ = (
        UniqueConstraint("partner_id", "idempotency_key", name="uq_partner_reconciliation_idempotency"),
        Index("ix_partner_reconciliation_provider_txn", "provider_type", "provider_transaction_id"),
        Index("ix_partner_reconciliation_partner_created", "partner_id", "created_at"),
    )


class PartnerPayoutAuditLog(Base):
    """Append-only payout audit trail with provider reference context."""

    __tablename__ = "partner_payout_audit_logs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    payout_account_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("partner_payout_accounts.id", ondelete="SET NULL"), nullable=True
    )
    payout_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("partner_payouts.id", ondelete="SET NULL"), nullable=True)
    reconciliation_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("partner_payout_reconciliations.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[PartnerPayoutAuditAction] = mapped_column(
        enum_type(PartnerPayoutAuditAction, "partner_payout_audit_action_enum"),
        nullable=False,
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (Index("ix_partner_payout_audit_partner_created", "partner_id", "created_at"),)


class PartnerOnboardingProfile(Base):
    """Partner-supplied onboarding profile, separate from operator-only decisions."""

    __tablename__ = "partner_onboarding_profiles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    legal_organization_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    organization_type: Mapped[PartnerOrganizationType | None] = mapped_column(
        enum_type(PartnerOrganizationType, "partner_organization_type_enum"),
        nullable=True,
    )
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    primary_business_contact_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    finance_contact_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    technical_contact_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    approved_domains_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    requested_domains_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    requested_capabilities_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    requested_api_embed_access: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settlement_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    payout_readiness_status: Mapped[PartnerPayoutReadinessStatus] = mapped_column(
        enum_type(PartnerPayoutReadinessStatus, "partner_payout_readiness_status_enum"),
        nullable=False,
        default=PartnerPayoutReadinessStatus.NOT_STARTED,
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    partner: Mapped[Partner] = relationship("Partner", back_populates="onboarding_profile")

    __table_args__ = (Index("ix_partner_onboarding_profiles_partner", "partner_id"),)


class PartnerOnboardingChecklistItem(Base):
    """Persisted checklist state, with completion derived by service where possible."""

    __tablename__ = "partner_onboarding_checklist_items"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    item_key: Mapped[PartnerOnboardingChecklistKey] = mapped_column(
        enum_type(PartnerOnboardingChecklistKey, "partner_onboarding_checklist_key_enum"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    is_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    derived_from: Mapped[str | None] = mapped_column(String(120), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    partner: Mapped[Partner] = relationship("Partner", back_populates="onboarding_checklist")

    __table_args__ = (
        UniqueConstraint("partner_id", "item_key", name="uq_partner_onboarding_checklist_item"),
        Index("ix_partner_onboarding_checklist_partner_complete", "partner_id", "is_complete"),
    )


class PartnerInvitation(Base):
    """Hashed partner invitation token metadata."""

    __tablename__ = "partner_invitations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    target_email: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    status: Mapped[PartnerInvitationStatus] = mapped_column(
        enum_type(PartnerInvitationStatus, "partner_invitation_status_enum"),
        nullable=False,
        default=PartnerInvitationStatus.PENDING,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    accepted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    partner: Mapped[Partner] = relationship("Partner", back_populates="invitations")

    __table_args__ = (Index("ix_partner_invitations_partner_status", "partner_id", "status", "expires_at"),)


class PartnerLifecycleAuditLog(Base):
    """Append-only audit trail for partner lifecycle and access provisioning."""

    __tablename__ = "partner_lifecycle_audit_logs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[PartnerLifecycleAuditAction] = mapped_column(
        enum_type(PartnerLifecycleAuditAction, "partner_lifecycle_audit_action_enum"),
        nullable=False,
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    invitation_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("partner_invitations.id", ondelete="SET NULL"), nullable=True
    )
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    partner: Mapped[Partner] = relationship("Partner", back_populates="lifecycle_audits")

    __table_args__ = (Index("ix_partner_lifecycle_audit_partner_created", "partner_id", "created_at"),)


class PartnerPortalEvent(Base):
    """Partner-visible financial and account status event feed."""

    __tablename__ = "partner_portal_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[PartnerPortalEventType] = mapped_column(
        enum_type(PartnerPortalEventType, "partner_portal_event_type_enum"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="info")
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    visible_to_partner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    partner: Mapped[Partner] = relationship("Partner", back_populates="portal_events")

    __table_args__ = (
        Index("ix_partner_portal_events_partner_created", "partner_id", "created_at"),
        Index("ix_partner_portal_events_partner_type", "partner_id", "event_type", "created_at"),
    )


class PartnerPortalUser(Base):
    """User membership granting access to the partner portal."""

    __tablename__ = "partner_portal_users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default=PartnerPortalUserRole.VIEWER.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    partner: Mapped[Partner] = relationship("Partner", back_populates="portal_users")

    __table_args__ = (
        UniqueConstraint("partner_id", "user_id", name="uq_partner_portal_user"),
        Index("ix_partner_portal_users_user", "user_id"),
    )
