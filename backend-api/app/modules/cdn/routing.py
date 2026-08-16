"""CDN Routing Service for Global Multi-CDN & Edge Acceleration (Module 7 Sprint 7.3)."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlsplit

from app.modules.cdn.models import CDNEndpoint, CDNHealthStatus
from app.modules.cdn.repository import CDNRepository
from app.modules.cdn.schemas import CDNRouteResponse
from app.modules.cdn.signing import CdnUrlSigner


class CdnRoutingService:
    """Selects target CDN edge / origin based on priority, health status, and failover policy."""

    def __init__(self, repository: CDNRepository, url_signer: CdnUrlSigner | None = None) -> None:
        self.repository = repository
        self.url_signer = url_signer or CdnUrlSigner()

    def route_asset(
        self,
        asset_id: str,
        asset_path: str,
        *,
        playback_type: str = "live",
        client_ip: str | None = None,
        query_params: dict[str, str] | None = None,
        ttl_seconds: int | None = None,
    ) -> CDNRouteResponse:
        """Deterministically route a playback request to the optimal healthy CDN edge endpoint."""
        endpoints = self.repository.list_active_routing_endpoints()

        selected_endpoint: CDNEndpoint | None = None
        routing_reason = "NO_HEALTHY_ENDPOINTS_AVAILABLE"
        is_failover = False

        if endpoints:
            # 1. Look for HEALTHY endpoint with highest priority (lowest priority integer)
            healthy_endpoints = [ep for ep in endpoints if ep.health_status == CDNHealthStatus.HEALTHY]
            if healthy_endpoints:
                selected_endpoint = healthy_endpoints[0]
                primary_origin_id = endpoints[0].origin_id if endpoints else None
                if selected_endpoint.origin_id != primary_origin_id:
                    routing_reason = "FAILOVER_SECONDARY_HEALTHY"
                    is_failover = True
                else:
                    routing_reason = "PRIMARY_HEALTHY"
            else:
                # 2. Look for DEGRADED endpoint if no HEALTHY endpoints are available
                degraded_endpoints = [ep for ep in endpoints if ep.health_status == CDNHealthStatus.DEGRADED]
                if degraded_endpoints:
                    selected_endpoint = degraded_endpoints[0]
                    routing_reason = "DEGRADED_ENDPOINT_FALLBACK"
                    is_failover = True
                else:
                    # 3. Fallback to primary endpoint if all are marked UNHEALTHY (emergency degradation mode)
                    selected_endpoint = endpoints[0]
                    routing_reason = "EMERGENCY_UNHEALTHY_FALLBACK"
                    is_failover = True

        if not selected_endpoint:
            raise ValueError(f"No active CDN endpoints configured for asset {asset_id}")

        # Preserve query parameters including SSAI parameters
        merged_params: dict[str, str] = {}
        parsed_asset = urlsplit(asset_path)
        if parsed_asset.query:
            merged_params.update(dict(parse_qsl(parsed_asset.query)))
        if query_params:
            merged_params.update(query_params)

        # Generate signed URL using provider abstraction
        signed_url, expires_at = self.url_signer.sign_url(
            edge_hostname=selected_endpoint.edge_hostname,
            asset_path=parsed_asset.path,
            provider_type=selected_endpoint.provider_type,
            secret=None,  # Uses default or endpoint signing_key_ref
            ttl_seconds=ttl_seconds,
            client_ip=client_ip,
            custom_params=merged_params,
        )

        # Derive cache headers
        cache_headers = self.url_signer.get_cache_headers(
            asset_path=parsed_asset.path,
            playback_type=playback_type,
            provider_type=selected_endpoint.provider_type,
            custom_policy=selected_endpoint.cache_policy_json,
        )

        # Log routing decision event for auditability
        decision_metadata = {
            "playback_type": playback_type,
            "is_failover": is_failover,
            "endpoint_priority": selected_endpoint.priority,
            "endpoint_health_status": selected_endpoint.health_status.value,
            "cache_control": cache_headers.get("Cache-Control", ""),
            "query_param_keys": list(merged_params.keys()),
        }
        self.repository.log_routing_event(
            asset_id=asset_id,
            endpoint_id=selected_endpoint.id,
            routing_reason=routing_reason,
            client_ip=client_ip,
            decision_metadata_json=decision_metadata,
        )

        origin_hostname = selected_endpoint.origin.origin_hostname if selected_endpoint.origin else "origin.gntv.com"

        return CDNRouteResponse(
            routed_url=signed_url,
            endpoint_id=selected_endpoint.id,
            edge_hostname=selected_endpoint.edge_hostname,
            provider_type=selected_endpoint.provider_type,
            origin_hostname=origin_hostname,
            routing_reason=routing_reason,
            is_failover=is_failover,
            expires_at=expires_at,
            cache_control=cache_headers.get("Cache-Control", "public, max-age=300"),
        )
