"""CDN observability, analytics aggregation, and traffic optimization services."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from uuid import UUID

from app.modules.cdn.models import (
    CDNEndpoint,
    CDNEndpointMetric,
    CDNHealthStatus,
    CDNMetricGranularity,
    CDNProviderMetric,
)
from app.modules.cdn.repository import CDNRepository
from app.modules.cdn.schemas import (
    CDNEndpointAnalytics,
    CDNEndpointMetricCreate,
    CDNEndpointMetricResponse,
    CDNFailoverEventCreate,
    CDNFailoverEventResponse,
    CDNMetricSummary,
    CDNObservabilityOverview,
    CDNOperationalMetrics,
    CDNProviderAnalytics,
    CDNRegionAnalytics,
    CDNRoutingEventResponse,
    CDNTrafficAllocationOverrideCreate,
    CDNTrafficAllocationOverrideResponse,
    CDNTrafficAllocationRecommendation,
    CDNTrafficAllocationResponse,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _clamp_percent(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


class CDNObservabilityService:
    """Aggregates CDN metrics and produces deterministic routing recommendations."""

    def __init__(self, repository: CDNRepository) -> None:
        self.repository = repository

    def ingest_endpoint_metric(self, data: CDNEndpointMetricCreate) -> CDNEndpointMetricResponse:
        metric = self.repository.create_endpoint_metric(data)
        self._store_provider_rollup(metric)
        return CDNEndpointMetricResponse.model_validate(metric)

    def overview(self, region_code: str | None = None) -> CDNObservabilityOverview:
        endpoints = self.repository.list_endpoints()
        metrics = self.repository.list_endpoint_metrics(region_code=region_code)
        failovers = self.repository.list_failover_events()
        summary = self._summarize(metrics)
        return CDNObservabilityOverview(
            generated_at=utc_now(),
            provider_count=len({endpoint.provider_type for endpoint in endpoints}),
            endpoint_count=len(endpoints),
            healthy_endpoint_count=sum(1 for endpoint in endpoints if endpoint.health_status == CDNHealthStatus.HEALTHY),
            degraded_endpoint_count=sum(1 for endpoint in endpoints if endpoint.health_status == CDNHealthStatus.DEGRADED),
            unhealthy_endpoint_count=sum(1 for endpoint in endpoints if endpoint.health_status == CDNHealthStatus.UNHEALTHY),
            failover_count=len(failovers),
            metrics=summary,
        )

    def provider_analytics(self, region_code: str | None = None) -> list[CDNProviderAnalytics]:
        endpoints = self.repository.list_endpoints()
        metrics = self.repository.list_endpoint_metrics(region_code=region_code)
        by_provider: dict[tuple[str, str], list[CDNEndpointMetric]] = defaultdict(list)
        for metric in metrics:
            by_provider[(metric.provider_type.value, metric.region_code)].append(metric)

        results: list[CDNProviderAnalytics] = []
        for (provider_value, region), grouped_metrics in sorted(by_provider.items()):
            provider_endpoints = [endpoint for endpoint in endpoints if endpoint.provider_type.value == provider_value]
            healthy_count = sum(1 for endpoint in provider_endpoints if endpoint.health_status == CDNHealthStatus.HEALTHY)
            results.append(
                CDNProviderAnalytics(
                    provider_type=grouped_metrics[0].provider_type,
                    region_code=region,
                    endpoint_count=len(provider_endpoints),
                    healthy_endpoint_count=healthy_count,
                    metrics=self._summarize(grouped_metrics),
                )
            )
        return results

    def endpoint_analytics(self, region_code: str | None = None) -> list[CDNEndpointAnalytics]:
        metrics = self.repository.list_endpoint_metrics(region_code=region_code)
        latest_by_endpoint: dict[tuple[UUID, str], CDNEndpointMetric] = {}
        for metric in metrics:
            key = (metric.endpoint_id, metric.region_code)
            if key not in latest_by_endpoint:
                latest_by_endpoint[key] = metric

        analytics: list[CDNEndpointAnalytics] = []
        for metric in latest_by_endpoint.values():
            endpoint = metric.endpoint
            analytics.append(
                CDNEndpointAnalytics(
                    endpoint_id=endpoint.id,
                    edge_hostname=endpoint.edge_hostname,
                    provider_type=endpoint.provider_type,
                    region_code=metric.region_code,
                    is_enabled=endpoint.is_enabled,
                    health_status=endpoint.health_status,
                    score=self._score_endpoint(endpoint, metric),
                    metrics=self._summarize([metric]),
                )
            )
        return sorted(analytics, key=lambda item: (-item.score, item.edge_hostname))

    def region_analytics(self) -> list[CDNRegionAnalytics]:
        endpoints = self.repository.list_endpoints()
        metrics = self.repository.list_endpoint_metrics()
        by_region: dict[str, list[CDNEndpointMetric]] = defaultdict(list)
        for metric in metrics:
            by_region[metric.region_code].append(metric)

        results: list[CDNRegionAnalytics] = []
        for region, grouped_metrics in sorted(by_region.items()):
            endpoint_ids = {metric.endpoint_id for metric in grouped_metrics}
            provider_types = {metric.provider_type for metric in grouped_metrics}
            results.append(
                CDNRegionAnalytics(
                    region_code=region,
                    provider_count=len(provider_types),
                    endpoint_count=len([endpoint for endpoint in endpoints if endpoint.id in endpoint_ids]),
                    metrics=self._summarize(grouped_metrics),
                )
            )
        return results

    def routing_events(self, limit: int = 100) -> list[CDNRoutingEventResponse]:
        return [CDNRoutingEventResponse.model_validate(event) for event in self.repository.list_routing_events(limit=limit)]

    def record_failover_event(self, data: CDNFailoverEventCreate) -> CDNFailoverEventResponse:
        return CDNFailoverEventResponse.model_validate(self.repository.create_failover_event(data))

    def failover_history(self, limit: int = 100) -> list[CDNFailoverEventResponse]:
        return [CDNFailoverEventResponse.model_validate(event) for event in self.repository.list_failover_events(limit=limit)]

    def create_operator_override(
        self,
        data: CDNTrafficAllocationOverrideCreate,
        created_by_user_id: int | None,
    ) -> CDNTrafficAllocationOverrideResponse:
        override = self.repository.create_traffic_override(data, created_by_user_id)
        return CDNTrafficAllocationOverrideResponse.model_validate(override)

    def traffic_allocation_recommendations(self, region_code: str = "global") -> CDNTrafficAllocationResponse:
        analytics = self.endpoint_analytics(region_code=region_code)
        if not analytics:
            analytics = self.endpoint_analytics(region_code=None)

        eligible = [
            item
            for item in analytics
            if item.is_enabled and item.health_status != CDNHealthStatus.UNHEALTHY and item.score > 0.0
        ]
        overrides = self.repository.list_active_traffic_overrides(region_code=region_code)
        forced: dict[UUID, float] = {}
        for override in overrides:
            for item in eligible:
                provider_match = override.provider_type is not None and override.provider_type == item.provider_type
                endpoint_match = override.endpoint_id is not None and override.endpoint_id == item.endpoint_id
                if endpoint_match or provider_match:
                    forced[item.endpoint_id] = max(forced.get(item.endpoint_id, 0.0), override.allocation_percent)

        forced_total = min(100.0, sum(forced.values()))
        remaining = max(0.0, 100.0 - forced_total)
        unforced = [item for item in eligible if item.endpoint_id not in forced]
        unforced_score_total = sum(item.score for item in unforced)
        recommendations: list[CDNTrafficAllocationRecommendation] = []

        for item in eligible:
            if item.endpoint_id in forced:
                allocation = forced[item.endpoint_id]
                override_flag = True
                reason = "operator_override"
            elif unforced_score_total > 0:
                allocation = remaining * (item.score / unforced_score_total)
                override_flag = False
                reason = "performance_weighted"
            else:
                allocation = 0.0
                override_flag = False
                reason = "no_capacity"
            recommendations.append(
                CDNTrafficAllocationRecommendation(
                    endpoint_id=item.endpoint_id,
                    edge_hostname=item.edge_hostname,
                    provider_type=item.provider_type,
                    region_code=item.region_code,
                    allocation_percent=_clamp_percent(allocation),
                    score=item.score,
                    health_status=item.health_status,
                    reason=reason,
                    operator_override=override_flag,
                )
            )

        return CDNTrafficAllocationResponse(
            generated_at=utc_now(),
            region_code=region_code,
            recommendations=sorted(recommendations, key=lambda item: (-item.allocation_percent, item.edge_hostname)),
        )

    def operational_metrics(self) -> CDNOperationalMetrics:
        overview = self.overview()
        return CDNOperationalMetrics(
            generated_at=overview.generated_at,
            cdn_requests_total=overview.metrics.request_count,
            cdn_bandwidth_bytes_total=overview.metrics.bandwidth_bytes,
            cdn_cache_hit_ratio=overview.metrics.cache_hit_ratio,
            cdn_origin_offload_ratio=overview.metrics.origin_offload_ratio,
            cdn_http_error_rate=overview.metrics.http_error_rate,
            cdn_endpoint_health={
                "healthy": overview.healthy_endpoint_count,
                "degraded": overview.degraded_endpoint_count,
                "unhealthy": overview.unhealthy_endpoint_count,
            },
        )

    def _store_provider_rollup(self, metric: CDNEndpointMetric) -> None:
        rollup = CDNProviderMetric(
            provider_type=metric.provider_type,
            region_code=metric.region_code,
            granularity=CDNMetricGranularity.HOURLY,
            window_start=metric.window_start,
            window_end=metric.window_end,
            request_count=metric.request_count,
            bandwidth_bytes=metric.bandwidth_bytes,
            cache_hit_count=metric.cache_hit_count,
            cache_miss_count=metric.cache_miss_count,
            origin_fetch_count=metric.origin_fetch_count,
            avg_latency_ms=metric.avg_latency_ms,
            p95_latency_ms=metric.p95_latency_ms,
            http_4xx_count=metric.http_4xx_count,
            http_5xx_count=metric.http_5xx_count,
            health_status=metric.health_status,
        )
        self.repository.create_provider_metric(rollup)

    def _summarize(self, metrics: Sequence[CDNEndpointMetric | CDNProviderMetric]) -> CDNMetricSummary:
        request_count = sum(metric.request_count for metric in metrics)
        bandwidth_bytes = sum(metric.bandwidth_bytes for metric in metrics)
        cache_hit_count = sum(metric.cache_hit_count for metric in metrics)
        cache_miss_count = sum(metric.cache_miss_count for metric in metrics)
        origin_fetch_count = sum(metric.origin_fetch_count for metric in metrics)
        http_4xx_count = sum(metric.http_4xx_count for metric in metrics)
        http_5xx_count = sum(metric.http_5xx_count for metric in metrics)
        weighted_latency = sum(metric.avg_latency_ms * max(metric.request_count, 1) for metric in metrics)
        weighted_p95 = sum(metric.p95_latency_ms * max(metric.request_count, 1) for metric in metrics)
        weight = sum(max(metric.request_count, 1) for metric in metrics)
        status = self._worst_health(metric.health_status for metric in metrics)
        return CDNMetricSummary(
            request_count=request_count,
            bandwidth_bytes=bandwidth_bytes,
            cache_hit_ratio=_safe_ratio(cache_hit_count, cache_hit_count + cache_miss_count),
            origin_offload_ratio=round(max(0.0, 1.0 - _safe_ratio(origin_fetch_count, request_count)), 4),
            avg_latency_ms=round(_safe_ratio(weighted_latency, weight), 2),
            p95_latency_ms=round(_safe_ratio(weighted_p95, weight), 2),
            http_error_rate=_safe_ratio(http_4xx_count + http_5xx_count, request_count),
            http_4xx_count=http_4xx_count,
            http_5xx_count=http_5xx_count,
            health_status=status,
        )

    def _score_endpoint(self, endpoint: CDNEndpoint, metric: CDNEndpointMetric) -> float:
        if not endpoint.is_enabled or endpoint.health_status == CDNHealthStatus.UNHEALTHY:
            return 0.0
        latency_penalty = min(metric.p95_latency_ms / 20.0, 35.0)
        error_penalty = _safe_ratio(metric.http_4xx_count + metric.http_5xx_count, max(metric.request_count, 1)) * 100.0
        cache_penalty = (1.0 - _safe_ratio(metric.cache_hit_count, metric.cache_hit_count + metric.cache_miss_count)) * 20.0
        priority_penalty = min(endpoint.priority / 100.0, 10.0)
        failure_penalty = min(endpoint.consecutive_failures * 8.0, 32.0)
        health_penalty = 18.0 if endpoint.health_status == CDNHealthStatus.DEGRADED else 0.0
        score = 100.0 - latency_penalty - error_penalty - cache_penalty - priority_penalty - failure_penalty - health_penalty
        return round(max(0.0, score), 2)

    def _worst_health(self, statuses: Iterable[CDNHealthStatus]) -> CDNHealthStatus:
        ordered = list(statuses)
        if CDNHealthStatus.UNHEALTHY in ordered:
            return CDNHealthStatus.UNHEALTHY
        if CDNHealthStatus.DEGRADED in ordered:
            return CDNHealthStatus.DEGRADED
        return CDNHealthStatus.HEALTHY
