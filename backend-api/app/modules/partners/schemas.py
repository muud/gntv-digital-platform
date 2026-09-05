"""Pydantic contracts for partner syndication and embed authorization."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.partners.models import (
    PartnerContentType,
    PartnerEmbedEventType,
    PartnerEntitlementStatus,
    PartnerFinancialAuditAction,
    PartnerStatus,
    PartnerUsageEventType,
    RevenueShareRuleType,
    SettlementStatus,
)


class PartnerBrandingInput(BaseModel):
    display_name: str = Field(..., min_length=2, max_length=160)
    logo_url: AnyHttpUrl | None = None
    accent_color: str = Field("#ff8a00", pattern=r"^#[0-9a-fA-F]{6}$")
    theme_json: dict[str, object] | None = None
    show_gntv_attribution: bool = True


class PartnerBrandingResponse(PartnerBrandingInput):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    updated_at: datetime


class PartnerCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    slug: str = Field(..., min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
    status: PartnerStatus = PartnerStatus.PENDING
    contact_email: str | None = Field(None, max_length=255)
    rate_limit_per_minute: int = Field(120, ge=1, le=10_000)
    branding: PartnerBrandingInput | None = None
    audit_metadata_json: dict[str, object] | None = None


class PartnerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    status: PartnerStatus
    contact_email: str | None
    rate_limit_per_minute: int
    audit_metadata_json: dict[str, object] | None
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    branding: PartnerBrandingResponse | None = None


class PartnerCredentialResponse(BaseModel):
    id: UUID
    key_prefix: str
    status: str
    created_at: datetime


class PartnerCreateResponse(BaseModel):
    partner: PartnerResponse
    credential: PartnerCredentialResponse


class PartnerDomainCreate(BaseModel):
    domain_pattern: str = Field(..., min_length=3, max_length=255)
    origin_pattern: str | None = Field(None, min_length=8, max_length=500)

    @field_validator("domain_pattern")
    @classmethod
    def validate_domain_pattern(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "://" in cleaned or "/" in cleaned:
            raise ValueError("domain_pattern must be a hostname pattern, not a URL")
        if cleaned.startswith("*.") and cleaned.count("*") == 1:
            return cleaned
        if "*" in cleaned:
            raise ValueError("wildcards are only supported as a leading '*.'")
        return cleaned


class PartnerDomainResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    domain_pattern: str
    origin_pattern: str | None
    status: str
    created_at: datetime


class PartnerEntitlementCreate(BaseModel):
    content_type: PartnerContentType
    content_id: str = Field(..., min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=lambda: ["embed:play"])
    starts_at: datetime | None = None
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        cleaned = sorted({scope.strip() for scope in value if scope.strip()})
        if not cleaned:
            raise ValueError("at least one scope is required")
        return cleaned


class PartnerEntitlementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    content_type: PartnerContentType
    content_id: str
    scopes_json: list[str]
    starts_at: datetime | None
    expires_at: datetime | None
    status: PartnerEntitlementStatus
    created_at: datetime


class EmbedTokenRequest(BaseModel):
    content_type: PartnerContentType
    content_id: str = Field(..., min_length=1, max_length=255)
    domain: str = Field(..., min_length=3, max_length=255)
    origin: str | None = Field(None, min_length=8, max_length=500)
    viewer_session_id: str | None = Field(None, max_length=128)
    playback_session_id: str | None = Field(None, max_length=128)
    scopes: list[str] = Field(default_factory=lambda: ["embed:play"])
    ttl_seconds: int | None = Field(None, ge=30, le=3600)


class EmbedTokenResponse(BaseModel):
    token: str
    expires_at: datetime
    partner_id: UUID
    content_type: PartnerContentType
    content_id: str
    scopes: list[str]
    branding: PartnerBrandingResponse | None


class EmbedAuthorizeRequest(BaseModel):
    token: str = Field(..., min_length=32)
    domain: str = Field(..., min_length=3, max_length=255)
    origin: str | None = Field(None, max_length=500)
    playback_session_id: str | None = Field(None, max_length=128)


class EmbedAuthorizeResponse(BaseModel):
    authorized: bool
    partner_id: UUID
    content_type: PartnerContentType
    content_id: str
    expires_at: datetime
    scopes: list[str]
    playback_url: str
    branding: PartnerBrandingResponse | None


class PartnerEmbedEventCreate(BaseModel):
    token: str = Field(..., min_length=32)
    event_type: PartnerEmbedEventType
    domain: str = Field(..., min_length=3, max_length=255)
    origin: str | None = Field(None, max_length=500)
    playback_session_id: str | None = Field(None, max_length=128)
    error_code: str | None = Field(None, max_length=80)
    metadata_json: dict[str, object] | None = None


class PartnerEmbedEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    content_type: PartnerContentType
    content_id: str
    event_type: PartnerEmbedEventType
    playback_session_id: str | None
    domain: str
    origin: str | None
    error_code: str | None
    created_at: datetime


class PartnerAnalyticsOverview(BaseModel):
    partner_count: int
    active_partner_count: int
    authorized_embed_count: int
    playback_start_count: int
    completion_count: int
    error_count: int


class RevenueShareTier(BaseModel):
    threshold_amount: Decimal = Field(..., ge=Decimal("0"))
    partner_percentage: Decimal = Field(..., ge=Decimal("0"), le=Decimal("1"))


class PartnerRevenueShareAgreementCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    rule_type: RevenueShareRuleType
    fixed_partner_percentage: Decimal | None = Field(None, ge=Decimal("0"), le=Decimal("1"))
    tiers: list[RevenueShareTier] | None = None
    currency: str = Field("USD", min_length=3, max_length=3)
    starts_at: datetime
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def validate_rule(self) -> "PartnerRevenueShareAgreementCreate":
        if self.ends_at and self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be before ends_at")
        if self.rule_type == RevenueShareRuleType.FIXED_PERCENTAGE and self.fixed_partner_percentage is None:
            raise ValueError("fixed_partner_percentage is required for fixed rules")
        if self.rule_type == RevenueShareRuleType.TIERED_PERCENTAGE:
            if not self.tiers:
                raise ValueError("tiers are required for tiered rules")
            thresholds = [tier.threshold_amount for tier in self.tiers]
            if thresholds != sorted(thresholds):
                raise ValueError("tiers must be sorted by threshold_amount")
        return self


class PartnerRevenueShareAgreementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    name: str
    rule_type: RevenueShareRuleType
    fixed_partner_percentage: Decimal | None
    tiers_json: list[dict[str, str]] | None
    currency: str
    starts_at: datetime
    ends_at: datetime | None
    is_active: bool
    created_by_user_id: int | None
    created_at: datetime


class PartnerUsageMeterCreate(BaseModel):
    content_type: PartnerContentType
    content_id: str = Field(..., min_length=1, max_length=255)
    usage_event_type: PartnerUsageEventType
    quantity: int = Field(1, ge=1, le=1_000_000)
    gross_revenue_amount: Decimal = Field(Decimal("0"), ge=Decimal("0"))
    currency: str = Field("USD", min_length=3, max_length=3)
    source_event_id: str | None = Field(None, max_length=160)
    idempotency_key: str = Field(..., min_length=8, max_length=160)
    occurred_at: datetime
    metadata_json: dict[str, object] | None = None


class PartnerUsageMeterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    content_type: PartnerContentType
    content_id: str
    usage_event_type: PartnerUsageEventType
    quantity: int
    gross_revenue_amount: Decimal
    currency: str
    source_event_id: str | None
    idempotency_key: str
    occurred_at: datetime
    created_at: datetime


class PartnerSettlementGenerateRequest(BaseModel):
    period_start: datetime
    period_end: datetime
    currency: str = Field("USD", min_length=3, max_length=3)
    adjustment_amount: Decimal = Decimal("0")
    idempotency_key: str = Field(..., min_length=8, max_length=160)

    @model_validator(mode="after")
    def validate_period(self) -> "PartnerSettlementGenerateRequest":
        if self.period_start >= self.period_end:
            raise ValueError("period_start must be before period_end")
        return self


class PartnerSettlementStatusUpdate(BaseModel):
    status: SettlementStatus
    reason: str | None = Field(None, max_length=500)


class PartnerSettlementStatementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    agreement_id: UUID
    period_start: datetime
    period_end: datetime
    currency: str
    usage_count: int
    gross_revenue_amount: Decimal
    platform_share_amount: Decimal
    partner_share_amount: Decimal
    adjustment_amount: Decimal
    net_settlement_amount: Decimal
    status: SettlementStatus
    calculation_json: dict[str, object]
    idempotency_key: str
    generated_by_user_id: int | None
    generated_at: datetime
    finalized_at: datetime | None
    paid_at: datetime | None


class PartnerFinancialAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    statement_id: UUID | None
    action: PartnerFinancialAuditAction
    actor_user_id: int | None
    before_json: dict[str, object] | None
    after_json: dict[str, object] | None
    created_at: datetime
