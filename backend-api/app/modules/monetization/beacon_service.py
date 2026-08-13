"""Compatibility helpers for signed ad beacons."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.monetization.repository import MonetizationRepository
from app.modules.monetization.schemas import TrackingBeaconRequest, TrackingBeaconResponse
from app.modules.monetization.services import MonetizationService, sign_beacon_payload


class BeaconValidationError(ValueError):
    """Raised when beacon signature validation fails."""


def generate_beacon_signature(
    campaign_id: str,
    session_id: str,
    event_type: str,
    idempotency_key: str,
    secret: str | None = None,
) -> str:
    del campaign_id, secret
    return sign_beacon_payload(idempotency_key=idempotency_key, session_id=session_id, event_type=event_type)


def verify_beacon_signature(request: TrackingBeaconRequest, secret: str | None = None) -> bool:
    del secret
    return request.signature == sign_beacon_payload(
        idempotency_key=request.idempotency_key,
        session_id=request.session_id,
        event_type=str(request.event_type),
    )


class BeaconService:
    def __init__(self, db: Session) -> None:
        self.service = MonetizationService(MonetizationRepository(db))

    def record_beacon(self, request: TrackingBeaconRequest, user_id: int | None = None) -> TrackingBeaconResponse:
        del user_id
        return self.service.record_beacon(request)
