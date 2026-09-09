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
    PartnerInvitationStatus,
    PartnerLifecycleAuditAction,
    PartnerLifecycleStatus,
    PartnerOnboardingChecklistKey,
    PartnerOrganizationType,
    PartnerPayoutAccountStatus,
    PartnerPayoutAuditAction,
    PartnerPayoutReadinessStatus,
    PartnerPayoutProviderType,
    PartnerPayoutReconciliationOutcome,
    PartnerPayoutStatus,
    PartnerPayoutVerificationStatus,
    PartnerPortalEventType,
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
    lifecycle_status: PartnerLifecycleStatus
    lifecycle_updated_at: datetime | None
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


class PartnerPayoutAccountCreate(BaseModel):
    provider_type: PartnerPayoutProviderType = PartnerPayoutProviderType.MOCK
    destination_label: str = Field(..., min_length=2, max_length=160)
    destination_reference: str = Field(..., min_length=4, max_length=255)
    provider_metadata: dict[str, object] | None = None
    currency: str = Field("USD", min_length=3, max_length=3)
    verification_status: PartnerPayoutVerificationStatus = PartnerPayoutVerificationStatus.UNVERIFIED
    idempotency_key: str = Field(..., min_length=8, max_length=160)

    @field_validator("provider_metadata")
    @classmethod
    def reject_sensitive_metadata(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        if value is None:
            return None
        forbidden_fragments = ("account_number", "routing_number", "iban", "swift", "password", "secret", "token", "key")
        lower_keys = {str(key).lower() for key in value}
        if any(any(fragment in key for fragment in forbidden_fragments) for key in lower_keys):
            raise ValueError("provider_metadata must not contain plaintext banking credentials or payment secrets")
        return value


class PartnerPayoutAccountUpdate(BaseModel):
    destination_label: str | None = Field(None, min_length=2, max_length=160)
    provider_metadata: dict[str, object] | None = None
    status: PartnerPayoutAccountStatus | None = None
    verification_status: PartnerPayoutVerificationStatus | None = None

    @field_validator("provider_metadata")
    @classmethod
    def reject_sensitive_metadata(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        return PartnerPayoutAccountCreate.reject_sensitive_metadata(value)


class PartnerPayoutAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    provider_type: PartnerPayoutProviderType
    destination_label: str
    destination_reference: str
    currency: str
    status: PartnerPayoutAccountStatus
    verification_status: PartnerPayoutVerificationStatus
    idempotency_key: str
    created_by_user_id: int | None
    updated_by_user_id: int | None
    created_at: datetime
    updated_at: datetime


class PartnerPayoutCreate(BaseModel):
    settlement_id: UUID
    payout_account_id: UUID
    idempotency_key: str = Field(..., min_length=8, max_length=160)


class PartnerPayoutExecuteRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=8, max_length=160)


class PartnerPayoutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    settlement_id: UUID
    payout_account_id: UUID
    amount: Decimal
    currency: str
    status: PartnerPayoutStatus
    provider_type: PartnerPayoutProviderType
    provider_payout_id: str | None
    provider_transaction_id: str | None
    provider_execution_key: str | None
    idempotency_key: str
    failure_code: str | None
    failure_reason: str | None
    created_by_user_id: int | None
    approved_by_user_id: int | None
    created_at: datetime
    approved_at: datetime | None
    executed_at: datetime | None
    paid_at: datetime | None
    cancelled_at: datetime | None
    updated_at: datetime


class PartnerReconciliationCreate(BaseModel):
    provider_type: PartnerPayoutProviderType = PartnerPayoutProviderType.MOCK
    provider_transaction_id: str = Field(..., min_length=4, max_length=160)
    reported_amount: Decimal = Field(..., ge=Decimal("0"))
    reported_currency: str = Field(..., min_length=3, max_length=3)
    provider_status: str = Field(..., min_length=2, max_length=80)
    idempotency_key: str = Field(..., min_length=8, max_length=160)


class PartnerReconciliationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    payout_id: UUID | None
    provider_type: PartnerPayoutProviderType
    provider_transaction_id: str
    reported_amount: Decimal
    reported_currency: str
    provider_status: str
    outcome: PartnerPayoutReconciliationOutcome
    details_json: dict[str, object] | None
    idempotency_key: str
    reconciled_by_user_id: int | None
    created_at: datetime


class PartnerPayoutAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    payout_account_id: UUID | None
    payout_id: UUID | None
    reconciliation_id: UUID | None
    action: PartnerPayoutAuditAction
    actor_user_id: int | None
    provider_reference: str | None
    before_json: dict[str, object] | None
    after_json: dict[str, object] | None
    created_at: datetime


class PartnerPortalPayoutAccountSummary(BaseModel):
    id: UUID
    provider_type: PartnerPayoutProviderType
    destination_label: str
    masked_destination_reference: str
    currency: str
    status: PartnerPayoutAccountStatus
    verification_status: PartnerPayoutVerificationStatus
    created_at: datetime
    updated_at: datetime


class PartnerPortalMeResponse(BaseModel):
    partner: PartnerResponse
    authorized_domains: list[PartnerDomainResponse]
    entitlements: list[PartnerEntitlementResponse]
    payout_accounts: list[PartnerPortalPayoutAccountSummary]


class PartnerPortalEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    event_type: PartnerPortalEventType
    title: str
    message: str
    resource_type: str | None
    resource_id: UUID | None
    severity: str
    payload_json: dict[str, object] | None
    created_at: datetime


class PartnerPortalOverviewResponse(BaseModel):
    partner_id: UUID
    active_entitlements: int
    authorized_domains: int
    usage_total: int
    gross_revenue_amount: Decimal
    partner_share_amount: Decimal
    finalized_settlements: int
    pending_payouts: int
    paid_payouts: int
    reconciliation_exceptions: int
    currency: str | None
    recent_events: list[PartnerPortalEventResponse]


class PartnerPortalUsageSummaryResponse(BaseModel):
    partner_id: UUID
    usage_total: int
    gross_revenue_amount: Decimal
    currency: str | None
    rows: list[PartnerUsageMeterResponse]
    content_performance: list[dict[str, object]]


class PartnerPortalRevenueSummaryResponse(BaseModel):
    partner_id: UUID
    gross_revenue_amount: Decimal
    platform_share_amount: Decimal
    partner_share_amount: Decimal
    adjustment_amount: Decimal
    net_settlement_amount: Decimal
    currency: str | None
    time_series: list[dict[str, object]]


class PartnerPortalSettlementResponse(PartnerSettlementStatementResponse):
    payout_status: PartnerPayoutStatus | None = None


class PartnerPortalPayoutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    settlement_id: UUID
    payout_account_id: UUID
    amount: Decimal
    currency: str
    status: PartnerPayoutStatus
    provider_type: PartnerPayoutProviderType
    provider_transaction_reference: str | None
    failure_code: str | None
    failure_reason: str | None
    created_at: datetime
    approved_at: datetime | None
    executed_at: datetime | None
    paid_at: datetime | None
    cancelled_at: datetime | None
    updated_at: datetime


class PartnerPortalReconciliationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payout_id: UUID | None
    provider_type: PartnerPayoutProviderType
    provider_transaction_reference: str
    reported_amount: Decimal
    reported_currency: str
    provider_status: str
    outcome: PartnerPayoutReconciliationOutcome
    details_json: dict[str, object] | None
    created_at: datetime


class PartnerPortalStatementResponse(BaseModel):
    settlement: PartnerPortalSettlementResponse
    payouts: list[PartnerPortalPayoutResponse]
    reconciliation: list[PartnerPortalReconciliationResponse]


class PartnerPortalExportManifestResponse(BaseModel):
    generated_at: datetime
    partner_id: UUID
    report_type: str
    currency: str | None
    rows: list[dict[str, object]]


class PartnerContactInfo(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    email: str = Field(..., min_length=5, max_length=255)
    phone: str | None = Field(None, max_length=80)
    title: str | None = Field(None, max_length=120)


class PartnerOnboardingProfileUpdate(BaseModel):
    legal_organization_name: str | None = Field(None, min_length=2, max_length=240)
    display_name: str | None = Field(None, min_length=2, max_length=160)
    organization_type: PartnerOrganizationType | None = None
    country: str | None = Field(None, min_length=2, max_length=2)
    primary_business_contact: PartnerContactInfo | None = None
    finance_contact: PartnerContactInfo | None = None
    technical_contact: PartnerContactInfo | None = None
    requested_domains: list[str] | None = None
    requested_capabilities: list[str] | None = None
    requested_api_embed_access: bool | None = None
    settlement_currency: str | None = Field(None, min_length=3, max_length=3)

    @field_validator("requested_domains")
    @classmethod
    def validate_requested_domains(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = sorted({item.strip().lower() for item in value if item.strip()})
        if any("://" in item or "/" in item for item in cleaned):
            raise ValueError("requested_domains must contain hostnames, not URLs")
        if len(cleaned) > 50:
            raise ValueError("requested_domains cannot exceed 50 entries")
        return cleaned

    @field_validator("requested_capabilities")
    @classmethod
    def validate_capabilities(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        allowed = {"vod_embed", "live_embed", "podcast_embed", "api_reporting", "fast_channel"}
        cleaned = sorted({item.strip().lower() for item in value if item.strip()})
        unsupported = [item for item in cleaned if item not in allowed]
        if unsupported:
            raise ValueError(f"Unsupported requested capabilities: {', '.join(unsupported)}")
        return cleaned


class PartnerOperatorOnboardingUpdate(PartnerOnboardingProfileUpdate):
    approved_domains: list[str] | None = None
    payout_readiness_status: PartnerPayoutReadinessStatus | None = None
    review_notes: str | None = Field(None, max_length=1000)

    @field_validator("approved_domains")
    @classmethod
    def validate_approved_domains(cls, value: list[str] | None) -> list[str] | None:
        return PartnerOnboardingProfileUpdate.validate_requested_domains(value)


class PartnerOnboardingProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    legal_organization_name: str | None
    display_name: str | None
    organization_type: PartnerOrganizationType | None
    country: str | None
    primary_business_contact_json: dict[str, object] | None
    finance_contact_json: dict[str, object] | None
    technical_contact_json: dict[str, object] | None
    approved_domains_json: list[str]
    requested_domains_json: list[str]
    requested_capabilities_json: list[str]
    requested_api_embed_access: bool
    settlement_currency: str | None
    payout_readiness_status: PartnerPayoutReadinessStatus
    submitted_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by_user_id: int | None
    review_notes: str | None
    created_at: datetime
    updated_at: datetime


class PartnerOnboardingChecklistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    item_key: PartnerOnboardingChecklistKey
    title: str
    is_complete: bool
    derived_from: str | None
    completed_at: datetime | None
    completed_by_user_id: int | None
    metadata_json: dict[str, object] | None
    created_at: datetime
    updated_at: datetime


class PartnerLifecycleAuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    partner_id: UUID
    action: PartnerLifecycleAuditAction
    actor_user_id: int | None
    invitation_id: UUID | None
    before_json: dict[str, object] | None
    after_json: dict[str, object] | None
    metadata_json: dict[str, object] | None
    created_at: datetime


class PartnerInvitationCreate(BaseModel):
    target_email: str = Field(..., min_length=5, max_length=255)
    expires_at: datetime | None = None


class PartnerInvitationPartnerCreateRequest(BaseModel):
    partner: PartnerCreate
    invitation: PartnerInvitationCreate


class PartnerInvitationAccept(BaseModel):
    token: str = Field(..., min_length=24, max_length=240)
    user_id: int | None = Field(None, ge=1)


class PartnerInvitationResponse(BaseModel):
    id: UUID
    partner_id: UUID
    target_email: str
    status: PartnerInvitationStatus
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_by_user_id: int | None
    accepted_by_user_id: int | None
    created_at: datetime
    invitation_reference: str | None = None


class PartnerLifecycleActionRequest(BaseModel):
    reason: str | None = Field(None, max_length=1000)


class PartnerOnboardingReviewRequest(BaseModel):
    review_notes: str | None = Field(None, max_length=1000)


class PartnerOnboardingStatusResponse(BaseModel):
    partner: PartnerResponse
    profile: PartnerOnboardingProfileResponse | None
    checklist: list[PartnerOnboardingChecklistItemResponse]
    checklist_complete_count: int
    checklist_total_count: int
    can_submit: bool
    can_approve: bool
    can_activate: bool
    audit: list[PartnerLifecycleAuditResponse] = []


class PartnerLifecycleResponse(BaseModel):
    partner: PartnerResponse
    profile: PartnerOnboardingProfileResponse | None
    checklist: list[PartnerOnboardingChecklistItemResponse]
    audit_event: PartnerLifecycleAuditResponse | None = None
