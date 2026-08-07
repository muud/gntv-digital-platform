"""QoE Telemetry & Observability Service for Sprint 6.5."""

from datetime import UTC, datetime
import hashlib
import hmac
from typing import Any
from uuid import UUID


from app.modules.streaming.models.domain import (
    QoEEventRaw,
    QoESessionMetric,
)
from app.modules.streaming.repositories.telemetry import QoERepository
from app.modules.streaming.schemas.contracts import (
    TelemetryBatchRequest,
    TelemetryBatchResponse,
)

SALT_KEY = b"gntv-telemetry-anonymization-salt-prod-v1"


def anonymize_identifier(raw_identifier: str) -> str:
    """Anonymize PII identifiers using HMAC-SHA256."""
    return hmac.new(SALT_KEY, raw_identifier.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


class QoEService:
    def __init__(self, repo: QoERepository) -> None:
        self.repo = repo

    def ingest_batch(
        self,
        request: TelemetryBatchRequest,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> TelemetryBatchResponse:
        """Ingest a batch of client playback telemetry events."""
        if not request.events:
            return TelemetryBatchResponse(
                accepted_count=0,
                dropped_count=0,
                next_flush_interval_ms=10000,
            )

        now_utc = datetime.now(UTC)
        server_ms = int(now_utc.timestamp() * 1000)
        skew_ms = server_ms - request.client_timestamp_ms

        raw_records: list[QoEEventRaw] = []
        accepted_count = 0

        for item in request.events:
            # Normalize timestamp with clock-skew adjustment
            norm_timestamp_ms = item.timestamp_ms + skew_ms
            norm_dt = datetime.fromtimestamp(norm_timestamp_ms / 1000.0, tz=UTC)

            meta = dict(item.metadata or {})
            if client_ip:
                meta["anonymized_ip"] = anonymize_identifier(client_ip)
            if user_agent:
                meta["user_agent_short"] = user_agent[:100]

            record = QoEEventRaw(
                playback_session_id=request.session_id,
                event_type=item.event_type,
                client_timestamp_ms=item.timestamp_ms,
                server_timestamp=norm_dt,
                position_ms=item.position_ms,
                bitrate_bps=item.bitrate_bps,
                fps=item.fps,
                error_code=item.error_code,
                metadata_json=meta,
            )
            raw_records.append(record)
            accepted_count += 1

        self.repo.add_raw_events(raw_records)
        self._update_session_summary(request.session_id, raw_records)

        return TelemetryBatchResponse(
            accepted_count=accepted_count,
            dropped_count=0,
            next_flush_interval_ms=10000,
        )

    def _update_session_summary(self, session_id: UUID, events: list[QoEEventRaw]) -> None:
        """Calculate and update session QoE metrics summary."""
        existing = self.repo.get_session_metric(session_id)

        startup_latency_ms: int | None = existing.startup_latency_ms if existing else None
        total_rebuffer_duration_ms: int = (
            existing.total_rebuffer_duration_ms if existing else 0
        )
        rebuffer_count: int = existing.rebuffer_count if existing else 0
        average_bitrate_bps: int | None = existing.average_bitrate_bps if existing else None
        total_watch_duration_ms: int = existing.total_watch_duration_ms if existing else 0
        has_error: bool = existing.has_error if existing else False

        bitrate_samples: list[int] = []
        if average_bitrate_bps is not None:
            bitrate_samples.append(average_bitrate_bps)

        for evt in events:
            if evt.event_type == "startup" and startup_latency_ms is None:
                stall = evt.metadata_json.get("stall_duration_ms")
                if isinstance(stall, (int, float)):
                    startup_latency_ms = int(stall)
                elif evt.position_ms > 0:
                    startup_latency_ms = int(evt.position_ms)

            elif evt.event_type == "buffer_start":
                rebuffer_count += 1

            elif evt.event_type == "buffer_end":
                stall = evt.metadata_json.get("stall_duration_ms")
                if isinstance(stall, (int, float)):
                    total_rebuffer_duration_ms += int(stall)

            elif evt.event_type == "error" or evt.error_code:
                has_error = True

            if evt.bitrate_bps is not None and evt.bitrate_bps > 0:
                bitrate_samples.append(evt.bitrate_bps)

            if evt.position_ms > total_watch_duration_ms:
                total_watch_duration_ms = evt.position_ms

        if bitrate_samples:
            average_bitrate_bps = int(sum(bitrate_samples) / len(bitrate_samples))

        total_time = max(1, total_watch_duration_ms + total_rebuffer_duration_ms)
        rebuffer_ratio = min(1.0, round(total_rebuffer_duration_ms / total_time, 4))

        metric = QoESessionMetric(
            playback_session_id=session_id,
            startup_latency_ms=startup_latency_ms,
            total_rebuffer_duration_ms=total_rebuffer_duration_ms,
            rebuffer_count=rebuffer_count,
            rebuffer_ratio=rebuffer_ratio,
            average_bitrate_bps=average_bitrate_bps,
            total_watch_duration_ms=total_watch_duration_ms,
            completion_ratio=min(1.0, round(total_watch_duration_ms / 3600000.0, 4)),
            device_category="web",
            network_type="wifi",
            country_code="KE",
            has_error=has_error,
        )

        self.repo.upsert_session_metric(metric)

    def get_metrics_summary(self, target_id: UUID) -> dict[str, Any]:
        """Generate high-level QoE metrics summary for admin dashboard."""
        now = datetime.now(UTC)
        aggregates = self.repo.get_hourly_aggregates(
            target_id=target_id,
            start_time=datetime.fromtimestamp(now.timestamp() - 86400, tz=UTC),
            end_time=now,
        )

        if not aggregates:
            return {
                "target_id": str(target_id),
                "total_sessions": 0,
                "p50_startup_latency_ms": 0,
                "p95_startup_latency_ms": 0,
                "avg_rebuffer_ratio": 0.0,
                "error_rate_percentage": 0.0,
                "status": "healthy",
            }

        total_sessions = sum(a.total_sessions for a in aggregates)
        avg_rebuffer = sum(a.avg_rebuffer_ratio for a in aggregates) / len(aggregates)
        total_errors = sum(a.total_errors for a in aggregates)

        return {
            "target_id": str(target_id),
            "total_sessions": total_sessions,
            "p50_startup_latency_ms": aggregates[-1].p50_startup_latency_ms or 350,
            "p95_startup_latency_ms": aggregates[-1].p95_startup_latency_ms or 1200,
            "avg_rebuffer_ratio": round(avg_rebuffer, 4),
            "total_errors": total_errors,
            "status": "healthy" if avg_rebuffer < 0.025 else "degraded",
        }
