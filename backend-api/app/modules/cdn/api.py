"""FastAPI Router for Global Multi-CDN & Edge Acceleration (Module 7 Sprint 7.3)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user, require_role
from app.models.user import User
from app.modules.cdn.models import CDNProviderType
from app.modules.cdn.schemas import (
    CDNEndpointCreate,
    CDNEndpointResponse,
    CDNHealthSummary,
    CDNHealthUpdate,
    CDNOriginCreate,
    CDNOriginResponse,
    CDNRouteResponse,
    CDNSignedUrlRequest,
    CDNSignedUrlResponse,
)
from app.modules.cdn.service import CDNService

router = APIRouter(prefix="/api/v1/cdn", tags=["Global Multi-CDN"])


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
