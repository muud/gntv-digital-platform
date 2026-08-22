"""Pydantic schemas for Executive Broadcaster Analytics (Module 7 Sprint 7.5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ConcurrencyItem(BaseModel):
    dimension: str = Field(..., description="Dimension label (e.g. channel name, region code, device)")
    id: str | None = Field(default=None, description="Optional UUID or identifier")
    count: int = Field(..., ge=0, description="Active viewer count")
    ratio: float = Field(default=0.0, ge=0.0, le=1.0, description="Share ratio of total viewers")


class TrendPoint(BaseModel):
    timestamp: datetime = Field(..., description="Time marker for trend point")
    value: float | int | None = Field(default=None, description="Observed metric value")


class QoETrendPoint(BaseModel):
    timestamp: datetime
    startup_time_ms: float | None = None
    rebuffer_ratio: float | None = None
    bitrate_bps: float | None = None
    error_count: int = 0


class ConcurrencyAnalyticsResponse(BaseModel):
    total_active_viewers: int = Field(default=0, ge=0)
    peak_concurrency: int = Field(default=0, ge=0)
    by_channel: list[ConcurrencyItem] = Field(default_factory=list)
    by_region: list[ConcurrencyItem] = Field(default_factory=list)
    by_device: list[ConcurrencyItem] = Field(default_factory=list)
    trend: list[TrendPoint] = Field(default_factory=list)


class QoEAnalyticsResponse(BaseModel):
    avg_startup_time_ms: float | None = None
    p50_startup_time_ms: float | None = None
    p95_startup_time_ms: float | None = None
    avg_rebuffer_ratio: float | None = None
    avg_bitrate_bps: float | None = None
    total_playback_errors: int = 0
    failed_sessions_count: int = 0
    total_sessions: int = 0
    qoe_score: float | None = None
    trend: list[QoETrendPoint] = Field(default_factory=list)


class CDNRegionalPerformanceItem(BaseModel):
    region_code: str
    request_count: int = 0
    bandwidth_bytes: int = 0
    cache_hit_ratio: float | None = None
    avg_latency_ms: float | None = None


class CDNTrafficAllocationItem(BaseModel):
    provider_type: str
    edge_hostname: str | None = None
    allocation_percent: float = 0.0
    request_count: int = 0
    bandwidth_bytes: int = 0


class CDNAnalyticsResponse(BaseModel):
    cache_hit_ratio: float | None = None
    origin_offload_ratio: float | None = None
    total_bandwidth_bytes: int = 0
    bandwidth_bps: float | None = None
    avg_provider_latency_ms: float | None = None
    p95_provider_latency_ms: float | None = None
    total_requests: int = 0
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    origin_fetch_count: int = 0
    endpoint_health_counts: dict[str, int] = Field(default_factory=lambda: {"HEALTHY": 0, "DEGRADED": 0, "UNHEALTHY": 0})
    failover_count: int = 0
    regional_performance: list[CDNRegionalPerformanceItem] = Field(default_factory=list)
    traffic_allocation: list[CDNTrafficAllocationItem] = Field(default_factory=list)


class CampaignPerformanceItem(BaseModel):
    campaign_id: UUID | None = None
    campaign_name: str
    impressions: int = 0
    completed_ads: int = 0
    fill_rate: float | None = None
    estimated_revenue_usd: float | None = None


class MonetizationAnalyticsResponse(BaseModel):
    total_ad_impressions: int = 0
    total_completed_ads: int = 0
    ad_fill_rate: float | None = None
    estimated_revenue_usd: float | None = None
    campaign_performance: list[CampaignPerformanceItem] = Field(default_factory=list)
    revenue_by_channel: list[dict[str, Any]] = Field(default_factory=list)
    revenue_by_region: list[dict[str, Any]] = Field(default_factory=list)


class RegionalAnalyticsResponse(BaseModel):
    region_code: str
    active_viewers: int = 0
    total_sessions: int = 0
    avg_startup_latency_ms: float | None = None
    avg_rebuffer_ratio: float | None = None
    cdn_cache_hit_ratio: float | None = None
    cdn_latency_ms: float | None = None
    ad_impressions: int = 0
    estimated_revenue_usd: float | None = None


class ChannelAnalyticsResponse(BaseModel):
    channel_id: UUID
    channel_name: str
    channel_slug: str | None = None
    active_viewers: int = 0
    total_sessions: int = 0
    avg_startup_latency_ms: float | None = None
    avg_rebuffer_ratio: float | None = None
    ad_impressions: int = 0
    estimated_revenue_usd: float | None = None


class ExecutiveOverviewResponse(BaseModel):
    summary: dict[str, Any] = Field(..., description="High-level executive summary metrics")
    concurrency: ConcurrencyAnalyticsResponse
    qoe: QoEAnalyticsResponse
    cdn: CDNAnalyticsResponse
    monetization: MonetizationAnalyticsResponse
    top_regions: list[RegionalAnalyticsResponse] = Field(default_factory=list)
    top_channels: list[ChannelAnalyticsResponse] = Field(default_factory=list)
