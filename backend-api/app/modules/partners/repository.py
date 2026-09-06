"""Persistence helpers for partner syndication."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.modules.partners.models import (
    Partner,
    PartnerApiCredential,
    PartnerBranding,
    PartnerContentType,
    PartnerDomain,
    PartnerDomainStatus,
    PartnerEmbedEvent,
    PartnerEmbedEventType,
    PartnerEntitlement,
    PartnerEntitlementStatus,
    PartnerFinancialAuditLog,
    PartnerPayout,
    PartnerPayoutAccount,
    PartnerPayoutAuditLog,
    PartnerPayoutProviderType,
    PartnerPayoutReconciliation,
    PartnerPayoutStatus,
    PartnerRevenueShareAgreement,
    PartnerSettlementStatement,
    PartnerUsageMeter,
    PartnerStatus,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class PartnerRepository:
    """Repository boundary for partner management and embed attribution."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_partner(self, partner: Partner, branding: PartnerBranding | None, credential: PartnerApiCredential) -> Partner:
        self.db.add(partner)
        self.db.flush()
        if branding is not None:
            branding.partner_id = partner.id
            self.db.add(branding)
        credential.partner_id = partner.id
        self.db.add(credential)
        self.db.commit()
        return self.get_partner(partner.id) or partner

    def list_partners(self) -> list[Partner]:
        return (
            self.db.query(Partner)
            .options(joinedload(Partner.branding))
            .order_by(Partner.created_at.desc())
            .all()
        )

    def get_partner(self, partner_id: UUID) -> Partner | None:
        return (
            self.db.query(Partner)
            .options(joinedload(Partner.branding))
            .filter(Partner.id == partner_id)
            .one_or_none()
        )

    def get_active_partner(self, partner_id: UUID) -> Partner | None:
        return (
            self.db.query(Partner)
            .options(joinedload(Partner.branding), joinedload(Partner.domains), joinedload(Partner.entitlements))
            .filter(Partner.id == partner_id, Partner.status == PartnerStatus.ACTIVE)
            .one_or_none()
        )

    def create_domain(self, domain: PartnerDomain) -> PartnerDomain:
        self.db.add(domain)
        self.db.commit()
        self.db.refresh(domain)
        return domain

    def list_domains(self, partner_id: UUID) -> list[PartnerDomain]:
        return (
            self.db.query(PartnerDomain)
            .filter(PartnerDomain.partner_id == partner_id)
            .order_by(PartnerDomain.created_at.desc())
            .all()
        )

    def list_active_domains(self, partner_id: UUID) -> list[PartnerDomain]:
        return (
            self.db.query(PartnerDomain)
            .filter(PartnerDomain.partner_id == partner_id, PartnerDomain.status == PartnerDomainStatus.ACTIVE)
            .all()
        )

    def create_entitlement(self, entitlement: PartnerEntitlement) -> PartnerEntitlement:
        self.db.add(entitlement)
        self.db.commit()
        self.db.refresh(entitlement)
        return entitlement

    def list_entitlements(self, partner_id: UUID) -> list[PartnerEntitlement]:
        return (
            self.db.query(PartnerEntitlement)
            .filter(PartnerEntitlement.partner_id == partner_id)
            .order_by(PartnerEntitlement.created_at.desc())
            .all()
        )

    def get_active_entitlement(
        self,
        partner_id: UUID,
        content_type: PartnerContentType,
        content_id: str,
        now: datetime | None = None,
    ) -> PartnerEntitlement | None:
        observed_at = now or utc_now()
        return (
            self.db.query(PartnerEntitlement)
            .filter(
                PartnerEntitlement.partner_id == partner_id,
                PartnerEntitlement.content_type == content_type,
                PartnerEntitlement.content_id == content_id,
                PartnerEntitlement.status == PartnerEntitlementStatus.ACTIVE,
                ((PartnerEntitlement.starts_at.is_(None)) | (PartnerEntitlement.starts_at <= observed_at)),
                ((PartnerEntitlement.expires_at.is_(None)) | (PartnerEntitlement.expires_at > observed_at)),
            )
            .one_or_none()
        )

    def record_event(self, event: PartnerEmbedEvent) -> PartnerEmbedEvent:
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def analytics_overview(self) -> dict[str, int]:
        partner_count = self.db.query(func.count(Partner.id)).scalar() or 0
        active_partner_count = (
            self.db.query(func.count(Partner.id)).filter(Partner.status == PartnerStatus.ACTIVE).scalar() or 0
        )
        event_rows = (
            self.db.query(PartnerEmbedEvent.event_type, func.count(PartnerEmbedEvent.id))
            .group_by(PartnerEmbedEvent.event_type)
            .all()
        )
        event_counts: dict[PartnerEmbedEventType, int] = {event_type: int(count) for event_type, count in event_rows}
        return {
            "partner_count": int(partner_count),
            "active_partner_count": int(active_partner_count),
            "authorized_embed_count": int(event_counts.get(PartnerEmbedEventType.AUTHORIZE, 0)),
            "playback_start_count": int(event_counts.get(PartnerEmbedEventType.PLAYBACK_START, 0)),
            "completion_count": int(event_counts.get(PartnerEmbedEventType.PLAYBACK_COMPLETE, 0)),
            "error_count": int(event_counts.get(PartnerEmbedEventType.PLAYBACK_ERROR, 0)),
        }

    def create_revenue_share_agreement(
        self, agreement: PartnerRevenueShareAgreement, audit: PartnerFinancialAuditLog
    ) -> PartnerRevenueShareAgreement:
        self.db.add(agreement)
        self.db.flush()
        audit.partner_id = agreement.partner_id
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(agreement)
        return agreement

    def list_revenue_share_agreements(self, partner_id: UUID) -> list[PartnerRevenueShareAgreement]:
        return (
            self.db.query(PartnerRevenueShareAgreement)
            .filter(PartnerRevenueShareAgreement.partner_id == partner_id)
            .order_by(PartnerRevenueShareAgreement.starts_at.desc())
            .all()
        )

    def get_active_revenue_share_agreement(
        self, partner_id: UUID, currency: str, period_start: datetime, period_end: datetime
    ) -> PartnerRevenueShareAgreement | None:
        return (
            self.db.query(PartnerRevenueShareAgreement)
            .filter(
                PartnerRevenueShareAgreement.partner_id == partner_id,
                PartnerRevenueShareAgreement.currency == currency,
                PartnerRevenueShareAgreement.is_active.is_(True),
                PartnerRevenueShareAgreement.starts_at <= period_start,
                (
                    (PartnerRevenueShareAgreement.ends_at.is_(None))
                    | (PartnerRevenueShareAgreement.ends_at >= period_end)
                ),
            )
            .order_by(PartnerRevenueShareAgreement.starts_at.desc())
            .first()
        )

    def get_usage_by_idempotency_key(self, partner_id: UUID, idempotency_key: str) -> PartnerUsageMeter | None:
        return (
            self.db.query(PartnerUsageMeter)
            .filter(PartnerUsageMeter.partner_id == partner_id, PartnerUsageMeter.idempotency_key == idempotency_key)
            .one_or_none()
        )

    def create_usage_meter(self, usage: PartnerUsageMeter, audit: PartnerFinancialAuditLog) -> PartnerUsageMeter:
        existing = self.get_usage_by_idempotency_key(usage.partner_id, usage.idempotency_key)
        if existing is not None:
            return existing
        self.db.add(usage)
        self.db.flush()
        audit.partner_id = usage.partner_id
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(usage)
        return usage

    def list_usage(
        self,
        partner_id: UUID,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        currency: str | None = None,
    ) -> list[PartnerUsageMeter]:
        query = self.db.query(PartnerUsageMeter).filter(PartnerUsageMeter.partner_id == partner_id)
        if period_start is not None:
            query = query.filter(PartnerUsageMeter.occurred_at >= period_start)
        if period_end is not None:
            query = query.filter(PartnerUsageMeter.occurred_at < period_end)
        if currency is not None:
            query = query.filter(PartnerUsageMeter.currency == currency)
        return query.order_by(PartnerUsageMeter.occurred_at.asc()).all()

    def get_settlement_by_idempotency_key(
        self, partner_id: UUID, idempotency_key: str
    ) -> PartnerSettlementStatement | None:
        return (
            self.db.query(PartnerSettlementStatement)
            .filter(
                PartnerSettlementStatement.partner_id == partner_id,
                PartnerSettlementStatement.idempotency_key == idempotency_key,
            )
            .one_or_none()
        )

    def get_settlement_by_period(
        self, partner_id: UUID, period_start: datetime, period_end: datetime, currency: str
    ) -> PartnerSettlementStatement | None:
        return (
            self.db.query(PartnerSettlementStatement)
            .filter(
                PartnerSettlementStatement.partner_id == partner_id,
                PartnerSettlementStatement.period_start == period_start,
                PartnerSettlementStatement.period_end == period_end,
                PartnerSettlementStatement.currency == currency,
            )
            .one_or_none()
        )

    def create_settlement(
        self, statement: PartnerSettlementStatement, audit: PartnerFinancialAuditLog
    ) -> PartnerSettlementStatement:
        existing = self.get_settlement_by_idempotency_key(statement.partner_id, statement.idempotency_key)
        if existing is not None:
            return existing
        self.db.add(statement)
        self.db.flush()
        audit.partner_id = statement.partner_id
        audit.statement_id = statement.id
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(statement)
        return statement

    def list_settlements(self, partner_id: UUID) -> list[PartnerSettlementStatement]:
        return (
            self.db.query(PartnerSettlementStatement)
            .filter(PartnerSettlementStatement.partner_id == partner_id)
            .order_by(PartnerSettlementStatement.period_start.desc())
            .all()
        )

    def get_settlement(self, partner_id: UUID, statement_id: UUID) -> PartnerSettlementStatement | None:
        return (
            self.db.query(PartnerSettlementStatement)
            .filter(
                PartnerSettlementStatement.partner_id == partner_id,
                PartnerSettlementStatement.id == statement_id,
            )
            .one_or_none()
        )

    def update_settlement_status(
        self, statement: PartnerSettlementStatement, audit: PartnerFinancialAuditLog
    ) -> PartnerSettlementStatement:
        self.db.add(statement)
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(statement)
        return statement

    def list_financial_audits(self, partner_id: UUID) -> list[PartnerFinancialAuditLog]:
        return (
            self.db.query(PartnerFinancialAuditLog)
            .filter(PartnerFinancialAuditLog.partner_id == partner_id)
            .order_by(PartnerFinancialAuditLog.created_at.desc())
            .all()
        )

    def get_payout_account_by_idempotency_key(
        self, partner_id: UUID, idempotency_key: str
    ) -> PartnerPayoutAccount | None:
        return (
            self.db.query(PartnerPayoutAccount)
            .filter(
                PartnerPayoutAccount.partner_id == partner_id,
                PartnerPayoutAccount.idempotency_key == idempotency_key,
            )
            .one_or_none()
        )

    def create_payout_account(
        self, account: PartnerPayoutAccount, audit: PartnerPayoutAuditLog
    ) -> PartnerPayoutAccount:
        existing = self.get_payout_account_by_idempotency_key(account.partner_id, account.idempotency_key)
        if existing is not None:
            return existing
        self.db.add(account)
        self.db.flush()
        audit.partner_id = account.partner_id
        audit.payout_account_id = account.id
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(account)
        return account

    def list_payout_accounts(self, partner_id: UUID) -> list[PartnerPayoutAccount]:
        return (
            self.db.query(PartnerPayoutAccount)
            .filter(PartnerPayoutAccount.partner_id == partner_id)
            .order_by(PartnerPayoutAccount.created_at.desc())
            .all()
        )

    def get_payout_account(self, partner_id: UUID, account_id: UUID) -> PartnerPayoutAccount | None:
        return (
            self.db.query(PartnerPayoutAccount)
            .filter(PartnerPayoutAccount.partner_id == partner_id, PartnerPayoutAccount.id == account_id)
            .one_or_none()
        )

    def update_payout_account(
        self, account: PartnerPayoutAccount, audit: PartnerPayoutAuditLog
    ) -> PartnerPayoutAccount:
        self.db.add(account)
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(account)
        return account

    def get_payout_by_idempotency_key(self, partner_id: UUID, idempotency_key: str) -> PartnerPayout | None:
        return (
            self.db.query(PartnerPayout)
            .filter(PartnerPayout.partner_id == partner_id, PartnerPayout.idempotency_key == idempotency_key)
            .one_or_none()
        )

    def get_payout_by_settlement(self, partner_id: UUID, settlement_id: UUID) -> PartnerPayout | None:
        return (
            self.db.query(PartnerPayout)
            .filter(PartnerPayout.partner_id == partner_id, PartnerPayout.settlement_id == settlement_id)
            .one_or_none()
        )

    def create_payout(self, payout: PartnerPayout, audit: PartnerPayoutAuditLog) -> PartnerPayout:
        existing = self.get_payout_by_idempotency_key(payout.partner_id, payout.idempotency_key)
        if existing is not None:
            return existing
        existing_settlement = self.get_payout_by_settlement(payout.partner_id, payout.settlement_id)
        if existing_settlement is not None:
            return existing_settlement
        self.db.add(payout)
        self.db.flush()
        audit.partner_id = payout.partner_id
        audit.payout_id = payout.id
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(payout)
        return payout

    def list_payouts(self, partner_id: UUID, status: PartnerPayoutStatus | None = None) -> list[PartnerPayout]:
        query = self.db.query(PartnerPayout).filter(PartnerPayout.partner_id == partner_id)
        if status is not None:
            query = query.filter(PartnerPayout.status == status)
        return query.order_by(PartnerPayout.created_at.desc()).all()

    def get_payout(self, partner_id: UUID, payout_id: UUID) -> PartnerPayout | None:
        return (
            self.db.query(PartnerPayout)
            .filter(PartnerPayout.partner_id == partner_id, PartnerPayout.id == payout_id)
            .one_or_none()
        )

    def get_payout_by_provider_transaction(
        self, partner_id: UUID, provider_type: PartnerPayoutProviderType, provider_transaction_id: str
    ) -> PartnerPayout | None:
        return (
            self.db.query(PartnerPayout)
            .filter(
                PartnerPayout.partner_id == partner_id,
                PartnerPayout.provider_type == provider_type,
                PartnerPayout.provider_transaction_id == provider_transaction_id,
            )
            .one_or_none()
        )

    def count_reconciliations_by_provider_transaction(
        self, provider_type: PartnerPayoutProviderType, provider_transaction_id: str
    ) -> int:
        return int(
            self.db.query(func.count(PartnerPayoutReconciliation.id))
            .filter(
                PartnerPayoutReconciliation.provider_type == provider_type,
                PartnerPayoutReconciliation.provider_transaction_id == provider_transaction_id,
            )
            .scalar()
            or 0
        )

    def update_payout(
        self,
        payout: PartnerPayout,
        audit: PartnerPayoutAuditLog,
        settlement: PartnerSettlementStatement | None = None,
    ) -> PartnerPayout:
        self.db.add(payout)
        if settlement is not None:
            self.db.add(settlement)
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(payout)
        return payout

    def get_reconciliation_by_idempotency_key(
        self, partner_id: UUID, idempotency_key: str
    ) -> PartnerPayoutReconciliation | None:
        return (
            self.db.query(PartnerPayoutReconciliation)
            .filter(
                PartnerPayoutReconciliation.partner_id == partner_id,
                PartnerPayoutReconciliation.idempotency_key == idempotency_key,
            )
            .one_or_none()
        )

    def create_reconciliation(
        self, reconciliation: PartnerPayoutReconciliation, audit: PartnerPayoutAuditLog
    ) -> PartnerPayoutReconciliation:
        existing = self.get_reconciliation_by_idempotency_key(
            reconciliation.partner_id, reconciliation.idempotency_key
        )
        if existing is not None:
            return existing
        self.db.add(reconciliation)
        self.db.flush()
        audit.partner_id = reconciliation.partner_id
        audit.payout_id = reconciliation.payout_id
        audit.reconciliation_id = reconciliation.id
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(reconciliation)
        return reconciliation

    def list_reconciliations(self, partner_id: UUID) -> list[PartnerPayoutReconciliation]:
        return (
            self.db.query(PartnerPayoutReconciliation)
            .filter(PartnerPayoutReconciliation.partner_id == partner_id)
            .order_by(PartnerPayoutReconciliation.created_at.desc())
            .all()
        )

    def list_payout_audits(self, partner_id: UUID) -> list[PartnerPayoutAuditLog]:
        return (
            self.db.query(PartnerPayoutAuditLog)
            .filter(PartnerPayoutAuditLog.partner_id == partner_id)
            .order_by(PartnerPayoutAuditLog.created_at.desc())
            .all()
        )
