"""FastAPI REST routes for Module 7 Sprint 7.2 Monetization & SSAI."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user, security
from app.models.user import User
from app.modules.monetization.schemas import (
    AdBeaconRequest,
    AdBeaconResponse,
    AdBreakCreateRequest,
    AdBreakResponse,
    AdCampaignCreateRequest,
    AdCampaignResponse,
    AdCreativeCreateRequest,
    AdCreativeResponse,
)
from app.modules.monetization.service import MonetizationService
from app.modules.streaming.api.router import ERROR_RESPONSES

router = APIRouter(prefix="/api/v1/monetization", tags=["Monetization & SSAI"])


def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    if not credentials:
        return None
    try:
        return get_current_user(credentials, db)
    except Exception:
        return None


DbDependency = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


@router.get(
    "/manifest/{target_id}/ssai.m3u8",
    responses={
        200: {
            "content": {"application/vnd.apple.mpegurl": {}},
            "description": "Stitched HLS manifest containing content and SSAI ad segments",
        },
        **ERROR_RESPONSES,
    },
)
def get_ssai_manifest(
    target_id: str,
    db: DbDependency,
) -> Response:
    """Generate SSAI stitched HLS manifest for VOD or Live target."""
    service = MonetizationService(db)
    m3u8_content = service.generate_ssai_manifest_for_target(target_id)
    return Response(content=m3u8_content, media_type="application/vnd.apple.mpegurl")


@router.post(
    "/beacon",
    response_model=AdBeaconResponse,
    status_code=status.HTTP_200_OK,
    responses=ERROR_RESPONSES,
)
def record_beacon(
    payload: AdBeaconRequest,
    db: DbDependency,
    user: OptionalUser,
) -> AdBeaconResponse:
    """Process signed ad impression or tracking beacon idempotently."""
    service = MonetizationService(db)
    user_id = user.id if user else None
    return service.process_beacon(payload, user_id=user_id)


@router.post(
    "/tracking/beacon",
    response_model=AdBeaconResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=ERROR_RESPONSES,
)
def record_tracking_beacon(
    payload: AdBeaconRequest,
    db: DbDependency,
    user: OptionalUser,
) -> AdBeaconResponse:
    """Process the canonical Sprint 7.2 signed tracking beacon contract."""
    service = MonetizationService(db)
    return service.record_beacon(payload, user)


@router.post(
    "/campaigns",
    response_model=AdCampaignResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def create_campaign(
    payload: AdCampaignCreateRequest,
    user: CurrentUser,
    db: DbDependency,
) -> AdCampaignResponse:
    """Create a new ad campaign."""
    service = MonetizationService(db)
    return AdCampaignResponse.model_validate(service.create_campaign(payload, user))


@router.get(
    "/campaigns/{campaign_id}",
    response_model=AdCampaignResponse,
    responses=ERROR_RESPONSES,
)
def get_campaign(
    campaign_id: str,
    user: CurrentUser,
    db: DbDependency,
) -> AdCampaignResponse:
    """Retrieve ad campaign by ID."""
    service = MonetizationService(db)
    return AdCampaignResponse.model_validate(service.get_campaign(campaign_id, user))


@router.post(
    "/campaigns/{campaign_id}/creatives",
    response_model=AdCreativeResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def add_creative(
    campaign_id: str,
    payload: AdCreativeCreateRequest,
    user: CurrentUser,
    db: DbDependency,
) -> AdCreativeResponse:
    """Add a creative to an existing ad campaign."""
    service = MonetizationService(db)
    return AdCreativeResponse.model_validate(service.add_creative(campaign_id, payload, user))


@router.post(
    "/breaks",
    response_model=AdBreakResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def register_ad_break(
    payload: AdBreakCreateRequest,
    user: CurrentUser,
    db: DbDependency,
) -> AdBreakResponse:
    """Register an ad break opportunity for a target content stream."""
    service = MonetizationService(db)
    return AdBreakResponse.model_validate(service.register_ad_break(payload, user))
