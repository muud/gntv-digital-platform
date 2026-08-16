"""Health check & failover hysteresis monitor for Global Multi-CDN (Module 7 Sprint 7.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.core.config import settings
from app.modules.cdn.models import CDNEndpoint, CDNHealthStatus
from app.modules.cdn.providers.alibaba_dcdn import AlibabaDcdnProvider
from app.modules.cdn.providers.base import BaseCDNProvider
from app.modules.cdn.repository import CDNRepository


def utc_now() -> datetime:
    return datetime.now(UTC)


class CdnHealthMonitor:
    """Manages CDN endpoint health checking and state transitions with flapping hysteresis."""

    def __init__(
        self,
        repository: CDNRepository,
        failover_threshold: int | None = None,
        cooldown_seconds: int | None = None,
    ) -> None:
        self.repository = repository
        self.failover_threshold = failover_threshold or settings.CDN_FAILOVER_THRESHOLD
        self.cooldown_seconds = cooldown_seconds or settings.CDN_COOLDOWN_SECONDS
        self._provider: BaseCDNProvider = AlibabaDcdnProvider()

    def process_probe_result(
        self,
        endpoint: CDNEndpoint,
        probe_status: CDNHealthStatus,
        latency_ms: float,
        failure_reason: str | None = None,
    ) -> tuple[CDNHealthStatus, bool]:
        """Process a probe result for an endpoint and apply hysteresis state transitions.

        Returns:
            (new_health_status, state_changed_boolean)
        """
        previous_status = endpoint.health_status
        new_status = previous_status
        consecutive_failures = endpoint.consecutive_failures

        if probe_status == CDNHealthStatus.HEALTHY:
            # Probe succeeded
            consecutive_failures = 0
            if previous_status == CDNHealthStatus.UNHEALTHY:
                # Check cooldown period before restoring to HEALTHY
                if endpoint.last_health_check_at:
                    last_check = endpoint.last_health_check_at
                    if last_check.tzinfo is None:
                        last_check = last_check.replace(tzinfo=UTC)
                    elapsed = (utc_now() - last_check).total_seconds()
                    if elapsed >= self.cooldown_seconds:
                        new_status = CDNHealthStatus.HEALTHY
                    else:
                        new_status = CDNHealthStatus.DEGRADED
                else:
                    new_status = CDNHealthStatus.HEALTHY
            elif previous_status == CDNHealthStatus.DEGRADED:
                new_status = CDNHealthStatus.HEALTHY
            else:
                new_status = CDNHealthStatus.HEALTHY

        else:
            # Probe failed or degraded
            consecutive_failures += 1
            if consecutive_failures >= self.failover_threshold:
                new_status = CDNHealthStatus.UNHEALTHY
            else:
                new_status = CDNHealthStatus.DEGRADED

        state_changed = new_status != previous_status

        # Update repository logs and endpoint record
        self.repository.log_health_check(
            endpoint_id=endpoint.id,
            status=probe_status,
            response_latency_ms=latency_ms,
            failure_reason=failure_reason,
        )
        self.repository.update_endpoint_health(
            endpoint_id=endpoint.id,
            status=new_status,
            consecutive_failures=consecutive_failures,
            failure_reason=failure_reason if probe_status != CDNHealthStatus.HEALTHY else None,
        )

        return new_status, state_changed

    def probe_endpoint(
        self,
        endpoint_id: UUID,
        health_path: str | None = None,
    ) -> tuple[CDNHealthStatus, float, str | None]:
        """Probe an endpoint target and apply state update."""
        endpoint = self.repository.get_endpoint(endpoint_id)
        if not endpoint:
            raise ValueError(f"CDN endpoint {endpoint_id} not found")

        path = health_path or (endpoint.origin.health_check_path if endpoint.origin else "/health")
        probe_status, latency_ms, failure_reason = self._provider.probe_health(
            edge_hostname=endpoint.edge_hostname,
            health_path=path,
        )

        self.process_probe_result(
            endpoint=endpoint,
            probe_status=probe_status,
            latency_ms=latency_ms,
            failure_reason=failure_reason,
        )

        return probe_status, latency_ms, failure_reason
