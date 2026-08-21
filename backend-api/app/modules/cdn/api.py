"""FastAPI Router for Global Multi-CDN & Edge Acceleration (Module 7 Sprint 7.3)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user, require_role
from app.models.user import User
from app.modules.cdn.analytics import CDNObservabilityService
from app.modules.cdn.models import CDNProviderType
from app.modules.cdn.schemas import (
    CDNEndpointCreate,
    CDNEndpointAnalytics,
    CDNEndpointMetricCreate,
    CDNEndpointMetricResponse,
    CDNEndpointResponse,
    CDNFailoverEventCreate,
    CDNFailoverEventResponse,
    CDNHealthSummary,
    CDNHealthUpdate,
    CDNObservabilityOverview,
    CDNOperationalMetrics,
    CDNOriginCreate,
    CDNOriginResponse,
    CDNProviderAnalytics,
    CDNRegionAnalytics,
    CDNRouteResponse,
    CDNRoutingEventResponse,
    CDNSignedUrlRequest,
    CDNSignedUrlResponse,
    CDNTrafficAllocationOverrideCreate,
    CDNTrafficAllocationOverrideResponse,
    CDNTrafficAllocationResponse,
)
from app.modules.cdn.repository import CDNRepository
from app.modules.cdn.service import CDNService

router = APIRouter(prefix="/api/v1/cdn", tags=["Global Multi-CDN"])


def require_cdn_operator(current_user: User = Depends(get_current_user)) -> User:
    """Require an admin or CDN operator role for observability controls."""
    if {"admin", "operator"} & set(current_user.role_names):
        return current_user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin or operator role required",
    )


@router.get(
    "/route/{asset_id}",
    response_model=CDNRouteResponse,
    summary="Resolve signed edge playback URL with health-aware failover",
)
def route_asset_playback(
    asset_id: str,
    request: Request,
    asset_path: str = Query(..., description="Canonical asset path, e.g., /hls/live/channel1/index.m3u8"),
    playback_type: str = Query("live", description="Playback mode: live, vod, fast"),
    ttl_seconds: int = Query(1800, ge=30, le=86400, description="Expiration time in seconds"),
    db: Session = Depends(get_db),
) -> CDNRouteResponse:
    """Select optimal healthy CDN edge endpoint and return signed playback URL.

    Preserves SSAI query parameters, ad tracking markers, and records routing event for auditability.
    """
    service = CDNService(db)

    raw_query = dict(request.query_params)
    raw_query.pop("asset_path", None)
    raw_query.pop("playback_type", None)
    raw_query.pop("ttl_seconds", None)

    client_ip = request.client.host if request.client else None

    try:
        return service.route_asset(
            asset_id=asset_id,
            asset_path=asset_path,
            playback_type=playback_type,
            client_ip=client_ip,
            query_params=raw_query,
            ttl_seconds=ttl_seconds,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.get(
    "/endpoints",
    response_model=list[CDNEndpointResponse],
    summary="List all configured CDN edge endpoints",
)
def list_endpoints(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[CDNEndpointResponse]:
    """Retrieve list of CDN endpoints and health states."""
    del current_user
    service = CDNService(db)
    return service.list_endpoints()


@router.post(
    "/endpoints",
    response_model=CDNEndpointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Configure a new CDN edge endpoint target",
)
def create_endpoint(
    payload: CDNEndpointCreate,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> CDNEndpointResponse:
    """Create a new CDN endpoint configuration. Requires admin role."""
    service = CDNService(db)
    return service.create_endpoint(payload)


@router.get(
    "/origins",
    response_model=list[CDNOriginResponse],
    summary="List all configured origin servers",
)
def list_origins(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[CDNOriginResponse]:
    """Retrieve list of origin servers."""
    del current_user
    service = CDNService(db)
    return service.list_origins()


@router.post(
    "/origins",
    response_model=CDNOriginResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new origin server configuration",
)
def create_origin(
    payload: CDNOriginCreate,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> CDNOriginResponse:
    """Create a new origin server record. Requires admin role."""
    service = CDNService(db)
    return service.create_origin(payload)


@router.get(
    "/health",
    response_model=list[CDNHealthSummary],
    summary="Retrieve aggregate health status of CDN endpoints",
)
def get_cdn_health(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[CDNHealthSummary]:
    """Get current health summary for all CDN endpoints."""
    del current_user
    service = CDNService(db)
    return service.get_health_summary()


@router.post(
    "/endpoints/{endpoint_id}/health",
    response_model=CDNEndpointResponse,
    summary="Update or report health check result for a CDN endpoint",
)
def update_endpoint_health(
    endpoint_id: UUID,
    payload: CDNHealthUpdate,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> CDNEndpointResponse:
    """Submit health check report for a CDN endpoint. Requires admin role."""
    service = CDNService(db)
    try:
        return service.update_endpoint_health(
            endpoint_id=endpoint_id,
            status=payload.status,
            latency_ms=payload.response_latency_ms,
            failure_reason=payload.failure_reason,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


@router.post(
    "/sign-url",
    response_model=CDNSignedUrlResponse,
    summary="Generate a signed edge URL directly",
)
def sign_edge_url(
    payload: CDNSignedUrlRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CDNSignedUrlResponse:
    """Generate a signed CDN edge URL for an asset path."""
    service = CDNService(db)
    endpoints = service.list_endpoints()
    edge_hostname = endpoints[0].edge_hostname if endpoints else "dcdn.gntv.com"

    signed_url, expires_at = service.url_signer.sign_url(
        edge_hostname=edge_hostname,
        asset_path=payload.asset_path,
        ttl_seconds=payload.ttl_seconds,
        client_ip=payload.client_ip,
        custom_params=payload.custom_params,
    )

    return CDNSignedUrlResponse(
        signed_url=signed_url,
        expires_at=expires_at,
        edge_hostname=edge_hostname,
        provider_type=endpoints[0].provider_type if endpoints else CDNProviderType.ALIBABA_DCDN,
        signature_algorithm="HMAC-SHA256",
    )


@router.post(
    "/observability/metrics",
    response_model=CDNEndpointMetricResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest CDN endpoint observability metrics",
)
def ingest_endpoint_metrics(
    payload: CDNEndpointMetricCreate,
    current_user: User = Depends(require_cdn_operator),
    db: Session = Depends(get_db),
) -> CDNEndpointMetricResponse:
    """Persist endpoint metrics for analytics, monitoring, and deterministic optimization."""
    del current_user
    service = CDNObservabilityService(CDNRepository(db))
    try:
        return service.ingest_endpoint_metric(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get(
    "/observability/overview",
    response_model=CDNObservabilityOverview,
    summary="Get CDN observability overview",
)
def observability_overview(
    region_code: str | None = Query(default=None, max_length=32),
    current_user: User = Depends(require_cdn_operator),
    db: Session = Depends(get_db),
) -> CDNObservabilityOverview:
    """Return aggregate request, bandwidth, cache, latency, health, and failover metrics."""
    del current_user
    return CDNObservabilityService(CDNRepository(db)).overview(region_code=region_code)


@router.get(
    "/observability/providers",
    response_model=list[CDNProviderAnalytics],
    summary="Get provider-level CDN analytics",
)
def provider_analytics(
    region_code: str | None = Query(default=None, max_length=32),
    current_user: User = Depends(require_cdn_operator),
    db: Session = Depends(get_db),
) -> list[CDNProviderAnalytics]:
    """Return provider rollups by region."""
    del current_user
    return CDNObservabilityService(CDNRepository(db)).provider_analytics(region_code=region_code)


@router.get(
    "/observability/endpoints",
    response_model=list[CDNEndpointAnalytics],
    summary="Get endpoint-level CDN analytics",
)
def endpoint_analytics(
    region_code: str | None = Query(default=None, max_length=32),
    current_user: User = Depends(require_cdn_operator),
    db: Session = Depends(get_db),
) -> list[CDNEndpointAnalytics]:
    """Return endpoint health, metrics, and routing score summaries."""
    del current_user
    return CDNObservabilityService(CDNRepository(db)).endpoint_analytics(region_code=region_code)


@router.get(
    "/observability/regions",
    response_model=list[CDNRegionAnalytics],
    summary="Get regional CDN analytics",
)
def region_analytics(
    current_user: User = Depends(require_cdn_operator),
    db: Session = Depends(get_db),
) -> list[CDNRegionAnalytics]:
    """Return aggregate CDN metrics grouped by region code."""
    del current_user
    return CDNObservabilityService(CDNRepository(db)).region_analytics()


@router.get(
    "/observability/routing-events",
    response_model=list[CDNRoutingEventResponse],
    summary="Get CDN routing event history",
)
def routing_event_history(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(require_cdn_operator),
    db: Session = Depends(get_db),
) -> list[CDNRoutingEventResponse]:
    """Return recent routing decisions for audit and optimization review."""
    del current_user
    return CDNObservabilityService(CDNRepository(db)).routing_events(limit=limit)


@router.post(
    "/observability/failover-history",
    response_model=CDNFailoverEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a CDN failover event",
)
def record_failover_event(
    payload: CDNFailoverEventCreate,
    current_user: User = Depends(require_cdn_operator),
    db: Session = Depends(get_db),
) -> CDNFailoverEventResponse:
    """Record failover metadata for operator review and metrics history."""
    del current_user
    return CDNObservabilityService(CDNRepository(db)).record_failover_event(payload)


@router.get(
    "/observability/failover-history",
    response_model=list[CDNFailoverEventResponse],
    summary="Get CDN failover history",
)
def failover_history(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(require_cdn_operator),
    db: Session = Depends(get_db),
) -> list[CDNFailoverEventResponse]:
    """Return recent CDN failover events."""
    del current_user
    return CDNObservabilityService(CDNRepository(db)).failover_history(limit=limit)


@router.post(
    "/observability/traffic-overrides",
    response_model=CDNTrafficAllocationOverrideResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an operator traffic allocation override",
)
def create_traffic_override(
    payload: CDNTrafficAllocationOverrideCreate,
    current_user: User = Depends(require_cdn_operator),
    db: Session = Depends(get_db),
) -> CDNTrafficAllocationOverrideResponse:
    """Create a bounded operator override used by allocation recommendations."""
    return CDNObservabilityService(CDNRepository(db)).create_operator_override(payload, current_user.id)


@router.get(
    "/observability/traffic-allocation",
    response_model=CDNTrafficAllocationResponse,
    summary="Get CDN traffic allocation recommendations",
)
def traffic_allocation_recommendations(
    region_code: str = Query(default="global", max_length=32),
    current_user: User = Depends(require_cdn_operator),
    db: Session = Depends(get_db),
) -> CDNTrafficAllocationResponse:
    """Return deterministic endpoint allocation percentages from health and performance metrics."""
    del current_user
    return CDNObservabilityService(CDNRepository(db)).traffic_allocation_recommendations(region_code=region_code)


@router.get(
    "/metrics",
    response_model=CDNOperationalMetrics,
    summary="Get operational CDN metrics for monitoring integration",
)
def operational_metrics(
    current_user: User = Depends(require_cdn_operator),
    db: Session = Depends(get_db),
) -> CDNOperationalMetrics:
    """Expose aggregate application/CDN operational metrics."""
    del current_user
    return CDNObservabilityService(CDNRepository(db)).operational_metrics()
