"""Business logic for partner syndication and secure embed authorization."""

from __future__ import annotations

import base64
import csv
from cryptography.fernet import Fernet
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import hmac
from io import StringIO
import json
import secrets
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from app.core.config import settings
from app.modules.partners.models import (
    Partner,
    PartnerApiCredential,
    PartnerBranding,
    PartnerContentType,
    PartnerCredentialStatus,
    PartnerDomain,
    PartnerEmbedEvent,
    PartnerEmbedEventType,
    PartnerEntitlement,
    PartnerFinancialAuditAction,
    PartnerFinancialAuditLog,
    PartnerPayout,
    PartnerPayoutAccount,
    PartnerPayoutAccountStatus,
    PartnerPayoutAuditAction,
    PartnerPayoutAuditLog,
    PartnerPayoutReconciliation,
    PartnerPayoutReconciliationOutcome,
    PartnerPayoutStatus,
    PartnerPayoutVerificationStatus,
    PartnerPortalEvent,
    PartnerPortalEventType,
    PartnerPortalUser,
    PartnerRevenueShareAgreement,

    PartnerSettlementStatement,
    PartnerStatus,
    PartnerUsageMeter,
    RevenueShareRuleType,
    SettlementStatus,
)
from app.modules.partners.providers import ProviderPayoutRequest, get_payment_provider
from app.modules.partners.repository import PartnerRepository
from app.modules.partners.schemas import (
    EmbedAuthorizeRequest,
    EmbedAuthorizeResponse,
    EmbedTokenRequest,
    EmbedTokenResponse,
    PartnerAnalyticsOverview,
    PartnerBrandingInput,
    PartnerBrandingResponse,
    PartnerCreate,
    PartnerCreateResponse,
    PartnerCredentialResponse,
    PartnerDomainCreate,
    PartnerDomainResponse,
    PartnerEmbedEventCreate,
    PartnerEntitlementCreate,
    PartnerEntitlementResponse,
    PartnerFinancialAuditLogResponse,
    PartnerPayoutAccountCreate,
    PartnerPayoutAccountResponse,
    PartnerPayoutAccountUpdate,
    PartnerPayoutAuditLogResponse,
    PartnerPayoutCreate,
    PartnerPayoutExecuteRequest,
    PartnerPayoutResponse,
    PartnerPortalEventResponse,
    PartnerPortalExportManifestResponse,
    PartnerPortalMeResponse,
    PartnerPortalOverviewResponse,
    PartnerPortalPayoutAccountSummary,
    PartnerPortalPayoutResponse,
    PartnerPortalReconciliationResponse,
    PartnerPortalRevenueSummaryResponse,
    PartnerPortalSettlementResponse,
    PartnerPortalStatementResponse,
    PartnerPortalUsageSummaryResponse,
    PartnerReconciliationCreate,
    PartnerReconciliationResponse,
    PartnerRevenueShareAgreementCreate,
    PartnerRevenueShareAgreementResponse,
    PartnerSettlementGenerateRequest,
    PartnerSettlementStatementResponse,
    PartnerSettlementStatusUpdate,
    PartnerUsageMeterCreate,
    PartnerUsageMeterResponse,
    PartnerResponse,
    RevenueShareTier,
)


class PartnerSecurityError(ValueError):
    """Raised when partner security validation fails."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def _b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _b64decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(payload + padding)


def normalize_domain(value: str) -> str:
    """Return a lower-case hostname from a hostname or URL-like value."""
    candidate = value.strip().lower()
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    host = parsed.hostname or candidate
    return host.strip(".")


def domain_matches(pattern: str, domain: str) -> bool:
    normalized_pattern = normalize_domain(pattern)
    normalized_domain = normalize_domain(domain)
    if normalized_pattern.startswith("*."):
        suffix = normalized_pattern[2:]
        return normalized_domain.endswith(f".{suffix}") and normalized_domain != suffix
    return hmac.compare_digest(normalized_pattern, normalized_domain)


class PartnerSyndicationService:
    """Coordinates partner authorization, token signing, and analytics attribution."""

    token_prefix = "gntv_embed.v1"

    def __init__(self, repo: PartnerRepository, signing_secret: str | None = None) -> None:
        self.repo = repo
        self.signing_secret = signing_secret or settings.EMBED_SIGNING_SECRET.get_secret_value()
        self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(self.signing_secret.encode("utf-8")).digest()))

    def create_partner(self, payload: PartnerCreate, created_by_user_id: int | None) -> PartnerCreateResponse:
        raw_secret = f"gntv_pk_{secrets.token_urlsafe(24)}"
        key_prefix = raw_secret[:14]
        credential = PartnerApiCredential(
            partner_id=uuid4(),
            key_prefix=key_prefix,
            secret_hash=self.hash_api_secret(raw_secret),
            status=PartnerCredentialStatus.ACTIVE,
        )
        branding = self._make_branding(payload.branding, payload.name)
        partner = Partner(
            name=payload.name,
            slug=payload.slug,
            status=payload.status,
            contact_email=payload.contact_email,
            rate_limit_per_minute=payload.rate_limit_per_minute,
            audit_metadata_json=payload.audit_metadata_json,
            created_by_user_id=created_by_user_id,
        )
        created = self.repo.create_partner(partner, branding, credential)
        return PartnerCreateResponse(
            partner=PartnerResponse.model_validate(created),
            credential=PartnerCredentialResponse(
                id=credential.id,
                key_prefix=credential.key_prefix,
                status=credential.status.value,
                created_at=credential.created_at,
            ),
        )

    def list_partners(self) -> list[Partner]:
        return self.repo.list_partners()

    def get_partner(self, partner_id: UUID) -> Partner:
        partner = self.repo.get_partner(partner_id)
        if partner is None:
            raise ValueError("Partner not found")
        return partner

    def add_domain(self, partner_id: UUID, payload: PartnerDomainCreate) -> PartnerDomain:
        self.get_partner(partner_id)
        domain = PartnerDomain(
            partner_id=partner_id,
            domain_pattern=normalize_domain(payload.domain_pattern) if not payload.domain_pattern.startswith("*.") else payload.domain_pattern,
            origin_pattern=payload.origin_pattern,
        )
        return self.repo.create_domain(domain)

    def list_domains(self, partner_id: UUID) -> list[PartnerDomain]:
        self.get_partner(partner_id)
        return self.repo.list_domains(partner_id)

    def add_entitlement(self, partner_id: UUID, payload: PartnerEntitlementCreate) -> PartnerEntitlement:
        self.get_partner(partner_id)
        if payload.starts_at and payload.expires_at and payload.starts_at >= payload.expires_at:
            raise ValueError("starts_at must be before expires_at")
        entitlement = PartnerEntitlement(
            partner_id=partner_id,
            content_type=payload.content_type,
            content_id=payload.content_id,
            scopes_json=payload.scopes,
            starts_at=payload.starts_at,
            expires_at=payload.expires_at,
        )
        return self.repo.create_entitlement(entitlement)

    def list_entitlements(self, partner_id: UUID) -> list[PartnerEntitlement]:
        self.get_partner(partner_id)
        return self.repo.list_entitlements(partner_id)

    def issue_embed_token(self, partner_id: UUID, payload: EmbedTokenRequest) -> EmbedTokenResponse:
        partner = self._load_active_partner(partner_id)
        self._assert_domain_authorized(partner_id, payload.domain, payload.origin)
        entitlement = self.repo.get_active_entitlement(partner_id, payload.content_type, payload.content_id)
        if entitlement is None:
            raise PartnerSecurityError("Partner is not entitled to this content")
        requested_scopes = sorted({scope.strip() for scope in payload.scopes if scope.strip()})
        allowed_scopes = set(entitlement.scopes_json or [])
        if not set(requested_scopes).issubset(allowed_scopes):
            raise PartnerSecurityError("Requested scopes exceed partner entitlement")

        ttl = min(payload.ttl_seconds or settings.EMBED_TOKEN_TTL_SECONDS, settings.EMBED_TOKEN_MAX_TTL_SECONDS)
        issued_at = utc_now()
        expires_at = issued_at + timedelta(seconds=ttl)
        viewer_hash = self._hash_optional(payload.viewer_session_id)
        token_payload: dict[str, Any] = {
            "jti": str(uuid4()),
            "pid": str(partner_id),
            "cty": payload.content_type.value,
            "cid": payload.content_id,
            "dom": normalize_domain(payload.domain),
            "origin": payload.origin,
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
            "sid": payload.playback_session_id,
            "vsh": viewer_hash,
            "scp": requested_scopes,
        }
        token = self._sign_payload(token_payload)
        return EmbedTokenResponse(
            token=token,
            expires_at=expires_at,
            partner_id=partner.id,
            content_type=payload.content_type,
            content_id=payload.content_id,
            scopes=requested_scopes,
            branding=self._branding_response(partner.branding),
        )

    def authorize_embed(self, payload: EmbedAuthorizeRequest) -> EmbedAuthorizeResponse:
        claims = self.verify_token(payload.token)
        partner_id = UUID(str(claims["pid"]))
        partner = self._load_active_partner(partner_id)
        token_domain = str(claims["dom"])
        request_domain = normalize_domain(payload.domain)
        if not hmac.compare_digest(token_domain, request_domain):
            raise PartnerSecurityError("Token domain does not match request domain")
        self._assert_domain_authorized(partner_id, request_domain, payload.origin or claims.get("origin"))
        content_type = PartnerContentType(str(claims["cty"]))
        content_id = str(claims["cid"])
        if self.repo.get_active_entitlement(partner_id, content_type, content_id) is None:
            raise PartnerSecurityError("Partner is not entitled to this content")
        self.repo.record_event(
            PartnerEmbedEvent(
                partner_id=partner_id,
                content_type=content_type,
                content_id=content_id,
                event_type=PartnerEmbedEventType.AUTHORIZE,
                playback_session_id=payload.playback_session_id or claims.get("sid"),
                viewer_session_id_hash=claims.get("vsh"),
                domain=request_domain,
                origin=payload.origin,
                metadata_json={"scopes": claims.get("scp", [])},
            )
        )
        return EmbedAuthorizeResponse(
            authorized=True,
            partner_id=partner_id,
            content_type=content_type,
            content_id=content_id,
            expires_at=datetime.fromtimestamp(int(claims["exp"]), UTC),
            scopes=list(claims.get("scp", [])),
            playback_url=self._playback_url(content_type, content_id, payload.token),
            branding=self._branding_response(partner.branding),
        )

    def record_embed_event(self, payload: PartnerEmbedEventCreate) -> PartnerEmbedEvent:
        claims = self.verify_token(payload.token)
        partner_id = UUID(str(claims["pid"]))
        self._assert_domain_authorized(partner_id, payload.domain, payload.origin)
        event = PartnerEmbedEvent(
            partner_id=partner_id,
            content_type=PartnerContentType(str(claims["cty"])),
            content_id=str(claims["cid"]),
            event_type=payload.event_type,
            playback_session_id=payload.playback_session_id or claims.get("sid"),
            viewer_session_id_hash=claims.get("vsh"),
            domain=normalize_domain(payload.domain),
            origin=payload.origin,
            error_code=payload.error_code,
            metadata_json=payload.metadata_json,
        )
        return self.repo.record_event(event)

    def analytics_overview(self) -> PartnerAnalyticsOverview:
        return PartnerAnalyticsOverview(**self.repo.analytics_overview())

    def create_revenue_share_agreement(
        self, partner_id: UUID, payload: PartnerRevenueShareAgreementCreate, actor_user_id: int | None
    ) -> PartnerRevenueShareAgreementResponse:
        self.get_partner(partner_id)
        tiers_json = None
        if payload.tiers is not None:
            tiers_json = [
                {
                    "threshold_amount": self._money(tier.threshold_amount),
                    "partner_percentage": self._rate(tier.partner_percentage),
                }
                for tier in payload.tiers
            ]
        agreement = PartnerRevenueShareAgreement(
            partner_id=partner_id,
            name=payload.name,
            rule_type=payload.rule_type,
            fixed_partner_percentage=payload.fixed_partner_percentage,
            tiers_json=tiers_json,
            currency=payload.currency.upper(),
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            created_by_user_id=actor_user_id,
        )
        audit = self._audit(
            partner_id=partner_id,
            action=PartnerFinancialAuditAction.AGREEMENT_CREATED,
            actor_user_id=actor_user_id,
            after={"name": payload.name, "rule_type": payload.rule_type.value, "currency": payload.currency.upper()},
        )
        return PartnerRevenueShareAgreementResponse.model_validate(
            self.repo.create_revenue_share_agreement(agreement, audit)
        )

    def list_revenue_share_agreements(self, partner_id: UUID) -> list[PartnerRevenueShareAgreementResponse]:
        self.get_partner(partner_id)
        return [
            PartnerRevenueShareAgreementResponse.model_validate(item)
            for item in self.repo.list_revenue_share_agreements(partner_id)
        ]

    def record_usage_meter(
        self, partner_id: UUID, payload: PartnerUsageMeterCreate, actor_user_id: int | None
    ) -> PartnerUsageMeterResponse:
        self.get_partner(partner_id)
        usage = PartnerUsageMeter(
            partner_id=partner_id,
            content_type=payload.content_type,
            content_id=payload.content_id,
            usage_event_type=payload.usage_event_type,
            quantity=payload.quantity,
            gross_revenue_amount=self._decimal_money(payload.gross_revenue_amount),
            currency=payload.currency.upper(),
            source_event_id=payload.source_event_id,
            idempotency_key=payload.idempotency_key,
            occurred_at=payload.occurred_at,
            metadata_json=payload.metadata_json,
        )
        audit = self._audit(
            partner_id=partner_id,
            action=PartnerFinancialAuditAction.USAGE_RECORDED,
            actor_user_id=actor_user_id,
            after={
                "idempotency_key": payload.idempotency_key,
                "gross_revenue_amount": self._money(payload.gross_revenue_amount),
                "currency": payload.currency.upper(),
            },
        )
        return PartnerUsageMeterResponse.model_validate(self.repo.create_usage_meter(usage, audit))

    def list_usage_metering(
        self,
        partner_id: UUID,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        currency: str | None = None,
    ) -> list[PartnerUsageMeterResponse]:
        self.get_partner(partner_id)
        if period_start and period_end and period_start >= period_end:
            raise ValueError("period_start must be before period_end")
        usage_rows = self.repo.list_usage(
            partner_id, period_start, period_end, currency.upper() if currency else None
        )
        return [PartnerUsageMeterResponse.model_validate(item) for item in usage_rows]

    def generate_settlement(
        self, partner_id: UUID, payload: PartnerSettlementGenerateRequest, actor_user_id: int | None
    ) -> PartnerSettlementStatementResponse:
        self.get_partner(partner_id)
        existing = self.repo.get_settlement_by_idempotency_key(partner_id, payload.idempotency_key)
        if existing is not None:
            return PartnerSettlementStatementResponse.model_validate(existing)
        currency = payload.currency.upper()
        existing_period = self.repo.get_settlement_by_period(
            partner_id, payload.period_start, payload.period_end, currency
        )
        if existing_period is not None:
            return PartnerSettlementStatementResponse.model_validate(existing_period)
        agreement = self.repo.get_active_revenue_share_agreement(
            partner_id, currency, payload.period_start, payload.period_end
        )
        if agreement is None:
            raise PartnerSecurityError("No active revenue-share agreement covers this billing period")
        usage_rows = self.repo.list_usage(partner_id, payload.period_start, payload.period_end, currency)
        gross = sum((Decimal(str(row.gross_revenue_amount)) for row in usage_rows), Decimal("0"))
        partner_share = self._calculate_partner_share(gross, agreement)
        platform_share = self._decimal_money(gross - partner_share)
        adjustment = self._decimal_money(payload.adjustment_amount)
        net = self._decimal_money(partner_share + adjustment)
        calculation_json: dict[str, Any] = {
            "rule_type": agreement.rule_type.value,
            "usage_event_ids": [str(row.id) for row in usage_rows],
            "gross_revenue_amount": self._money(gross),
            "partner_share_amount": self._money(partner_share),
            "platform_share_amount": self._money(platform_share),
            "adjustment_amount": self._money(adjustment),
        }
        statement = PartnerSettlementStatement(
            partner_id=partner_id,
            agreement_id=agreement.id,
            period_start=payload.period_start,
            period_end=payload.period_end,
            currency=currency,
            usage_count=sum(row.quantity for row in usage_rows),
            gross_revenue_amount=self._decimal_money(gross),
            platform_share_amount=platform_share,
            partner_share_amount=self._decimal_money(partner_share),
            adjustment_amount=adjustment,
            net_settlement_amount=net,
            status=SettlementStatus.DRAFT,
            calculation_json=calculation_json,
            idempotency_key=payload.idempotency_key,
            generated_by_user_id=actor_user_id,
        )
        audit = self._audit(
            partner_id=partner_id,
            action=PartnerFinancialAuditAction.SETTLEMENT_GENERATED,
            actor_user_id=actor_user_id,
            after=calculation_json,
        )
        return PartnerSettlementStatementResponse.model_validate(self.repo.create_settlement(statement, audit))

    def list_settlements(self, partner_id: UUID) -> list[PartnerSettlementStatementResponse]:
        self.get_partner(partner_id)
        return [PartnerSettlementStatementResponse.model_validate(item) for item in self.repo.list_settlements(partner_id)]

    def update_settlement_status(
        self,
        partner_id: UUID,
        statement_id: UUID,
        payload: PartnerSettlementStatusUpdate,
        actor_user_id: int | None,
    ) -> PartnerSettlementStatementResponse:
        statement = self.repo.get_settlement(partner_id, statement_id)
        if statement is None:
            raise ValueError("Settlement statement not found")
        before = {"status": statement.status.value}
        self._assert_status_transition(statement.status, payload.status)
        statement.status = payload.status
        now = utc_now()
        if payload.status == SettlementStatus.FINALIZED:
            statement.finalized_at = now
        if payload.status == SettlementStatus.PAID:
            statement.paid_at = now
        audit = self._audit(
            partner_id=partner_id,
            action=PartnerFinancialAuditAction.SETTLEMENT_STATUS_CHANGED,
            actor_user_id=actor_user_id,
            statement_id=statement.id,
            before=before,
            after={"status": payload.status.value, "reason": payload.reason},
        )
        updated = self.repo.update_settlement_status(statement, audit)
        if payload.status == SettlementStatus.FINALIZED:
            self._record_portal_event(
                partner_id=partner_id,
                event_type=PartnerPortalEventType.SETTLEMENT_FINALIZED,
                title="Settlement finalized",
                message="A settlement statement has been finalized and is eligible for payout review.",
                resource_type="settlement",
                resource_id=updated.id,
                payload={
                    "net_settlement_amount": self._money(updated.net_settlement_amount),
                    "currency": updated.currency,
                    "period_start": updated.period_start.isoformat(),
                    "period_end": updated.period_end.isoformat(),
                },
            )
        return PartnerSettlementStatementResponse.model_validate(updated)

    def list_financial_audit_logs(self, partner_id: UUID) -> list[PartnerFinancialAuditLogResponse]:
        self.get_partner(partner_id)
        return [
            PartnerFinancialAuditLogResponse.model_validate(item)
            for item in self.repo.list_financial_audits(partner_id)
        ]

    def _payout_audit(
        self,
        partner_id: UUID,
        action: PartnerPayoutAuditAction,
        actor_user_id: int | None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        payout_account_id: UUID | None = None,
        payout_id: UUID | None = None,
        reconciliation_id: UUID | None = None,
        provider_reference: str | None = None,
    ) -> PartnerPayoutAuditLog:
        return PartnerPayoutAuditLog(
            partner_id=partner_id,
            payout_account_id=payout_account_id,
            payout_id=payout_id,
            reconciliation_id=reconciliation_id,
            action=action,
            actor_user_id=actor_user_id,
            provider_reference=provider_reference,
            before_json=before,
            after_json=after,
        )

    def create_payout_account(
        self, partner_id: UUID, payload: PartnerPayoutAccountCreate, actor_user_id: int | None = None
    ) -> PartnerPayoutAccountResponse:
        self.get_partner(partner_id)
        existing = self.repo.get_payout_account_by_idempotency_key(partner_id, payload.idempotency_key)
        if existing is not None:
            return PartnerPayoutAccountResponse.model_validate(existing)

        account = PartnerPayoutAccount(
            partner_id=partner_id,
            provider_type=payload.provider_type,
            destination_label=payload.destination_label,
            destination_reference=payload.destination_reference,
            encrypted_provider_metadata=self._seal_provider_metadata(payload.provider_metadata),
            currency=payload.currency.upper(),
            status=PartnerPayoutAccountStatus.ENABLED,
            verification_status=payload.verification_status,
            idempotency_key=payload.idempotency_key,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        audit = self._payout_audit(
            partner_id=partner_id,
            action=PartnerPayoutAuditAction.PAYOUT_ACCOUNT_CREATED,
            actor_user_id=actor_user_id,
            after={
                "provider_type": payload.provider_type.value,
                "destination_label": payload.destination_label,
                "currency": payload.currency.upper(),
                "status": PartnerPayoutAccountStatus.ENABLED.value,
                "verification_status": payload.verification_status.value,
            },
        )
        return PartnerPayoutAccountResponse.model_validate(self.repo.create_payout_account(account, audit))

    def update_payout_account(
        self,
        partner_id: UUID,
        account_id: UUID,
        payload: PartnerPayoutAccountUpdate,
        actor_user_id: int | None = None,
    ) -> PartnerPayoutAccountResponse:
        self.get_partner(partner_id)
        account = self.repo.get_payout_account(partner_id, account_id)
        if account is None:
            raise ValueError("Payout account not found")

        before = {
            "destination_label": account.destination_label,
            "status": account.status.value,
            "verification_status": account.verification_status.value,
        }

        if payload.destination_label is not None:
            account.destination_label = payload.destination_label
        if payload.status is not None:
            account.status = payload.status
        if payload.verification_status is not None:
            account.verification_status = payload.verification_status
        if payload.provider_metadata is not None:
            account.encrypted_provider_metadata = self._seal_provider_metadata(payload.provider_metadata)

        account.updated_by_user_id = actor_user_id
        account.updated_at = utc_now()

        after = {
            "destination_label": account.destination_label,
            "status": account.status.value,
            "verification_status": account.verification_status.value,
        }

        audit = self._payout_audit(
            partner_id=partner_id,
            action=PartnerPayoutAuditAction.PAYOUT_ACCOUNT_UPDATED,
            actor_user_id=actor_user_id,
            payout_account_id=account.id,
            before=before,
            after=after,
        )
        return PartnerPayoutAccountResponse.model_validate(self.repo.update_payout_account(account, audit))

    def list_payout_accounts(self, partner_id: UUID) -> list[PartnerPayoutAccountResponse]:
        self.get_partner(partner_id)
        return [PartnerPayoutAccountResponse.model_validate(item) for item in self.repo.list_payout_accounts(partner_id)]

    def get_payout_account(self, partner_id: UUID, account_id: UUID) -> PartnerPayoutAccountResponse:
        self.get_partner(partner_id)
        account = self.repo.get_payout_account(partner_id, account_id)
        if account is None:
            raise ValueError("Payout account not found")
        return PartnerPayoutAccountResponse.model_validate(account)

    def create_payout(
        self, partner_id: UUID, payload: PartnerPayoutCreate, actor_user_id: int | None = None
    ) -> PartnerPayoutResponse:
        self.get_partner(partner_id)
        existing = self.repo.get_payout_by_idempotency_key(partner_id, payload.idempotency_key)
        if existing is not None:
            return PartnerPayoutResponse.model_validate(existing)

        statement = self.repo.get_settlement(partner_id, payload.settlement_id)
        if statement is None:
            raise ValueError("Settlement statement not found")

        if statement.status != SettlementStatus.FINALIZED:
            raise PartnerSecurityError(
                f"Only finalized settlement statements are eligible for payout. Current status: {statement.status.value}"
            )

        existing_settlement_payout = self.repo.get_payout_by_settlement(partner_id, payload.settlement_id)
        if existing_settlement_payout is not None:
            raise PartnerSecurityError("A payout instruction already exists for this settlement statement")

        account = self.repo.get_payout_account(partner_id, payload.payout_account_id)
        if account is None:
            raise ValueError("Payout account not found")
        if account.status != PartnerPayoutAccountStatus.ENABLED:
            raise PartnerSecurityError("Payout account is disabled")
        if account.verification_status != PartnerPayoutVerificationStatus.VERIFIED:
            raise PartnerSecurityError("Payout account must be verified before payout creation")

        if statement.currency.upper() != account.currency.upper():
            raise PartnerSecurityError(
                f"Currency mismatch: statement has {statement.currency}, account has {account.currency}"
            )

        if statement.net_settlement_amount <= Decimal("0"):
            raise PartnerSecurityError("Net settlement amount must be positive for payout")

        payout = PartnerPayout(
            partner_id=partner_id,
            settlement_id=statement.id,
            payout_account_id=account.id,
            amount=self._decimal_money(statement.net_settlement_amount),
            currency=statement.currency.upper(),
            status=PartnerPayoutStatus.PENDING,
            provider_type=account.provider_type,
            idempotency_key=payload.idempotency_key,
            created_by_user_id=actor_user_id,
        )
        audit = self._payout_audit(
            partner_id=partner_id,
            action=PartnerPayoutAuditAction.PAYOUT_CREATED,
            actor_user_id=actor_user_id,
            payout_account_id=account.id,
            after={
                "settlement_id": str(statement.id),
                "payout_account_id": str(account.id),
                "amount": self._money(statement.net_settlement_amount),
                "currency": statement.currency.upper(),
                "status": PartnerPayoutStatus.PENDING.value,
            },
        )
        return PartnerPayoutResponse.model_validate(self.repo.create_payout(payout, audit))

    def approve_payout(
        self, partner_id: UUID, payout_id: UUID, actor_user_id: int | None = None
    ) -> PartnerPayoutResponse:
        self.get_partner(partner_id)
        payout = self.repo.get_payout(partner_id, payout_id)
        if payout is None:
            raise ValueError("Payout not found")

        if payout.status != PartnerPayoutStatus.PENDING:
            raise PartnerSecurityError(
                f"Payout can only be approved from pending status. Current status: {payout.status.value}"
            )

        before = {"status": payout.status.value}
        payout.status = PartnerPayoutStatus.APPROVED
        payout.approved_by_user_id = actor_user_id
        payout.approved_at = utc_now()
        payout.updated_at = utc_now()

        after = {
            "status": payout.status.value,
            "approved_by_user_id": actor_user_id,
            "approved_at": payout.approved_at.isoformat(),
        }

        audit = self._payout_audit(
            partner_id=partner_id,
            action=PartnerPayoutAuditAction.PAYOUT_APPROVED,
            actor_user_id=actor_user_id,
            payout_id=payout.id,
            payout_account_id=payout.payout_account_id,
            before=before,
            after=after,
        )
        updated = self.repo.update_payout(payout, audit)
        self._record_portal_event(
            partner_id=partner_id,
            event_type=PartnerPortalEventType.PAYOUT_APPROVED,
            title="Payout approved",
            message="A payout instruction has been approved for execution.",
            resource_type="payout",
            resource_id=updated.id,
            payload={"status": updated.status.value, "amount": self._money(updated.amount), "currency": updated.currency},
        )
        return PartnerPayoutResponse.model_validate(updated)

    def execute_payout(
        self,
        partner_id: UUID,
        payout_id: UUID,
        payload: PartnerPayoutExecuteRequest,
        actor_user_id: int | None = None,
    ) -> PartnerPayoutResponse:
        self.get_partner(partner_id)
        payout = self.repo.get_payout(partner_id, payout_id)
        if payout is None:
            raise ValueError("Payout not found")

        if payout.status == PartnerPayoutStatus.PAID and payout.provider_execution_key == payload.idempotency_key:
            return PartnerPayoutResponse.model_validate(payout)

        if payout.status != PartnerPayoutStatus.APPROVED:
            raise PartnerSecurityError(
                f"Payout must be approved before execution. Current status: {payout.status.value}"
            )

        statement = self.repo.get_settlement(partner_id, payout.settlement_id)
        if statement is None:
            raise ValueError("Settlement statement associated with payout not found")

        account = self.repo.get_payout_account(partner_id, payout.payout_account_id)
        if account is None:
            raise ValueError("Payout account associated with payout not found")

        payout.provider_execution_key = payload.idempotency_key
        payout.executed_at = utc_now()

        provider = get_payment_provider(payout.provider_type.value)
        req = ProviderPayoutRequest(
            partner_id=partner_id,
            payout_id=payout.id,
            amount=payout.amount,
            currency=payout.currency,
            destination_reference=account.destination_reference,
            destination_routing=None,
            idempotency_key=payload.idempotency_key,
            metadata={"destination_label": account.destination_label},
        )
        result = provider.create_payout(req)

        if result.success:
            before = {"status": payout.status.value}
            payout.status = PartnerPayoutStatus.PAID
            payout.provider_payout_id = result.provider_transaction_id
            payout.provider_transaction_id = result.provider_transaction_id
            payout.paid_at = utc_now()
            payout.updated_at = utc_now()


            after = {
                "status": payout.status.value,
                "provider_payout_id": payout.provider_payout_id,
                "provider_transaction_id": payout.provider_transaction_id,
                "paid_at": payout.paid_at.isoformat(),
            }
            audit = self._payout_audit(
                partner_id=partner_id,
                action=PartnerPayoutAuditAction.PAYOUT_EXECUTED,
                actor_user_id=actor_user_id,
                payout_id=payout.id,
                payout_account_id=payout.payout_account_id,
                provider_reference=result.provider_transaction_id,
                before=before,
                after=after,
            )
            updated = self.repo.update_payout(payout, audit)
            self._record_portal_event(
                partner_id=partner_id,
                event_type=PartnerPortalEventType.PAYOUT_PAID,
                title="Payout paid",
                message="A payout has been marked paid by the payment provider.",
                resource_type="payout",
                resource_id=updated.id,
                severity="success",
                payload={
                    "status": updated.status.value,
                    "amount": self._money(updated.amount),
                    "currency": updated.currency,
                    "provider_transaction_reference": updated.provider_transaction_id,
                },
            )
            return PartnerPayoutResponse.model_validate(updated)
        else:
            before = {"status": payout.status.value}
            payout.status = PartnerPayoutStatus.FAILED
            payout.failure_code = "provider_failure"
            payout.failure_reason = result.error_message
            payout.updated_at = utc_now()

            after = {
                "status": payout.status.value,
                "failure_code": payout.failure_code or "",
                "failure_reason": payout.failure_reason or "",
            }
            audit = self._payout_audit(
                partner_id=partner_id,
                action=PartnerPayoutAuditAction.PAYOUT_FAILED,
                actor_user_id=actor_user_id,
                payout_id=payout.id,
                payout_account_id=payout.payout_account_id,
                before=before,
                after=after,
            )
            updated = self.repo.update_payout(payout, audit)
            self._record_portal_event(
                partner_id=partner_id,
                event_type=PartnerPortalEventType.PAYOUT_FAILED,
                title="Payout failed",
                message="A payout could not be completed by the payment provider.",
                resource_type="payout",
                resource_id=updated.id,
                severity="warning",
                payload={"status": updated.status.value, "failure_code": updated.failure_code},
            )
            return PartnerPayoutResponse.model_validate(updated)

    def cancel_payout(
        self,
        partner_id: UUID,
        payout_id: UUID,
        reason: str | None = None,
        actor_user_id: int | None = None,
    ) -> PartnerPayoutResponse:
        self.get_partner(partner_id)
        payout = self.repo.get_payout(partner_id, payout_id)
        if payout is None:
            raise ValueError("Payout not found")

        if payout.status not in (PartnerPayoutStatus.PENDING, PartnerPayoutStatus.APPROVED):
            raise PartnerSecurityError(
                f"Cannot cancel payout in status: {payout.status.value}"
            )

        before = {"status": payout.status.value}
        payout.status = PartnerPayoutStatus.CANCELLED
        payout.cancelled_at = utc_now()
        payout.failure_reason = reason or "Cancelled by operator"
        payout.updated_at = utc_now()

        after = {
            "status": payout.status.value,
            "reason": payout.failure_reason,
            "cancelled_at": payout.cancelled_at.isoformat(),
        }
        audit = self._payout_audit(
            partner_id=partner_id,
            action=PartnerPayoutAuditAction.PAYOUT_CANCELLED,
            actor_user_id=actor_user_id,
            payout_id=payout.id,
            payout_account_id=payout.payout_account_id,
            before=before,
            after=after,
        )
        return PartnerPayoutResponse.model_validate(self.repo.update_payout(payout, audit))

    def list_payouts(
        self, partner_id: UUID, status: PartnerPayoutStatus | None = None
    ) -> list[PartnerPayoutResponse]:
        self.get_partner(partner_id)
        return [PartnerPayoutResponse.model_validate(item) for item in self.repo.list_payouts(partner_id, status=status)]

    def get_payout(self, partner_id: UUID, payout_id: UUID) -> PartnerPayoutResponse:
        self.get_partner(partner_id)
        payout = self.repo.get_payout(partner_id, payout_id)
        if payout is None:
            raise ValueError("Payout not found")
        return PartnerPayoutResponse.model_validate(payout)

    def reconcile_payout(
        self, partner_id: UUID, payload: PartnerReconciliationCreate, actor_user_id: int | None = None
    ) -> PartnerReconciliationResponse:
        self.get_partner(partner_id)
        existing = self.repo.get_reconciliation_by_idempotency_key(partner_id, payload.idempotency_key)
        if existing is not None:
            return PartnerReconciliationResponse.model_validate(existing)

        matched_payout = self.repo.get_payout_by_provider_transaction(
            partner_id, payload.provider_type, payload.provider_transaction_id
        )
        duplicate_count = self.repo.count_reconciliations_by_provider_transaction(
            payload.provider_type, payload.provider_transaction_id
        )

        if matched_payout is None:
            payouts = self.repo.list_payouts(partner_id)
            for p in payouts:
                if p.provider_payout_id == payload.provider_transaction_id or p.provider_transaction_id == payload.provider_transaction_id:
                    matched_payout = p
                    break

        details: dict[str, Any] = {
            "reported_amount": self._money(payload.reported_amount),
            "reported_currency": payload.reported_currency.upper(),
            "provider_status": payload.provider_status,
        }

        outcome: PartnerPayoutReconciliationOutcome
        if duplicate_count > 0:
            outcome = PartnerPayoutReconciliationOutcome.DUPLICATE_PROVIDER_TRANSACTION
            details["note"] = "Duplicate provider transaction ID already reconciled"
        elif matched_payout is None:
            outcome = PartnerPayoutReconciliationOutcome.UNKNOWN_TRANSACTION
            details["note"] = "No matching payout instruction found in system"
        else:
            if matched_payout.partner_id != partner_id:
                raise ValueError("Payout not found")
            details["expected_amount"] = self._money(matched_payout.amount)
            details["expected_currency"] = matched_payout.currency.upper()
            if payload.provider_status.lower() in ("failed", "rejected", "returned", "reversed"):
                outcome = PartnerPayoutReconciliationOutcome.FAILED_OR_RETURNED
                details["note"] = f"Provider reported failure status: {payload.provider_status}"
                matched_payout.status = PartnerPayoutStatus.REVERSED
                matched_payout.updated_at = utc_now()
                self.repo.db.add(matched_payout)
            elif payload.reported_currency.upper() != matched_payout.currency.upper():
                outcome = PartnerPayoutReconciliationOutcome.CURRENCY_MISMATCH
                details["note"] = f"Currency mismatch: expected {matched_payout.currency}, got {payload.reported_currency}"
            elif self._decimal_money(payload.reported_amount) != self._decimal_money(matched_payout.amount):
                outcome = PartnerPayoutReconciliationOutcome.AMOUNT_MISMATCH
                details["note"] = f"Amount mismatch: expected {self._money(matched_payout.amount)}, got {self._money(payload.reported_amount)}"
            else:
                outcome = PartnerPayoutReconciliationOutcome.MATCHED
                details["note"] = "Deterministic match across amount, currency, and provider transaction"

        reconciliation = PartnerPayoutReconciliation(
            partner_id=partner_id,
            payout_id=matched_payout.id if matched_payout else None,
            provider_type=payload.provider_type,
            provider_transaction_id=payload.provider_transaction_id,
            reported_amount=self._decimal_money(payload.reported_amount),
            reported_currency=payload.reported_currency.upper(),
            provider_status=payload.provider_status,
            outcome=outcome,
            details_json=details,
            idempotency_key=payload.idempotency_key,
            reconciled_by_user_id=actor_user_id,
        )

        audit = self._payout_audit(
            partner_id=partner_id,
            action=PartnerPayoutAuditAction.PAYOUT_RECONCILED,
            actor_user_id=actor_user_id,
            payout_id=matched_payout.id if matched_payout else None,
            reconciliation_id=None,
            provider_reference=payload.provider_transaction_id,
            after={
                "outcome": outcome.value,
                "provider_transaction_id": payload.provider_transaction_id,
                "details": details,
            },
        )
        created = self.repo.create_reconciliation(reconciliation, audit)
        if outcome != PartnerPayoutReconciliationOutcome.MATCHED:
            self._record_portal_event(
                partner_id=partner_id,
                event_type=PartnerPortalEventType.RECONCILIATION_EXCEPTION,
                title="Reconciliation exception",
                message="A payout reconciliation record requires review.",
                resource_type="reconciliation",
                resource_id=created.id,
                severity="warning",
                payload={
                    "outcome": outcome.value,
                    "provider_transaction_reference": payload.provider_transaction_id,
                },
            )
        return PartnerReconciliationResponse.model_validate(created)

    def list_reconciliations(self, partner_id: UUID) -> list[PartnerReconciliationResponse]:
        self.get_partner(partner_id)
        return [
            PartnerReconciliationResponse.model_validate(item)
            for item in self.repo.list_reconciliations(partner_id)
        ]

    def list_payout_audit_logs(self, partner_id: UUID) -> list[PartnerPayoutAuditLogResponse]:
        self.get_partner(partner_id)
        return [
            PartnerPayoutAuditLogResponse.model_validate(item)
            for item in self.repo.list_payout_audits(partner_id)
        ]

    def authenticate_partner_portal_key(self, raw_secret: str) -> Partner:
        if not raw_secret.startswith("gntv_pk_"):
            raise PartnerSecurityError("Valid partner portal key required")
        key_prefix = raw_secret[:14]
        for credential in self.repo.list_credentials_by_prefix(key_prefix):
            if credential.status != PartnerCredentialStatus.ACTIVE:
                continue
            if self.verify_api_secret(raw_secret, credential.secret_hash):
                partner = credential.partner
                if partner is None or partner.status != PartnerStatus.ACTIVE:
                    raise PartnerSecurityError("Partner portal access is not active")
                credential.last_used_at = utc_now()
                self.repo.db.add(credential)
                self.repo.db.commit()
                return partner
        raise PartnerSecurityError("Valid partner portal key required")

    def portal_me(self, partner_id: UUID) -> PartnerPortalMeResponse:
        partner = self.get_partner(partner_id)
        return PartnerPortalMeResponse(
            partner=PartnerResponse.model_validate(partner),
            authorized_domains=[PartnerDomainResponse.model_validate(item) for item in self.repo.list_domains(partner_id)],
            entitlements=[PartnerEntitlementResponse.model_validate(item) for item in self.repo.list_entitlements(partner_id)],
            payout_accounts=[self._portal_account(item) for item in self.repo.list_payout_accounts(partner_id)],
        )

    def portal_overview(
        self,
        partner_id: UUID,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        currency: str | None = None,
    ) -> PartnerPortalOverviewResponse:
        self._validate_range(period_start, period_end)
        currency_code = currency.upper() if currency else None
        usage = self.repo.list_usage(partner_id, period_start, period_end, currency_code)
        settlements = self.repo.list_settlements(partner_id, period_start, period_end, currency_code)
        payouts = self.repo.list_payouts(partner_id, currency=currency_code)
        reconciliations = self.repo.list_reconciliations(partner_id, period_start, period_end)
        domains = [item for item in self.repo.list_domains(partner_id) if item.status.value == "active"]
        entitlements = [item for item in self.repo.list_entitlements(partner_id) if item.status.value == "active"]
        return PartnerPortalOverviewResponse(
            partner_id=partner_id,
            active_entitlements=len(entitlements),
            authorized_domains=len(domains),
            usage_total=sum(item.quantity for item in usage),
            gross_revenue_amount=self._sum_money(item.gross_revenue_amount for item in usage),
            partner_share_amount=self._sum_money(item.partner_share_amount for item in settlements),
            finalized_settlements=sum(1 for item in settlements if item.status in {SettlementStatus.FINALIZED, SettlementStatus.PAID}),
            pending_payouts=sum(1 for item in payouts if item.status in {PartnerPayoutStatus.PENDING, PartnerPayoutStatus.APPROVED, PartnerPayoutStatus.PROCESSING}),
            paid_payouts=sum(1 for item in payouts if item.status == PartnerPayoutStatus.PAID),
            reconciliation_exceptions=sum(1 for item in reconciliations if item.outcome != PartnerPayoutReconciliationOutcome.MATCHED),
            currency=currency_code,
            recent_events=self.portal_events(partner_id, limit=6),
        )

    def portal_usage(
        self,
        partner_id: UUID,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        currency: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PartnerPortalUsageSummaryResponse:
        self._validate_range(period_start, period_end)
        limit = self._limit(limit)
        currency_code = currency.upper() if currency else None
        all_usage = self.repo.list_usage(partner_id, period_start, period_end, currency_code)
        rows = self.repo.list_usage(partner_id, period_start, period_end, currency_code, limit=limit, offset=max(offset, 0))
        by_content: dict[str, dict[str, object]] = {}
        for item in all_usage:
            key = f"{item.content_type.value}:{item.content_id}"
            current = by_content.setdefault(
                key,
                {
                    "content_type": item.content_type.value,
                    "content_id": item.content_id,
                    "usage_total": 0,
                    "gross_revenue_amount": Decimal("0.000000"),
                    "currency": item.currency,
                },
            )
            usage_total = current["usage_total"]
            current["usage_total"] = (usage_total if isinstance(usage_total, int) else 0) + item.quantity
            current["gross_revenue_amount"] = self._decimal_money(
                Decimal(str(current["gross_revenue_amount"])) + Decimal(str(item.gross_revenue_amount))
            )
        return PartnerPortalUsageSummaryResponse(
            partner_id=partner_id,
            usage_total=sum(item.quantity for item in all_usage),
            gross_revenue_amount=self._sum_money(item.gross_revenue_amount for item in all_usage),
            currency=currency_code,
            rows=[PartnerUsageMeterResponse.model_validate(item) for item in rows],
            content_performance=list(by_content.values()),
        )

    def portal_revenue(
        self,
        partner_id: UUID,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        currency: str | None = None,
    ) -> PartnerPortalRevenueSummaryResponse:
        self._validate_range(period_start, period_end)
        currency_code = currency.upper() if currency else None
        settlements = self.repo.list_settlements(partner_id, period_start, period_end, currency_code)
        series: dict[str, dict[str, object]] = {}
        for item in settlements:
            bucket = item.period_start.date().isoformat()
            current = series.setdefault(
                bucket,
                {
                    "date": bucket,
                    "gross_revenue_amount": Decimal("0.000000"),
                    "partner_share_amount": Decimal("0.000000"),
                    "net_settlement_amount": Decimal("0.000000"),
                    "currency": item.currency,
                },
            )
            current["gross_revenue_amount"] = self._decimal_money(
                Decimal(str(current["gross_revenue_amount"])) + Decimal(str(item.gross_revenue_amount))
            )
            current["partner_share_amount"] = self._decimal_money(
                Decimal(str(current["partner_share_amount"])) + Decimal(str(item.partner_share_amount))
            )
            current["net_settlement_amount"] = self._decimal_money(
                Decimal(str(current["net_settlement_amount"])) + Decimal(str(item.net_settlement_amount))
            )
        return PartnerPortalRevenueSummaryResponse(
            partner_id=partner_id,
            gross_revenue_amount=self._sum_money(item.gross_revenue_amount for item in settlements),
            platform_share_amount=self._sum_money(item.platform_share_amount for item in settlements),
            partner_share_amount=self._sum_money(item.partner_share_amount for item in settlements),
            adjustment_amount=self._sum_money(item.adjustment_amount for item in settlements),
            net_settlement_amount=self._sum_money(item.net_settlement_amount for item in settlements),
            currency=currency_code,
            time_series=sorted(series.values(), key=lambda row: str(row["date"])),
        )

    def portal_settlements(
        self,
        partner_id: UUID,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        currency: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PartnerPortalSettlementResponse]:
        self._validate_range(period_start, period_end)
        currency_code = currency.upper() if currency else None
        settlements = self.repo.list_settlements(
            partner_id, period_start, period_end, currency_code, limit=self._limit(limit), offset=max(offset, 0)
        )
        payouts = {item.settlement_id: item.status for item in self.repo.list_payouts(partner_id)}
        return [
            PartnerPortalSettlementResponse.model_validate(item).model_copy(
                update={"payout_status": payouts.get(item.id)}
            )
            for item in settlements
        ]

    def portal_payouts(
        self,
        partner_id: UUID,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        currency: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PartnerPortalPayoutResponse]:
        self._validate_range(period_start, period_end)
        return [
            self._portal_payout(item)
            for item in self.repo.list_payouts(
                partner_id,
                created_after=period_start,
                created_before=period_end,
                currency=currency.upper() if currency else None,
                limit=self._limit(limit),
                offset=max(offset, 0),
            )
        ]

    def portal_reconciliations(
        self,
        partner_id: UUID,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PartnerPortalReconciliationResponse]:
        self._validate_range(period_start, period_end)
        return [
            self._portal_reconciliation(item)
            for item in self.repo.list_reconciliations(
                partner_id, period_start, period_end, limit=self._limit(limit), offset=max(offset, 0)
            )
        ]

    def portal_statements(
        self,
        partner_id: UUID,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        currency: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PartnerPortalStatementResponse]:
        settlements = self.portal_settlements(partner_id, period_start, period_end, currency, limit, offset)
        payouts = self.repo.list_payouts(partner_id)
        reconciliations = self.repo.list_reconciliations(partner_id)
        response: list[PartnerPortalStatementResponse] = []
        for statement in settlements:
            linked_payouts = [p for p in payouts if p.settlement_id == statement.id]
            linked_reconciliations = [
                r for r in reconciliations if r.payout_id in {p.id for p in linked_payouts}
            ]
            response.append(
                PartnerPortalStatementResponse(
                    settlement=statement,
                    payouts=[self._portal_payout(item) for item in linked_payouts],
                    reconciliation=[self._portal_reconciliation(item) for item in linked_reconciliations],
                )
            )
        return response

    def portal_statement_detail(self, partner_id: UUID, statement_id: UUID) -> PartnerPortalStatementResponse:
        statement = self.repo.get_settlement(partner_id, statement_id)
        if statement is None:
            raise ValueError("Settlement statement not found")
        settlement_resp = PartnerPortalSettlementResponse.model_validate(statement)
        payouts = self.repo.list_payouts(partner_id)
        linked_payouts = [p for p in payouts if p.settlement_id == statement.id]
        if linked_payouts:
            settlement_resp.payout_status = linked_payouts[-1].status
        reconciliations = self.repo.list_reconciliations(partner_id)
        linked_reconciliations = [
            r for r in reconciliations if r.payout_id in {p.id for p in linked_payouts}
        ]
        return PartnerPortalStatementResponse(
            settlement=settlement_resp,
            payouts=[self._portal_payout(item) for item in linked_payouts],
            reconciliation=[self._portal_reconciliation(item) for item in linked_reconciliations],
        )

    def add_portal_user(self, partner_id: UUID, user_id: int, role: str = "partner_viewer") -> PartnerPortalUser:
        self.get_partner(partner_id)
        portal_user = PartnerPortalUser(partner_id=partner_id, user_id=user_id, role=role)
        return self.repo.create_portal_user(portal_user)

    def list_portal_users(self, partner_id: UUID) -> list[PartnerPortalUser]:
        self.get_partner(partner_id)
        return self.repo.list_portal_users(partner_id)


    def portal_events(
        self,
        partner_id: UUID,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> list[PartnerPortalEventResponse]:
        self._validate_range(period_start, period_end)
        return [
            PartnerPortalEventResponse.model_validate(item)
            for item in self.repo.list_portal_events(
                partner_id, period_start, period_end, limit=self._limit(limit), offset=max(offset, 0)
            )
        ]

    def portal_export_manifest(
        self,
        partner_id: UUID,
        report_type: str,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        currency: str | None = None,
    ) -> PartnerPortalExportManifestResponse:
        currency_code = currency.upper() if currency else None
        rows: list[dict[str, object]]
        if report_type == "usage":
            rows = [
                {
                    "occurred_at": item.occurred_at.isoformat(),
                    "content_type": item.content_type.value,
                    "content_id": item.content_id,
                    "usage_event_type": item.usage_event_type.value,
                    "quantity": item.quantity,
                    "gross_revenue_amount": self._money(item.gross_revenue_amount),
                    "currency": item.currency,
                }
                for item in self.repo.list_usage(partner_id, period_start, period_end, currency_code)
            ]
        elif report_type in {"settlements", "statements"}:
            rows = [
                {
                    "statement_id": str(item.id),
                    "period_start": item.period_start.isoformat(),
                    "period_end": item.period_end.isoformat(),
                    "status": item.status.value,
                    "usage_count": item.usage_count,
                    "gross_revenue_amount": self._money(item.gross_revenue_amount),
                    "platform_share_amount": self._money(item.platform_share_amount),
                    "partner_share_amount": self._money(item.partner_share_amount),
                    "adjustment_amount": self._money(item.adjustment_amount),
                    "net_settlement_amount": self._money(item.net_settlement_amount),
                    "currency": item.currency,
                }
                for item in self.repo.list_settlements(partner_id, period_start, period_end, currency_code)
            ]
        elif report_type == "payouts":
            rows = [
                {
                    "payout_id": str(item.id),
                    "settlement_id": str(item.settlement_id),
                    "status": item.status.value,
                    "amount": self._money(item.amount),
                    "currency": item.currency,
                    "provider_type": item.provider_type.value,
                    "provider_transaction_reference": item.provider_transaction_id or "",
                    "created_at": item.created_at.isoformat(),
                }
                for item in self.repo.list_payouts(partner_id, currency=currency_code)
            ]
        else:
            raise ValueError("Unsupported report_type")
        return PartnerPortalExportManifestResponse(
            generated_at=utc_now(),
            partner_id=partner_id,
            report_type=report_type,
            currency=currency_code,
            rows=rows,
        )

    def portal_export_csv(self, manifest: PartnerPortalExportManifestResponse) -> str:
        output = StringIO()
        fieldnames = sorted({key for row in manifest.rows for key in row})
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in manifest.rows:
            writer.writerow({key: self._csv_safe(row.get(key, "")) for key in fieldnames})
        return output.getvalue()


    def verify_token(self, token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 4 or ".".join(parts[:2]) != self.token_prefix:
            raise PartnerSecurityError("Invalid embed token format")
        payload_part = parts[2]
        signature = parts[3]
        expected = self._signature(payload_part)
        if not hmac.compare_digest(signature, expected):
            raise PartnerSecurityError("Invalid embed token signature")
        try:
            raw_claims = json.loads(_b64decode(payload_part))
            if not isinstance(raw_claims, dict):
                raise PartnerSecurityError("Invalid embed token payload")
            claims: dict[str, Any] = dict(raw_claims)
        except (json.JSONDecodeError, ValueError) as exc:
            raise PartnerSecurityError("Invalid embed token payload") from exc
        expires_at = int(claims.get("exp", 0))
        if expires_at <= int(utc_now().timestamp()):
            raise PartnerSecurityError("Embed token has expired")
        return claims

    def verify_api_secret(self, raw_secret: str, stored_hash: str) -> bool:
        return hmac.compare_digest(self.hash_api_secret(raw_secret), stored_hash)

    def hash_api_secret(self, raw_secret: str) -> str:
        return hmac.new(self.signing_secret.encode("utf-8"), raw_secret.encode("utf-8"), hashlib.sha256).hexdigest()

    def _sign_payload(self, payload: dict[str, Any]) -> str:
        payload_part = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        return f"{self.token_prefix}.{payload_part}.{self._signature(payload_part)}"

    def _signature(self, payload_part: str) -> str:
        digest = hmac.new(self.signing_secret.encode("utf-8"), payload_part.encode("utf-8"), hashlib.sha256).digest()
        return _b64encode(digest)

    def _load_active_partner(self, partner_id: UUID) -> Partner:
        partner = self.repo.get_active_partner(partner_id)
        if partner is None:
            raise PartnerSecurityError("Partner is not active")
        return partner

    def _assert_domain_authorized(self, partner_id: UUID, domain: str, origin: str | None) -> None:
        domains = self.repo.list_active_domains(partner_id)
        normalized_domain = normalize_domain(domain)
        if not any(domain_matches(item.domain_pattern, normalized_domain) for item in domains):
            raise PartnerSecurityError("Domain is not authorized for this partner")
        if origin:
            normalized_origin = normalize_domain(origin)
            origin_patterns = [item.origin_pattern for item in domains if item.origin_pattern]
            if origin_patterns and not any(domain_matches(pattern, normalized_origin) for pattern in origin_patterns if pattern):
                raise PartnerSecurityError("Origin is not authorized for this partner")

    def _make_branding(self, payload: PartnerBrandingInput | None, fallback_name: str) -> PartnerBranding:
        branding = payload or PartnerBrandingInput(display_name=fallback_name, accent_color="#ff8a00")
        return PartnerBranding(
            partner_id=uuid4(),
            display_name=branding.display_name,
            logo_url=str(branding.logo_url) if branding.logo_url else None,
            accent_color=branding.accent_color,
            theme_json=branding.theme_json,
            show_gntv_attribution=branding.show_gntv_attribution,
        )

    def _hash_optional(self, value: str | None) -> str | None:
        if not value:
            return None
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _branding_response(self, branding: PartnerBranding | None) -> PartnerBrandingResponse | None:
        if branding is None:
            return None
        return PartnerBrandingResponse.model_validate(branding)

    def _playback_url(self, content_type: PartnerContentType, content_id: str, token: str) -> str:
        safe_content_id = content_id.replace("/", "")
        if content_type == PartnerContentType.LIVE_CHANNEL:
            return f"/api/v1/streaming/live/{safe_content_id}/playlist.m3u8?embed_token={token}"
        return f"/api/v1/content/{safe_content_id}/playback?embed_token={token}"

    def _calculate_partner_share(self, gross: Decimal, agreement: PartnerRevenueShareAgreement) -> Decimal:
        if agreement.rule_type == RevenueShareRuleType.FIXED_PERCENTAGE:
            percentage = Decimal(str(agreement.fixed_partner_percentage or Decimal("0")))
            return self._decimal_money(gross * percentage)
        tiers = self._tiers_from_json(agreement.tiers_json or [])
        active_percentage = Decimal("0")
        for tier in tiers:
            if gross >= tier.threshold_amount:
                active_percentage = tier.partner_percentage
        return self._decimal_money(gross * active_percentage)

    def _tiers_from_json(self, tiers_json: list[dict[str, str]]) -> list[RevenueShareTier]:
        return [
            RevenueShareTier(
                threshold_amount=Decimal(tier["threshold_amount"]),
                partner_percentage=Decimal(tier["partner_percentage"]),
            )
            for tier in tiers_json
        ]

    def _assert_status_transition(self, current: SettlementStatus, target: SettlementStatus) -> None:
        allowed: dict[SettlementStatus, set[SettlementStatus]] = {
            SettlementStatus.DRAFT: {SettlementStatus.FINALIZED, SettlementStatus.DISPUTED, SettlementStatus.VOID},
            SettlementStatus.FINALIZED: {SettlementStatus.PAID, SettlementStatus.DISPUTED, SettlementStatus.VOID},
            SettlementStatus.DISPUTED: {SettlementStatus.FINALIZED, SettlementStatus.VOID},
            SettlementStatus.PAID: set(),
            SettlementStatus.VOID: set(),
        }
        if target == current:
            return
        if target not in allowed[current]:
            raise PartnerSecurityError(f"Invalid settlement status transition: {current.value} to {target.value}")

    def _audit(
        self,
        partner_id: UUID,
        action: PartnerFinancialAuditAction,
        actor_user_id: int | None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        statement_id: UUID | None = None,
    ) -> PartnerFinancialAuditLog:
        return PartnerFinancialAuditLog(
            partner_id=partner_id,
            statement_id=statement_id,
            action=action,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=after,
        )

    def _record_portal_event(
        self,
        partner_id: UUID,
        event_type: PartnerPortalEventType,
        title: str,
        message: str,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        severity: str = "info",
        payload: dict[str, object] | None = None,
    ) -> None:
        self.repo.create_portal_event(
            PartnerPortalEvent(
                partner_id=partner_id,
                event_type=event_type,
                title=title,
                message=message,
                resource_type=resource_type,
                resource_id=resource_id,
                severity=severity,
                payload_json=payload,
            )
        )

    def _portal_account(self, account: PartnerPayoutAccount) -> PartnerPortalPayoutAccountSummary:
        return PartnerPortalPayoutAccountSummary(
            id=account.id,
            provider_type=account.provider_type,
            destination_label=account.destination_label,
            masked_destination_reference=self._mask_reference(account.destination_reference),
            currency=account.currency,
            status=account.status,
            verification_status=account.verification_status,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )

    def _portal_payout(self, payout: PartnerPayout) -> PartnerPortalPayoutResponse:
        return PartnerPortalPayoutResponse(
            id=payout.id,
            settlement_id=payout.settlement_id,
            payout_account_id=payout.payout_account_id,
            amount=self._decimal_money(payout.amount),
            currency=payout.currency,
            status=payout.status,
            provider_type=payout.provider_type,
            provider_transaction_reference=payout.provider_transaction_id,
            failure_code=payout.failure_code,
            failure_reason=payout.failure_reason,
            created_at=payout.created_at,
            approved_at=payout.approved_at,
            executed_at=payout.executed_at,
            paid_at=payout.paid_at,
            cancelled_at=payout.cancelled_at,
            updated_at=payout.updated_at,
        )

    def _portal_reconciliation(
        self, reconciliation: PartnerPayoutReconciliation
    ) -> PartnerPortalReconciliationResponse:
        return PartnerPortalReconciliationResponse(
            id=reconciliation.id,
            payout_id=reconciliation.payout_id,
            provider_type=reconciliation.provider_type,
            provider_transaction_reference=reconciliation.provider_transaction_id,
            reported_amount=self._decimal_money(reconciliation.reported_amount),
            reported_currency=reconciliation.reported_currency,
            provider_status=reconciliation.provider_status,
            outcome=reconciliation.outcome,
            details_json=reconciliation.details_json,
            created_at=reconciliation.created_at,
        )

    def _validate_range(self, period_start: datetime | None, period_end: datetime | None) -> None:
        if period_start and period_end and period_start >= period_end:
            raise ValueError("period_start must be before period_end")

    def _limit(self, value: int) -> int:
        return max(1, min(value, 250))

    def _sum_money(self, values: Any) -> Decimal:
        total = Decimal("0")
        for value in values:
            total += Decimal(str(value))
        return self._decimal_money(total)

    def _mask_reference(self, value: str) -> str:
        if len(value) <= 4:
            return "****"
        return f"****{value[-4:]}"

    def _csv_safe(self, value: object) -> object:
        if not isinstance(value, str):
            return value
        if value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
            return f"'{value}"
        return value

    def _decimal_money(self, value: Decimal) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    def _money(self, value: Decimal) -> str:
        return str(self._decimal_money(value))

    def _rate(self, value: Decimal) -> str:
        return str(Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))

    def _seal_provider_metadata(self, value: dict[str, object] | None) -> str | None:
        if value is None:
            return None
        payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return self._fernet.encrypt(payload).decode("ascii")
