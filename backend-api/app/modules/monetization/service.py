"""Compatibility entrypoint for Sprint 7.2 monetization services."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User
from app.modules.monetization.models import TrackingEventStatus
from app.modules.monetization.repository import MonetizationRepository
from app.modules.monetization.schemas import (
    AdBreakCreateRequest,
    AdCampaignCreateRequest,
    AdCreativeCreateRequest,
    TrackingBeaconRequest,
)
from app.modules.monetization.services import (
    HLS_MEDIA_TYPE,
    HlsSegment,
    MonetizationService as AuthoritativeMonetizationService,
    build_ssai_manifest,
    sign_beacon_payload,
)


class MonetizationService:
    """Stable facade used by legacy imports while preserving Sprint 7.2 RBAC."""

    def __init__(self, db_or_repository: Session | MonetizationRepository) -> None:
        self.repository = (
            db_or_repository if isinstance(db_or_repository, MonetizationRepository) else MonetizationRepository(db_or_repository)
        )
        self._service = AuthoritativeMonetizationService(self.repository)

    def create_campaign(self, payload: AdCampaignCreateRequest, user: User | None = None):
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "authentication_required"})
        return self._service.create_campaign(payload, user)

    def get_campaign(self, campaign_id: str | UUID, user: User | None = None):
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "authentication_required"})
        return self._service.get_campaign(campaign_id, user)

    def create_creative(self, payload: AdCreativeCreateRequest, user: User | None = None):
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "authentication_required"})
        return self._service.create_creative(payload, user)

    def add_creative(self, campaign_id: str | UUID, payload: AdCreativeCreateRequest, user: User | None = None):
        payload = payload.model_copy(update={"campaign_id": UUID(str(campaign_id))})
        return self.create_creative(payload, user)

    def create_break(self, payload: AdBreakCreateRequest, user: User | None = None):
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "authentication_required"})
        return self._service.create_break(payload, user)

    def register_ad_break(self, payload: AdBreakCreateRequest, user: User | None = None):
        return self.create_break(payload, user)

    def ssai_manifest(self, target_id: str) -> str:
        return self._service.ssai_manifest(target_id)

    def generate_ssai_manifest_for_target(self, target_id: str) -> str:
        return self.ssai_manifest(target_id)

    def record_beacon(self, payload: TrackingBeaconRequest, user: User | None = None):
        return self._service.record_beacon(payload, user)

    def process_beacon(self, payload: TrackingBeaconRequest, user_id: int | None = None):
        del user_id
        response = self._service.record_beacon(payload)
        status_value = response.status.value if isinstance(response.status, TrackingEventStatus) else str(response.status)
        legacy_status = "idempotent_duplicate" if status_value == TrackingEventStatus.DUPLICATE.value else "success"
        return SimpleNamespace(
            impression_id=response.impression_id,
            event_id=response.event_id,
            status=legacy_status,
            idempotency_outcome=response.idempotency_outcome,
        )


__all__ = ["HLS_MEDIA_TYPE", "HlsSegment", "MonetizationService", "build_ssai_manifest", "sign_beacon_payload"]
