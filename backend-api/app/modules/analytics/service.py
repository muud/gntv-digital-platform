"""Service layer for Executive Broadcaster Analytics (Module 7 Sprint 7.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.modules.analytics.repository import BroadcasterAnalyticsRepository
from app.modules.analytics.schemas import (
    CDNAnalyticsResponse,
    CDNRegionalPerformanceItem,
    CDNTrafficAllocationItem,
    CampaignPerformanceItem,
    ChannelAnalyticsResponse,
    ConcurrencyAnalyticsResponse,
    ConcurrencyItem,
    ExecutiveOverviewResponse,
    MonetizationAnalyticsResponse,
    QoEAnalyticsResponse,
    QoETrendPoint,
    RegionalAnalyticsResponse,
    TrendPoint,
)


class BroadcasterAnalyticsService:
    """Service handling executive reporting calculations, aggregations, and null degradation."""

    def __init__(self, repository: BroadcasterAnalyticsRepository) -> None:
        self.repo = repository

    def get_concurrency_analytics(
        self,
        channel_id: UUID | None = None,
        region: str | None = None,
        device_category: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> ConcurrencyAnalyticsResponse:
        total_active = self.repo.get_total_active_viewers(channel_id, region, device_category, start_time, end_time)
        peak = self.repo.get_peak_concurrency(channel_id, region, start_time, end_time)
        by_channel_raw = self.repo.get_concurrency_by_channel(region, start_time, end_time)
        by_region_raw = self.repo.get_concurrency_by_region(channel_id, start_time, end_time)
        by_device_raw = self.repo.get_concurrency_by_device(channel_id, region, start_time, end_time)
        trend_raw = self.repo.get_concurrency_trend(channel_id, region, start_time, end_time)

        return ConcurrencyAnalyticsResponse(
            total_active_viewers=total_active,
            peak_concurrency=peak,
            by_channel=[ConcurrencyItem(**item) for item in by_channel_raw],
            by_region=[ConcurrencyItem(**item) for item in by_region_raw],
            by_device=[ConcurrencyItem(**item) for item in by_device_raw],
            trend=[TrendPoint(**item) for item in trend_raw],
        )

    def get_qoe_analytics(
        self,
        channel_id: UUID | None = None,
        region: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> QoEAnalyticsResponse:
        qoe_raw = self.repo.get_qoe_metrics(channel_id, region, start_time, end_time)
        trend_raw = self.repo.get_qoe_trend(channel_id, region, start_time, end_time)

        return QoEAnalyticsResponse(
            avg_startup_time_ms=qoe_raw["avg_startup_time_ms"],
            p50_startup_time_ms=qoe_raw["p50_startup_time_ms"],
            p95_startup_time_ms=qoe_raw["p95_startup_time_ms"],
            avg_rebuffer_ratio=qoe_raw["avg_rebuffer_ratio"],
            avg_bitrate_bps=qoe_raw["avg_bitrate_bps"],
            total_playback_errors=qoe_raw["total_playback_errors"],
            failed_sessions_count=qoe_raw["failed_sessions_count"],
            total_sessions=qoe_raw["total_sessions"],
            qoe_score=qoe_raw["qoe_score"],
            trend=[QoETrendPoint(**item) for item in trend_raw],
        )

    def get_cdn_analytics(
        self,
        provider: str | None = None,
        region: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> CDNAnalyticsResponse:
        cdn_raw = self.repo.get_cdn_metrics(provider, region, start_time, end_time)

        return CDNAnalyticsResponse(
            cache_hit_ratio=cdn_raw["cache_hit_ratio"],
            origin_offload_ratio=cdn_raw["origin_offload_ratio"],
            total_bandwidth_bytes=cdn_raw["total_bandwidth_bytes"],
            bandwidth_bps=cdn_raw["bandwidth_bps"],
            avg_provider_latency_ms=cdn_raw["avg_provider_latency_ms"],
            p95_provider_latency_ms=cdn_raw["p95_provider_latency_ms"],
            total_requests=cdn_raw["total_requests"],
            cache_hit_count=cdn_raw["cache_hit_count"],
            cache_miss_count=cdn_raw["cache_miss_count"],
            origin_fetch_count=cdn_raw["origin_fetch_count"],
            endpoint_health_counts=cdn_raw["endpoint_health_counts"],
            failover_count=cdn_raw["failover_count"],
            regional_performance=[CDNRegionalPerformanceItem(**item) for item in cdn_raw["regional_performance"]],
            traffic_allocation=[CDNTrafficAllocationItem(**item) for item in cdn_raw["traffic_allocation"]],
        )

    def get_monetization_analytics(
        self,
        campaign_id: UUID | None = None,
        channel_id: UUID | None = None,
        region: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> MonetizationAnalyticsResponse:
        mon_raw = self.repo.get_monetization_metrics(campaign_id, channel_id, region, start_time, end_time)

        return MonetizationAnalyticsResponse(
            total_ad_impressions=mon_raw["total_ad_impressions"],
            total_completed_ads=mon_raw["total_completed_ads"],
            ad_fill_rate=mon_raw["ad_fill_rate"],
            estimated_revenue_usd=mon_raw["estimated_revenue_usd"],
            campaign_performance=[CampaignPerformanceItem(**item) for item in mon_raw["campaign_performance"]],
            revenue_by_channel=mon_raw["revenue_by_channel"],
            revenue_by_region=mon_raw["revenue_by_region"],
        )

    def get_regional_analytics(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[RegionalAnalyticsResponse]:
        raw_list = self.repo.get_regional_analytics(start_time, end_time)
        return [RegionalAnalyticsResponse(**item) for item in raw_list]

    def get_channel_analytics(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[ChannelAnalyticsResponse]:
        raw_list = self.repo.get_channel_analytics(start_time, end_time)
        return [ChannelAnalyticsResponse(**item) for item in raw_list]

    def get_executive_overview(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> ExecutiveOverviewResponse:
        concurrency = self.get_concurrency_analytics(start_time=start_time, end_time=end_time)
        qoe = self.get_qoe_analytics(start_time=start_time, end_time=end_time)
        cdn = self.get_cdn_analytics(start_time=start_time, end_time=end_time)
        monetization = self.get_monetization_analytics(start_time=start_time, end_time=end_time)
        top_regions = self.get_regional_analytics(start_time=start_time, end_time=end_time)
        top_channels = self.get_channel_analytics(start_time=start_time, end_time=end_time)

        # High level executive summary dict
        cdn_status = "HEALTHY"
        if cdn.endpoint_health_counts.get("UNHEALTHY", 0) > 0:
            cdn_status = "UNHEALTHY"
        elif cdn.endpoint_health_counts.get("DEGRADED", 0) > 0:
            cdn_status = "DEGRADED"

        summary: dict[str, Any] = {
            "active_viewers": concurrency.total_active_viewers,
            "peak_concurrency": concurrency.peak_concurrency,
            "qoe_score": qoe.qoe_score,
            "cdn_offload_ratio": cdn.origin_offload_ratio,
            "cdn_health_status": cdn_status,
            "total_failovers": cdn.failover_count,
            "ad_impressions": monetization.total_ad_impressions,
            "estimated_revenue_usd": monetization.estimated_revenue_usd,
        }

        return ExecutiveOverviewResponse(
            summary=summary,
            concurrency=concurrency,
            qoe=qoe,
            cdn=cdn,
            monetization=monetization,
            top_regions=top_regions,
            top_channels=top_channels,
        )
