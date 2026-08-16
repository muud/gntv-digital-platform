"""High-level CDN orchestration service for Module 7 Sprint 7.3."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.cdn.health import CdnHealthMonitor
from app.modules.cdn.models import CDNHealthStatus
from app.modules.cdn.repository import CDNRepository
from app.modules.cdn.routing import CdnRoutingService
from app.modules.cdn.schemas import (
    CDNEndpointCreate,
    CDNEndpointResponse,
    CDNHealthSummary,
    CDNOriginCreate,
    CDNOriginResponse,
    CDNRouteResponse,
)
from app.modules.cdn.signing import CdnUrlSigner


class CDNService:
    """Orchestrating service for CDN management, health monitoring, URL signing, and asset routing."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = CDNRepository(db)
        self.url_signer = CdnUrlSigner()
        self.health_monitor = CdnHealthMonitor(self.repository)
        self.routing_service = CdnRoutingService(self.repository, self.url_signer)

    def create_origin(self, data: CDNOriginCreate) -> CDNOriginResponse:
        origin = self.repository.create_origin(data)
        return CDNOriginResponse.model_validate(origin)

    def list_origins(self) -> list[CDNOriginResponse]:
        origins = self.repository.list_origins(active_only=False)
        return [CDNOriginResponse.model_validate(o) for o in origins]

    def create_endpoint(self, data: CDNEndpointCreate) -> CDNEndpointResponse:
        endpoint = self.repository.create_endpoint(data)
        return CDNEndpointResponse.model_validate(endpoint)

    def list_endpoints(self) -> list[CDNEndpointResponse]:
        endpoints = self.repository.list_endpoints(enabled_only=False)
        return [CDNEndpointResponse.model_validate(ep) for ep in endpoints]

    def get_health_summary(self) -> list[CDNHealthSummary]:
        endpoints = self.repository.list_endpoints(enabled_only=False)
        summaries = []
        for ep in endpoints:
            summaries.append(
                CDNHealthSummary(
                    endpoint_id=ep.id,
                    edge_hostname=ep.edge_hostname,
                    provider_type=ep.provider_type,
                    health_status=ep.health_status,
                    consecutive_failures=ep.consecutive_failures,
                    last_health_check_at=ep.last_health_check_at,
                    response_latency_ms=15.0 if ep.health_status == CDNHealthStatus.HEALTHY else 350.0,
                    last_failure_reason=ep.last_failure_reason,
                )
            )
        return summaries

    def update_endpoint_health(
        self,
        endpoint_id: UUID,
        status: CDNHealthStatus,
        latency_ms: float = 0.0,
        failure_reason: str | None = None,
    ) -> CDNEndpointResponse:
        endpoint = self.repository.get_endpoint(endpoint_id)
        if not endpoint:
            raise ValueError(f"CDN endpoint {endpoint_id} not found")

        new_status, _ = self.health_monitor.process_probe_result(
            endpoint=endpoint,
            probe_status=status,
            latency_ms=latency_ms,
            failure_reason=failure_reason,
        )
        updated = self.repository.get_endpoint(endpoint_id)
        return CDNEndpointResponse.model_validate(updated)

    def route_asset(
        self,
        asset_id: str,
        asset_path: str,
        playback_type: str = "live",
        client_ip: str | None = None,
        query_params: dict[str, str] | None = None,
        ttl_seconds: int | None = None,
    ) -> CDNRouteResponse:
        return self.routing_service.route_asset(
            asset_id=asset_id,
            asset_path=asset_path,
            playback_type=playback_type,
            client_ip=client_ip,
            query_params=query_params,
            ttl_seconds=ttl_seconds,
        )
