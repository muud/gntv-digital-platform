"""FastAPI Router for Executive Broadcaster Analytics (Module 7 Sprint 7.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.analytics.repository import BroadcasterAnalyticsRepository
from app.modules.analytics.schemas import (
    CDNAnalyticsResponse,
    ChannelAnalyticsResponse,
    ConcurrencyAnalyticsResponse,
    ExecutiveOverviewResponse,
    MonetizationAnalyticsResponse,
    QoEAnalyticsResponse,
    RegionalAnalyticsResponse,
)
from app.modules.analytics.service import BroadcasterAnalyticsService

router = APIRouter(prefix="/api/v1/analytics/broadcaster", tags=["Executive Broadcaster Analytics"])


def require_broadcaster_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin or operator role for broadcaster executive analytics."""
    allowed = {"admin", "operator"}
    user_roles = set(current_user.role_names) if hasattr(current_user, "role_names") else set()
    if not (allowed & user_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or operator role required to access executive analytics",
        )
    return current_user


def get_analytics_service(db: Session = Depends(get_db)) -> BroadcasterAnalyticsService:
    repo = BroadcasterAnalyticsRepository(db)
    return BroadcasterAnalyticsService(repo)


AnalyticsServiceDep = Annotated[BroadcasterAnalyticsService, Depends(get_analytics_service)]
AuthDep = Annotated[User, Depends(require_broadcaster_admin)]


def validate_time_range(start_time: datetime | None, end_time: datetime | None) -> None:
    if start_time and end_time and start_time > end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date range: start_time must be before or equal to end_time",
        )


@router.get(
    "/overview",
    response_model=ExecutiveOverviewResponse,
    summary="Get high-level executive broadcaster analytics overview",
)
def get_executive_overview(
    service: AnalyticsServiceDep,
    _user: AuthDep,
    start_time: datetime | None = Query(None, description="Start timestamp filter (ISO 8601)"),
    end_time: datetime | None = Query(None, description="End timestamp filter (ISO 8601)"),
) -> ExecutiveOverviewResponse:
    validate_time_range(start_time, end_time)
    return service.get_executive_overview(start_time=start_time, end_time=end_time)


@router.get(
    "/concurrency",
    response_model=ConcurrencyAnalyticsResponse,
    summary="Get real-time concurrency metrics and distribution",
)
def get_concurrency_analytics(
    service: AnalyticsServiceDep,
    _user: AuthDep,
    channel_id: UUID | None = Query(None, description="Filter by Live Channel UUID"),
    region: str | None = Query(None, description="Filter by region code"),
    device_category: str | None = Query(None, description="Filter by device category"),
    start_time: datetime | None = Query(None, description="Start timestamp filter (ISO 8601)"),
    end_time: datetime | None = Query(None, description="End timestamp filter (ISO 8601)"),
) -> ConcurrencyAnalyticsResponse:
    validate_time_range(start_time, end_time)
    return service.get_concurrency_analytics(
        channel_id=channel_id,
        region=region,
        device_category=device_category,
        start_time=start_time,
        end_time=end_time,
    )


@router.get(
    "/qoe",
    response_model=QoEAnalyticsResponse,
    summary="Get executive QoE performance metrics and trends",
)
def get_qoe_analytics(
    service: AnalyticsServiceDep,
    _user: AuthDep,
    channel_id: UUID | None = Query(None, description="Filter by Live Channel UUID"),
    region: str | None = Query(None, description="Filter by region code"),
    start_time: datetime | None = Query(None, description="Start timestamp filter (ISO 8601)"),
    end_time: datetime | None = Query(None, description="End timestamp filter (ISO 8601)"),
) -> QoEAnalyticsResponse:
    validate_time_range(start_time, end_time)
    return service.get_qoe_analytics(
        channel_id=channel_id,
        region=region,
        start_time=start_time,
        end_time=end_time,
    )


@router.get(
    "/cdn",
    response_model=CDNAnalyticsResponse,
    summary="Get CDN executive metrics, cache hit ratio, offload, and latency",
)
def get_cdn_analytics(
    service: AnalyticsServiceDep,
    _user: AuthDep,
    provider: str | None = Query(None, description="Filter by CDN provider name"),
    region: str | None = Query(None, description="Filter by region code"),
    start_time: datetime | None = Query(None, description="Start timestamp filter (ISO 8601)"),
    end_time: datetime | None = Query(None, description="End timestamp filter (ISO 8601)"),
) -> CDNAnalyticsResponse:
    validate_time_range(start_time, end_time)
    return service.get_cdn_analytics(
        provider=provider,
        region=region,
        start_time=start_time,
        end_time=end_time,
    )


@router.get(
    "/monetization",
    response_model=MonetizationAnalyticsResponse,
    summary="Get monetization, SSAI ad impressions, fill rates, and revenue estimates",
)
def get_monetization_analytics(
    service: AnalyticsServiceDep,
    _user: AuthDep,
    campaign_id: UUID | None = Query(None, description="Filter by Ad Campaign UUID"),
    channel_id: UUID | None = Query(None, description="Filter by Live Channel UUID"),
    region: str | None = Query(None, description="Filter by region code"),
    start_time: datetime | None = Query(None, description="Start timestamp filter (ISO 8601)"),
    end_time: datetime | None = Query(None, description="End timestamp filter (ISO 8601)"),
) -> MonetizationAnalyticsResponse:
    validate_time_range(start_time, end_time)
    return service.get_monetization_analytics(
        campaign_id=campaign_id,
        channel_id=channel_id,
        region=region,
        start_time=start_time,
        end_time=end_time,
    )


@router.get(
    "/regions",
    response_model=list[RegionalAnalyticsResponse],
    summary="Get regional performance metrics breakdown",
)
def get_regional_analytics(
    service: AnalyticsServiceDep,
    _user: AuthDep,
    start_time: datetime | None = Query(None, description="Start timestamp filter (ISO 8601)"),
    end_time: datetime | None = Query(None, description="End timestamp filter (ISO 8601)"),
) -> list[RegionalAnalyticsResponse]:
    validate_time_range(start_time, end_time)
    return service.get_regional_analytics(start_time=start_time, end_time=end_time)


@router.get(
    "/channels",
    response_model=list[ChannelAnalyticsResponse],
    summary="Get channel performance metrics breakdown",
)
def get_channel_analytics(
    service: AnalyticsServiceDep,
    _user: AuthDep,
    start_time: datetime | None = Query(None, description="Start timestamp filter (ISO 8601)"),
    end_time: datetime | None = Query(None, description="End timestamp filter (ISO 8601)"),
) -> list[ChannelAnalyticsResponse]:
    validate_time_range(start_time, end_time)
    return service.get_channel_analytics(start_time=start_time, end_time=end_time)
