"""Database repository for Global Multi-CDN & Edge Acceleration (Module 7 Sprint 7.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.modules.cdn.models import (
    CDNEndpoint,
    CDNHealthCheck,
    CDNHealthStatus,
    CDNOrigin,
    CDNRoutingEvent,
)
from app.modules.cdn.schemas import CDNEndpointCreate, CDNOriginCreate


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
