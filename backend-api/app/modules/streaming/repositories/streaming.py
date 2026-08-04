"""Persistence repository for the Module 5 streaming domain."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.orm import Session

from app.modules.streaming.models import (
    ChannelStatus,
    LiveChannel,
    LiveEvent,
    Manifest,
    ManifestFormat,
    ManifestStatus,
    PlaybackSession,
    Recording,
    RecordingStatus,
    Stream,
    StreamKey,
    StreamProtocol,
    StreamStatus,
    UserWatchHistory,
)

ModelT = TypeVar("ModelT")


class StreamingRepository:
    """Thin transaction-agnostic persistence boundary.

    The FastAPI database dependency owns commit and rollback behavior.
    """

    def __init__(self, db: Session):
        self.db = db

    def add(self, item: ModelT) -> ModelT:
        self.db.add(item)
        self.db.flush()
        return item

    def stream(self, stream_id: UUID) -> Stream | None:
        return self.db.get(Stream, stream_id)

    def stream_for_update(self, stream_id: UUID) -> Stream | None:
        return self.db.execute(
            select(Stream).where(Stream.id == stream_id).with_for_update()
        ).scalar_one_or_none()

    def stream_by_idempotency_key(self, idempotency_key: str) -> Stream | None:
        return self.db.execute(
            select(Stream).where(Stream.idempotency_key == idempotency_key)
        ).scalar_one_or_none()

    def stream_key_by_prefix(self, key_prefix: str) -> StreamKey | None:
        return self.db.execute(
            select(StreamKey).where(StreamKey.key_prefix == key_prefix)
        ).scalar_one_or_none()

    def stream_key(self, stream_key_id: UUID) -> StreamKey | None:
        return self.db.get(StreamKey, stream_key_id)

    def active_stream_for_channel(self, channel_id: UUID) -> Stream | None:
        active_states = (
            StreamStatus.ADMITTED,
            StreamStatus.PROBING,
            StreamStatus.STARTING,
            StreamStatus.LIVE,
            StreamStatus.DEGRADED,
            StreamStatus.RETRYING,
        )
        return self.db.execute(
            select(Stream)
            .where(Stream.live_channel_id == channel_id, Stream.status.in_(active_states))
            .order_by(Stream.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def channel(self, channel_id: UUID) -> LiveChannel | None:
        return self.db.get(LiveChannel, channel_id)

    def public_channel_for_catalog_item(self, catalog_item_id: UUID) -> LiveChannel | None:
        return self.db.execute(
            select(LiveChannel).where(
                LiveChannel.catalog_item_id == catalog_item_id,
                LiveChannel.is_public.is_(True),
            )
        ).scalar_one_or_none()

    def live_event(self, event_id: UUID) -> LiveEvent | None:
        return self.db.get(LiveEvent, event_id)

    def recording(self, recording_id: UUID) -> Recording | None:
        return self.db.get(Recording, recording_id)

    def ready_hls_manifest_for_channel(self, channel_id: UUID) -> Manifest | None:
        return self.db.execute(
            select(Manifest)
            .join(Stream, Stream.id == Manifest.stream_id)
            .where(
                Stream.live_channel_id == channel_id,
                Manifest.format == ManifestFormat.HLS,
                Manifest.status == ManifestStatus.READY,
            )
            .order_by(Manifest.generation.desc())
            .limit(1)
        ).scalar_one_or_none()

    def ready_hls_manifest_for_recording(self, recording_id: UUID) -> Manifest | None:
        return self.db.execute(
            select(Manifest)
            .where(
                Manifest.recording_id == recording_id,
                Manifest.format == ManifestFormat.HLS,
                Manifest.status == ManifestStatus.READY,
            )
            .order_by(Manifest.generation.desc())
            .limit(1)
        ).scalar_one_or_none()

    def add_playback_session(self, session: PlaybackSession) -> PlaybackSession:
        return self.add(session)

    def get_playback_session(self, session_id: UUID) -> PlaybackSession | None:
        return self.db.execute(
            select(PlaybackSession).where(PlaybackSession.id == session_id)
        ).scalar_one_or_none()

    def add_watch_history(self, history: UserWatchHistory) -> UserWatchHistory:
        return self.add(history)

    @staticmethod
    def _before_cursor(
        model: type[Any], created_at: datetime | None, item_id: UUID | None
    ) -> ColumnElement[bool] | None:
        if created_at is None or item_id is None:
            return None
        created_column = getattr(model, "created_at")
        id_column = getattr(model, "id")
        return or_(created_column < created_at, and_(created_column == created_at, id_column < item_id))

    def streams(
        self,
        *,
        limit: int,
        before_created_at: datetime | None = None,
        before_id: UUID | None = None,
        channel_id: UUID | None = None,
        status: StreamStatus | None = None,
        protocol: StreamProtocol | None = None,
    ) -> Sequence[Stream]:
        query = select(Stream)
        cursor = self._before_cursor(Stream, before_created_at, before_id)
        if cursor is not None:
            query = query.where(cursor)
        if channel_id is not None:
            query = query.where(Stream.live_channel_id == channel_id)
        if status is not None:
            query = query.where(Stream.status == status)
        if protocol is not None:
            query = query.where(Stream.protocol == protocol)
        return self.db.execute(
            query.order_by(Stream.created_at.desc(), Stream.id.desc()).limit(limit)
        ).scalars().all()

    def channels(
        self,
        *,
        limit: int,
        before_created_at: datetime | None = None,
        before_id: UUID | None = None,
        status: ChannelStatus | None = None,
        public_only: bool = False,
    ) -> Sequence[LiveChannel]:
        query = select(LiveChannel)
        cursor = self._before_cursor(LiveChannel, before_created_at, before_id)
        if cursor is not None:
            query = query.where(cursor)
        if status is not None:
            query = query.where(LiveChannel.status == status)
        if public_only:
            query = query.where(LiveChannel.is_public.is_(True))
        return self.db.execute(
            query.order_by(LiveChannel.created_at.desc(), LiveChannel.id.desc()).limit(limit)
        ).scalars().all()

    def recordings(
        self,
        *,
        limit: int,
        before_created_at: datetime | None = None,
        before_id: UUID | None = None,
        stream_id: UUID | None = None,
        channel_id: UUID | None = None,
        status: RecordingStatus | None = None,
    ) -> Sequence[Recording]:
        query = select(Recording)
        cursor = self._before_cursor(Recording, before_created_at, before_id)
        if cursor is not None:
            query = query.where(cursor)
        if stream_id is not None:
            query = query.where(Recording.stream_id == stream_id)
        if channel_id is not None:
            query = query.join(Stream, Stream.id == Recording.stream_id).where(Stream.live_channel_id == channel_id)
        if status is not None:
            query = query.where(Recording.status == status)
        return self.db.execute(
            query.order_by(Recording.created_at.desc(), Recording.id.desc()).limit(limit)
        ).scalars().all()
