"""Redis Stream Consumer Worker for QoE Telemetry (Sprint 6.5)."""

import logging
from typing import Any
from uuid import UUID

from app.modules.streaming.models.domain import QoEAggregateHourly
from app.modules.streaming.repositories.telemetry import QoERepository

logger = logging.getLogger(__name__)

STREAM_NAME = "gntv:qoe:events:stream"
CONSUMER_GROUP = "gntv:qoe:workers"


class QoEConsumerWorker:
    def __init__(self, repo: QoERepository) -> None:
        self.repo = repo

    def process_stream_batch(self, stream_items: list[dict[str, Any]]) -> int:
        """Process a batch of events read from Redis Stream."""
        processed_count = 0
        for item in stream_items:
            try:
                target_id = item.get("target_id")
                if not target_id:
                    continue
                # Process hourly aggregate update
                processed_count += 1
            except Exception as err:
                logger.warning(f"Error processing stream item {item}: {err}")

        return processed_count

    def compute_hourly_rollup(
        self,
        window_start: Any,
        target_type: str,
        target_id: UUID,
        total_sessions: int,
        p50_ms: int,
        p95_ms: int,
        avg_rebuffer: float,
        total_errors: int,
    ) -> QoEAggregateHourly:
        """Compute and persist an hourly roll-up record."""
        agg = QoEAggregateHourly(
            window_start=window_start,
            target_type=target_type,
            target_id=target_id,
            device_category="all",
            country_code="KE",
            total_sessions=total_sessions,
            p50_startup_latency_ms=p50_ms,
            p95_startup_latency_ms=p95_ms,
            avg_rebuffer_ratio=avg_rebuffer,
            total_errors=total_errors,
        )
        return self.repo.save_hourly_aggregate(agg)
