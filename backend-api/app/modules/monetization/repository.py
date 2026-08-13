"""Persistence repository for monetization and SSAI state."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.monetization.models import AdBreak, AdCampaign, AdCreative, AdImpression, AdTrackingEvent


class MonetizationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add_campaign(self, campaign: AdCampaign) -> AdCampaign:
        self.db.add(campaign)
        self.db.flush()
        return campaign

    def campaign(self, campaign_id: UUID) -> AdCampaign | None:
        return self.db.get(AdCampaign, campaign_id)

    def list_campaigns(self) -> list[AdCampaign]:
        return list(self.db.execute(select(AdCampaign).order_by(AdCampaign.created_at.desc())).scalars().all())

    def add_creative(self, creative: AdCreative) -> AdCreative:
        self.db.add(creative)
        self.db.flush()
        return creative

    def creative(self, creative_id: UUID) -> AdCreative | None:
        return self.db.get(AdCreative, creative_id)

    def creatives_for_campaign(self, campaign_id: UUID) -> list[AdCreative]:
        return list(
            self.db.execute(select(AdCreative).where(AdCreative.campaign_id == campaign_id).order_by(AdCreative.created_at))
            .scalars()
            .all()
        )

    def add_break(self, ad_break: AdBreak) -> AdBreak:
        self.db.add(ad_break)
        self.db.flush()
        return ad_break

    def break_by_id(self, break_id: UUID) -> AdBreak | None:
        return self.db.get(AdBreak, break_id)

    def breaks_for_target(self, target_id: str) -> list[AdBreak]:
        return list(
            self.db.execute(
                select(AdBreak)
                .where(AdBreak.target_id == target_id, AdBreak.is_active.is_(True))
                .order_by(AdBreak.time_offset_seconds)
            )
            .scalars()
            .all()
        )

    def impression_by_idempotency_key(self, key: str) -> AdImpression | None:
        return self.db.execute(select(AdImpression).where(AdImpression.idempotency_key == key)).scalar_one_or_none()

    def add_impression(self, impression: AdImpression) -> AdImpression:
        self.db.add(impression)
        self.db.flush()
        return impression

    def add_tracking_event(self, event: AdTrackingEvent) -> AdTrackingEvent:
        self.db.add(event)
        self.db.flush()
        return event

    create_campaign = add_campaign
    get_campaign = campaign
    create_creative = add_creative
    create_ad_break = add_break
    get_ad_breaks_for_target = breaks_for_target
