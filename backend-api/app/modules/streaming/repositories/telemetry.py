"""QoE Telemetry Repository for Sprint 6.5."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.streaming.models.domain import (
    QoEAggregateHourly,
    QoEEventRaw,
    QoESessionMetric,
)


class QoERepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add_raw_events(self, events: list[QoEEventRaw]) -> None:
        """Batch insert raw telemetry events."""
        self.db.add_all(events)
        self.db.flush()

    def upsert_session_metric(self, metric: QoESessionMetric) -> QoESessionMetric:
        """Upsert a session summary metric record."""
        existing = self.db.scalars(
            select(QoESessionMetric).where(
                QoESessionMetric.playback_session_id == metric.playback_session_id
            )
        ).first()

        if existing:
            existing.startup_latency_ms = metric.startup_latency_ms
            existing.total_rebuffer_duration_ms = metric.total_rebuffer_duration_ms
            existing.rebuffer_count = metric.rebuffer_count
            existing.rebuffer_ratio = metric.rebuffer_ratio
            existing.average_bitrate_bps = metric.average_bitrate_bps
            existing.total_watch_duration_ms = metric.total_watch_duration_ms
            existing.completion_ratio = metric.completion_ratio
            existing.has_error = metric.has_error
            self.db.flush()
            return existing

        self.db.add(metric)
        self.db.flush()
        return metric

    def get_session_metric(self, session_id: UUID) -> QoESessionMetric | None:
        """Retrieve metric summary by playback session ID."""
        return self.db.scalars(
            select(QoESessionMetric).where(QoESessionMetric.playback_session_id == session_id)
        ).first()

    def save_hourly_aggregate(self, agg: QoEAggregateHourly) -> QoEAggregateHourly:
        """Save hourly roll-up aggregate."""
        self.db.add(agg)
        self.db.flush()
        return agg

    def get_hourly_aggregates(
        self, target_id: UUID, start_time: datetime, end_time: datetime
    ) -> list[QoEAggregateHourly]:
        """Query hourly roll-up aggregates for a target."""
        stmt = (
            select(QoEAggregateHourly)
            .where(
                QoEAggregateHourly.target_id == target_id,
                QoEAggregateHourly.window_start >= start_time,
                QoEAggregateHourly.window_start <= end_time,
            )
            .order_by(QoEAggregateHourly.window_start.asc())
        )
        return list(self.db.scalars(stmt).all())
