"""Database repository for Global Multi-CDN & Edge Acceleration (Module 7 Sprint 7.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.modules.cdn.models import (
    CDNEndpoint,
    CDNEndpointMetric,
    CDNFailoverEvent,
    CDNHealthCheck,
    CDNHealthStatus,
    CDNMetricGranularity,
    CDNOrigin,
    CDNProviderMetric,
    CDNRoutingEvent,
    CDNTrafficAllocationOverride,
)
from app.modules.cdn.schemas import (
    CDNEndpointCreate,
    CDNEndpointMetricCreate,
    CDNFailoverEventCreate,
    CDNOriginCreate,
    CDNTrafficAllocationOverrideCreate,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class CDNRepository:
    """Encapsulates all database interactions for CDN origins, endpoints, and health/routing logs."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # Origin operations
    def create_origin(self, data: CDNOriginCreate) -> CDNOrigin:
        origin = CDNOrigin(
            name=data.name,
            origin_hostname=data.origin_hostname,
            origin_type=data.origin_type,
            is_active=data.is_active,
            health_check_path=data.health_check_path,
        )
        self.db.add(origin)
        self.db.commit()
        self.db.refresh(origin)
        return origin

    def get_origin(self, origin_id: UUID) -> CDNOrigin | None:
        return self.db.query(CDNOrigin).filter(CDNOrigin.id == origin_id).first()

    def get_origin_by_name(self, name: str) -> CDNOrigin | None:
        return self.db.query(CDNOrigin).filter(CDNOrigin.name == name).first()

    def list_origins(self, active_only: bool = True) -> list[CDNOrigin]:
        query = self.db.query(CDNOrigin)
        if active_only:
            query = query.filter(CDNOrigin.is_active.is_(True))
        return query.order_by(CDNOrigin.name).all()

    # Endpoint operations
    def create_endpoint(self, data: CDNEndpointCreate) -> CDNEndpoint:
        endpoint = CDNEndpoint(
            origin_id=data.origin_id,
            provider_type=data.provider_type,
            edge_hostname=data.edge_hostname,
            signing_key_ref=data.signing_key_ref,
            priority=data.priority,
            is_enabled=data.is_enabled,
            cache_policy_json=data.cache_policy_json,
            health_status=CDNHealthStatus.HEALTHY,
            consecutive_failures=0,
        )
        self.db.add(endpoint)
        self.db.commit()
        self.db.refresh(endpoint)
        return endpoint

    def get_endpoint(self, endpoint_id: UUID) -> CDNEndpoint | None:
        stmt = select(CDNEndpoint).options(joinedload(CDNEndpoint.origin)).where(CDNEndpoint.id == endpoint_id)
        return self.db.scalars(stmt).first()

    def get_endpoint_by_edge_hostname(self, edge_hostname: str) -> CDNEndpoint | None:
        stmt = select(CDNEndpoint).options(joinedload(CDNEndpoint.origin)).where(CDNEndpoint.edge_hostname == edge_hostname)
        return self.db.scalars(stmt).first()

    def list_endpoints(self, enabled_only: bool = False) -> list[CDNEndpoint]:
        stmt = select(CDNEndpoint).options(joinedload(CDNEndpoint.origin))
        if enabled_only:
            stmt = stmt.where(CDNEndpoint.is_enabled.is_(True))
        stmt = stmt.order_by(CDNEndpoint.priority.asc())
        return list(self.db.scalars(stmt).all())

    def list_active_routing_endpoints(self) -> list[CDNEndpoint]:
        """Return enabled endpoints sorted deterministically by priority."""
        stmt = (
            select(CDNEndpoint)
            .options(joinedload(CDNEndpoint.origin))
            .join(CDNOrigin, CDNEndpoint.origin_id == CDNOrigin.id)
            .where(
                CDNEndpoint.is_enabled.is_(True),
                CDNOrigin.is_active.is_(True),
            )
            .order_by(CDNEndpoint.priority.asc(), CDNEndpoint.created_at.asc())
        )
        return list(self.db.scalars(stmt).all())

    def update_endpoint_health(
        self,
        endpoint_id: UUID,
        status: CDNHealthStatus,
        consecutive_failures: int,
        failure_reason: str | None = None,
    ) -> CDNEndpoint | None:
        endpoint = self.get_endpoint(endpoint_id)
        if not endpoint:
            return None

        endpoint.health_status = status
        endpoint.consecutive_failures = consecutive_failures
        endpoint.last_health_check_at = utc_now()
        endpoint.last_failure_reason = failure_reason

        self.db.commit()
        self.db.refresh(endpoint)
        return endpoint

    # Health Check Log operations
    def log_health_check(
        self,
        endpoint_id: UUID,
        status: CDNHealthStatus,
        response_latency_ms: float,
        failure_reason: str | None = None,
    ) -> CDNHealthCheck:
        check = CDNHealthCheck(
            endpoint_id=endpoint_id,
            status=status,
            response_latency_ms=response_latency_ms,
            failure_reason=failure_reason,
            checked_at=utc_now(),
        )
        self.db.add(check)
        self.db.commit()
        self.db.refresh(check)
        return check

    def get_latest_health_checks(self, limit: int = 50) -> list[CDNHealthCheck]:
        return (
            self.db.query(CDNHealthCheck)
            .options(joinedload(CDNHealthCheck.endpoint))
            .order_by(CDNHealthCheck.checked_at.desc())
            .limit(limit)
            .all()
        )

    # Routing Event operations
    def log_routing_event(
        self,
        asset_id: str,
        endpoint_id: UUID | None,
        routing_reason: str,
        client_ip: str | None = None,
        decision_metadata_json: dict[str, Any] | None = None,
    ) -> CDNRoutingEvent:
        event = CDNRoutingEvent(
            asset_id=asset_id,
            endpoint_id=endpoint_id,
            routing_reason=routing_reason,
            client_ip=client_ip,
            decision_metadata_json=decision_metadata_json,
            created_at=utc_now(),
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_routing_events(self, limit: int = 100) -> list[CDNRoutingEvent]:
        stmt = (
            select(CDNRoutingEvent)
            .options(joinedload(CDNRoutingEvent.endpoint))
            .order_by(CDNRoutingEvent.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    # Observability metrics
    def create_endpoint_metric(self, data: CDNEndpointMetricCreate) -> CDNEndpointMetric:
        endpoint = self.get_endpoint(data.endpoint_id)
        if not endpoint:
            raise ValueError("CDN endpoint not found")
        metric = CDNEndpointMetric(
            endpoint_id=endpoint.id,
            provider_type=endpoint.provider_type,
            region_code=data.region_code,
            granularity=data.granularity,
            window_start=data.window_start,
            window_end=data.window_end,
            request_count=data.request_count,
            bandwidth_bytes=data.bandwidth_bytes,
            cache_hit_count=data.cache_hit_count,
            cache_miss_count=data.cache_miss_count,
            origin_fetch_count=data.origin_fetch_count,
            avg_latency_ms=data.avg_latency_ms,
            p95_latency_ms=data.p95_latency_ms,
            http_4xx_count=data.http_4xx_count,
            http_5xx_count=data.http_5xx_count,
            health_status=data.health_status,
            observed_at=utc_now(),
        )
        self.db.add(metric)
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def list_endpoint_metrics(
        self,
        granularity: CDNMetricGranularity | None = None,
        region_code: str | None = None,
        limit: int = 500,
    ) -> list[CDNEndpointMetric]:
        stmt = select(CDNEndpointMetric).options(joinedload(CDNEndpointMetric.endpoint))
        if granularity:
            stmt = stmt.where(CDNEndpointMetric.granularity == granularity)
        if region_code:
            stmt = stmt.where(CDNEndpointMetric.region_code == region_code)
        stmt = stmt.order_by(CDNEndpointMetric.window_start.desc()).limit(limit)
        return list(self.db.scalars(stmt).all())

    def create_provider_metric(
        self,
        provider_metric: CDNProviderMetric,
    ) -> CDNProviderMetric:
        self.db.add(provider_metric)
        self.db.commit()
        self.db.refresh(provider_metric)
        return provider_metric

    def list_provider_metrics(
        self,
        granularity: CDNMetricGranularity | None = None,
        region_code: str | None = None,
        limit: int = 500,
    ) -> list[CDNProviderMetric]:
        stmt = select(CDNProviderMetric)
        if granularity:
            stmt = stmt.where(CDNProviderMetric.granularity == granularity)
        if region_code:
            stmt = stmt.where(CDNProviderMetric.region_code == region_code)
        stmt = stmt.order_by(CDNProviderMetric.window_start.desc()).limit(limit)
        return list(self.db.scalars(stmt).all())

    def create_failover_event(self, data: CDNFailoverEventCreate) -> CDNFailoverEvent:
        event = CDNFailoverEvent(
            from_endpoint_id=data.from_endpoint_id,
            to_endpoint_id=data.to_endpoint_id,
            provider_type=data.provider_type,
            region_code=data.region_code,
            asset_id=data.asset_id,
            reason=data.reason,
            decision_metadata_json=data.decision_metadata_json,
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_failover_events(self, limit: int = 100) -> list[CDNFailoverEvent]:
        stmt = select(CDNFailoverEvent).order_by(CDNFailoverEvent.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt).all())

    def create_traffic_override(
        self,
        data: CDNTrafficAllocationOverrideCreate,
        created_by_user_id: int | None,
    ) -> CDNTrafficAllocationOverride:
        override = CDNTrafficAllocationOverride(
            endpoint_id=data.endpoint_id,
            provider_type=data.provider_type,
            region_code=data.region_code,
            allocation_percent=data.allocation_percent,
            reason=data.reason,
            starts_at=data.starts_at or utc_now(),
            ends_at=data.ends_at,
            created_by_user_id=created_by_user_id,
            is_active=True,
        )
        self.db.add(override)
        self.db.commit()
        self.db.refresh(override)
        return override

    def list_active_traffic_overrides(self, region_code: str | None = None) -> list[CDNTrafficAllocationOverride]:
        now = utc_now()
        stmt = select(CDNTrafficAllocationOverride).where(
            CDNTrafficAllocationOverride.is_active.is_(True),
            CDNTrafficAllocationOverride.starts_at <= now,
        )
        stmt = stmt.where(
            (CDNTrafficAllocationOverride.ends_at.is_(None)) | (CDNTrafficAllocationOverride.ends_at > now)
        )
        if region_code:
            stmt = stmt.where(CDNTrafficAllocationOverride.region_code == region_code)
        stmt = stmt.order_by(CDNTrafficAllocationOverride.created_at.desc())
        return list(self.db.scalars(stmt).all())
