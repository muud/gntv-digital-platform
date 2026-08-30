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
