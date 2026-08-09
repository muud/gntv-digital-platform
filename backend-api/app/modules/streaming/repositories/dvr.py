"""DVR segment persistence for Sprint 6.3."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.streaming.models import DVRSegmentIndex, LiveChannel, LiveEvent, Recording


class DVRRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add_segment(self, segment: DVRSegmentIndex) -> DVRSegmentIndex:
        existing = self.segment_by_channel_sequence(
            segment.live_channel_id,
            segment.rendition,
            segment.sequence_number,
        )
        if existing is not None:
            return existing
        self.db.add(segment)
        self.db.flush()
        return segment

    def segment_by_channel_sequence(
        self,
        live_channel_id: UUID,
        rendition: str,
        sequence_number: int,
    ) -> DVRSegmentIndex | None:
        return self.db.execute(
            select(DVRSegmentIndex).where(
                DVRSegmentIndex.live_channel_id == live_channel_id,
                DVRSegmentIndex.rendition == rendition,
                DVRSegmentIndex.sequence_number == sequence_number,
            )
        ).scalar_one_or_none()

    def segment_by_provider_event_id(self, provider_event_id: str) -> DVRSegmentIndex | None:
        return self.db.execute(
            select(DVRSegmentIndex).where(DVRSegmentIndex.provider_event_id == provider_event_id)
        ).scalar_one_or_none()

    def channel(self, channel_id: UUID) -> LiveChannel | None:
        return self.db.get(LiveChannel, channel_id)

    def channel_by_code(self, channel_code: str) -> LiveChannel | None:
        return self.db.execute(
            select(LiveChannel).where(LiveChannel.channel_code == channel_code)
        ).scalar_one_or_none()

    def live_event(self, live_event_id: UUID) -> LiveEvent | None:
        return self.db.get(LiveEvent, live_event_id)

    def recording_for_event(self, live_event_id: UUID) -> Recording | None:
        return self.db.execute(
            select(Recording)
            .where(Recording.live_event_id == live_event_id)
            .order_by(Recording.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def segments_for_channel_window(
        self,
        channel_id: UUID,
        *,
        start_at: datetime,
        end_at: datetime,
        rendition: str = "source",
        limit: int = 2000,
    ) -> Sequence[DVRSegmentIndex]:
        return (
            self.db.execute(
                select(DVRSegmentIndex)
                .where(
                    DVRSegmentIndex.live_channel_id == channel_id,
                    DVRSegmentIndex.rendition == rendition,
                    DVRSegmentIndex.is_pruned.is_(False),
                    DVRSegmentIndex.segment_end_at > start_at,
                    DVRSegmentIndex.segment_start_at < end_at,
                )
                .order_by(DVRSegmentIndex.sequence_number)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def segments_for_recording(
        self,
        recording: Recording,
        *,
        rendition: str = "source",
        limit: int = 5000,
    ) -> Sequence[DVRSegmentIndex]:
        query = select(DVRSegmentIndex).where(
            DVRSegmentIndex.rendition == rendition,
            DVRSegmentIndex.is_pruned.is_(False),
        )
        if recording.id is not None:
            query = query.where(DVRSegmentIndex.recording_id == recording.id)
        if recording.live_event_id is not None:
            query = query.where(DVRSegmentIndex.live_event_id == recording.live_event_id)
        if recording.start_sequence_number is not None:
            query = query.where(DVRSegmentIndex.sequence_number >= recording.start_sequence_number)
        if recording.end_sequence_number is not None:
            query = query.where(DVRSegmentIndex.sequence_number <= recording.end_sequence_number)
        return (
            self.db.execute(query.order_by(DVRSegmentIndex.sequence_number).limit(limit))
            .scalars()
            .all()
        )

    def mark_pruned_before(self, channel_id: UUID, cutoff: datetime) -> int:
        result = self.db.execute(
            update(DVRSegmentIndex)
            .where(
                DVRSegmentIndex.live_channel_id == channel_id,
                DVRSegmentIndex.segment_end_at < cutoff,
                DVRSegmentIndex.is_pruned.is_(False),
            )
            .values(is_pruned=True)
        )
        self.db.flush()
        return int(getattr(result, "rowcount", 0) or 0)
