"""SQLAlchemy domain models for the Module 5 streaming control plane."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    """Return an aware UTC timestamp for ORM defaults."""

    return datetime.now(UTC)


def enum_type(enum: type[StrEnum], name: str) -> Enum:
    """Create a value-backed SQLAlchemy enum with a stable database name."""

    return Enum(enum, name=name, values_callable=lambda values: [item.value for item in values])


class ChannelStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    LIVE = "live"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class RecordingPolicy(StrEnum):
    ALWAYS = "always"
    EVENT = "event"
    MANUAL = "manual"
    NEVER = "never"


class LiveEventStatus(StrEnum):
    SCHEDULED = "scheduled"
    READY = "ready"
    LIVE = "live"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class StreamProtocol(StrEnum):
    RTMP = "rtmp"
    SRT = "srt"


class StreamStatus(StrEnum):
    REQUESTED = "requested"
    ADMITTED = "admitted"
    PROBING = "probing"
    STARTING = "starting"
    LIVE = "live"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    FINALIZING = "finalizing"
    STOPPED = "stopped"
    RETRYING = "retrying"
    FAILED = "failed"


class StreamKeyStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class RecordingStatus(StrEnum):
    RECORDING = "recording"
    FINALIZING = "finalizing"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"
    DELETED = "deleted"


class PlaybackSessionStatus(StrEnum):
    AUTHORIZED = "authorized"
    PLAYING = "playing"
    PAUSED = "paused"
    ENDED = "ended"
    REVOKED = "revoked"
    EXPIRED = "expired"


class TranscodingJobType(StrEnum):
    PROBE = "probe"
    LIVE_TRANSCODE = "live_transcode"
    PACKAGE = "package"
    FINALIZE = "finalize"
    THUMBNAIL = "thumbnail"


class TranscodingJobStatus(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ManifestFormat(StrEnum):
    HLS = "hls"
    DASH = "dash"


class ManifestKind(StrEnum):
    LIVE = "live"
    EVENT = "event"
    VOD = "vod"


class ManifestStatus(StrEnum):
    BUILDING = "building"
    READY = "ready"
    STALE = "stale"
    REVOKED = "revoked"
    FAILED = "failed"


class ThumbnailKind(StrEnum):
    POSTER = "poster"
    KEYFRAME = "keyframe"
    SPRITE = "sprite"
    PREVIEW = "preview"


class ThumbnailStatus(StrEnum):
    QUEUED = "queued"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class TimestampVersionMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class LiveChannel(Base, TimestampVersionMixin):
    __tablename__ = "live_channels"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    catalog_item_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("catalog_items.id", ondelete="SET NULL")
    )
    channel_code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), nullable=False, unique=True)
    status: Mapped[ChannelStatus] = mapped_column(
        enum_type(ChannelStatus, "gntv_channel_status"),
        default=ChannelStatus.DRAFT,
        nullable=False,
    )
    ingest_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    transcode_profile: Mapped[str] = mapped_column(String(100), nullable=False)
    recording_policy: Mapped[RecordingPolicy] = mapped_column(
        enum_type(RecordingPolicy, "gntv_recording_policy"),
        default=RecordingPolicy.MANUAL,
        nullable=False,
    )
    fallback_media_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("cms_media_files.id", ondelete="SET NULL")
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    current_event_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "live_events.id",
            name="fk_live_channels_current_event",
            ondelete="SET NULL",
            use_alter=True,
        ),
    )
    primary_ingest_host: Mapped[str | None] = mapped_column(String(500))
    backup_ingest_host: Mapped[str | None] = mapped_column(String(500))
    dvr_window_seconds: Mapped[int] = mapped_column(Integer, default=7200, nullable=False)
    catchup_retention_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    dvr_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    drm_policy_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("drm_policies.id", ondelete="SET NULL"))
    geo_policy_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("geo_policies.id", ondelete="SET NULL"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    __table_args__ = (
        CheckConstraint("dvr_window_seconds >= 0", name="ck_live_channels_dvr_window"),
        CheckConstraint(
            "catchup_retention_days >= 0",
            name="ck_live_channels_catchup_retention",
        ),
        Index("idx_live_channels_status", "status"),
        Index("idx_live_channels_catalog", "catalog_item_id"),
    )


class LiveEvent(Base, TimestampVersionMixin):
    __tablename__ = "live_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    live_channel_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("live_channels.id", ondelete="RESTRICT"), nullable=False
    )
    content_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("cms_content.id", ondelete="SET NULL"))
    catalog_item_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("catalog_items.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[LiveEventStatus] = mapped_column(
        enum_type(LiveEventStatus, "gntv_live_event_status"),
        default=LiveEventStatus.SCHEDULED,
        nullable=False,
    )
    scheduled_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actual_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actual_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recording_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    __table_args__ = (
        CheckConstraint("scheduled_end_at > scheduled_start_at", name="ck_live_event_schedule_order"),
        CheckConstraint(
            "actual_end_at IS NULL OR actual_start_at IS NULL OR actual_end_at >= actual_start_at",
            name="ck_live_event_actual_order",
        ),
        Index("idx_live_events_channel_schedule", "live_channel_id", "scheduled_start_at"),
        Index("idx_live_events_status_schedule", "status", "scheduled_start_at"),
    )


class StreamKey(Base, TimestampVersionMixin):
    __tablename__ = "stream_keys"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    live_channel_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("live_channels.id", ondelete="RESTRICT"), nullable=False
    )
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[StreamKeyStatus] = mapped_column(
        enum_type(StreamKeyStatus, "gntv_stream_key_status"),
        default=StreamKeyStatus.ACTIVE,
        nullable=False,
    )
    allowed_protocols: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allowed_cidrs: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    revoked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        Index("idx_stream_keys_channel_status", "live_channel_id", "status"),
        Index("idx_stream_keys_expiry", "expires_at"),
    )


class Stream(Base, TimestampVersionMixin):
    __tablename__ = "streams"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    live_channel_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("live_channels.id", ondelete="RESTRICT"), nullable=False
    )
    live_event_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("live_events.id", ondelete="SET NULL")
    )
    stream_key_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("stream_keys.id", ondelete="RESTRICT"), nullable=False
    )
    protocol: Mapped[StreamProtocol] = mapped_column(
        enum_type(StreamProtocol, "gntv_stream_protocol"), nullable=False
    )
    status: Mapped[StreamStatus] = mapped_column(
        enum_type(StreamStatus, "gntv_stream_status"),
        default=StreamStatus.REQUESTED,
        nullable=False,
    )
    gateway_node: Mapped[str | None] = mapped_column(String(160))
    worker_node: Mapped[str | None] = mapped_column(String(160))
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    health: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_detail: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    __table_args__ = (
        Index("idx_streams_channel_status", "live_channel_id", "status"),
        Index("idx_streams_status_heartbeat", "status", "last_heartbeat_at"),
        Index("idx_streams_event", "live_event_id"),
    )


class Recording(Base, TimestampVersionMixin):
    __tablename__ = "recordings"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    stream_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("streams.id", ondelete="RESTRICT"), nullable=False)
    live_event_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("live_events.id", ondelete="SET NULL")
    )
    media_file_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("cms_media_files.id", ondelete="SET NULL")
    )
    status: Mapped[RecordingStatus] = mapped_column(
        enum_type(RecordingStatus, "gntv_recording_status"),
        default=RecordingStatus.RECORDING,
        nullable=False,
    )
    oss_prefix: Mapped[str] = mapped_column(String(1024), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    start_sequence_number: Mapped[int | None] = mapped_column(BigInteger)
    end_sequence_number: Mapped[int | None] = mapped_column(BigInteger)
    epg_event_id: Mapped[str | None] = mapped_column(String(160))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_detail: Mapped[str | None] = mapped_column(Text)
    drm_policy_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("drm_policies.id", ondelete="SET NULL"))
    geo_policy_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("geo_policies.id", ondelete="SET NULL"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    __table_args__ = (
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_recording_duration"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="ck_recording_size"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_recording_time_order"),
        CheckConstraint(
            "start_sequence_number IS NULL OR start_sequence_number >= 0",
            name="ck_recording_start_sequence",
        ),
        CheckConstraint(
            "end_sequence_number IS NULL OR end_sequence_number >= 0",
            name="ck_recording_end_sequence",
        ),
        CheckConstraint(
            "end_sequence_number IS NULL OR start_sequence_number IS NULL "
            "OR end_sequence_number >= start_sequence_number",
            name="ck_recording_sequence_order",
        ),
        Index("idx_recordings_stream", "stream_id"),
        Index("idx_recordings_event", "live_event_id"),
        Index("idx_recordings_epg_event", "epg_event_id"),
        Index("idx_recordings_status_ended", "status", "ended_at"),
    )


class DVRSegmentIndex(Base, TimestampVersionMixin):
    __tablename__ = "dvr_segment_index"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    live_channel_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("live_channels.id", ondelete="CASCADE"), nullable=False
    )
    stream_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("streams.id", ondelete="SET NULL"))
    live_event_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("live_events.id", ondelete="SET NULL")
    )
    recording_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("recordings.id", ondelete="SET NULL")
    )
    rendition: Mapped[str] = mapped_column(String(80), default="source", nullable=False)
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    segment_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    segment_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    segment_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    provider_event_id: Mapped[str | None] = mapped_column(String(200))
    apsara_object_key: Mapped[str | None] = mapped_column(String(1024))
    is_pruned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("sequence_number >= 0", name="ck_dvr_segment_sequence"),
        CheckConstraint("duration_seconds > 0", name="ck_dvr_segment_duration"),
        CheckConstraint("segment_end_at > segment_start_at", name="ck_dvr_segment_time_order"),
        UniqueConstraint(
            "live_channel_id",
            "rendition",
            "sequence_number",
            name="uq_dvr_segment_channel_rendition_sequence",
        ),
        Index("idx_dvr_segment_channel_time", "live_channel_id", "segment_start_at"),
        Index("idx_dvr_segment_channel_live_event", "live_channel_id", "live_event_id"),
        Index("idx_dvr_segment_recording_sequence", "recording_id", "sequence_number"),
        Index("idx_dvr_segment_provider_event", "provider_event_id"),
        Index("idx_dvr_segment_prune", "live_channel_id", "segment_end_at", "is_pruned"),
    )


class PlaybackSession(Base, TimestampVersionMixin):
    __tablename__ = "playback_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    live_channel_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("live_channels.id", ondelete="RESTRICT")
    )
    recording_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("recordings.id", ondelete="RESTRICT")
    )
    catalog_item_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("catalog_items.id", ondelete="RESTRICT")
    )
    device_id: Mapped[str] = mapped_column(String(160), nullable=False)
    token_jti_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[PlaybackSessionStatus] = mapped_column(
        enum_type(PlaybackSessionStatus, "gntv_playback_session_status"),
        default=PlaybackSessionStatus.AUTHORIZED,
        nullable=False,
    )
    country_code: Mapped[str | None] = mapped_column(String(2))
    ip_hash: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    position_ms: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN live_channel_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN recording_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN catalog_item_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_playback_exactly_one_target",
        ),
        CheckConstraint("position_ms >= 0", name="ck_playback_position"),
        CheckConstraint(
            "country_code IS NULL OR length(country_code) = 2",
            name="ck_playback_country_code",
        ),
        Index("idx_playback_user_status", "user_id", "status"),
        Index("idx_playback_channel_status", "live_channel_id", "status"),
        Index("idx_playback_recording_status", "recording_id", "status"),
        Index("idx_playback_expiry", "expires_at"),
    )


class TranscodingJob(Base, TimestampVersionMixin):
    __tablename__ = "transcoding_jobs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    stream_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("streams.id", ondelete="RESTRICT"))
    recording_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("recordings.id", ondelete="RESTRICT")
    )
    job_type: Mapped[TranscodingJobType] = mapped_column(
        enum_type(TranscodingJobType, "gntv_transcoding_job_type"), nullable=False
    )
    queue: Mapped[str] = mapped_column(String(80), nullable=False)
    capability: Mapped[str | None] = mapped_column(String(100))
    input_source: Mapped[str | None] = mapped_column(String(2048))
    output_prefix: Mapped[str | None] = mapped_column(String(512))
    renditions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[TranscodingJobStatus] = mapped_column(
        enum_type(TranscodingJobStatus, "gntv_transcoding_job_status"),
        default=TranscodingJobStatus.QUEUED,
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(160))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_detail: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "stream_id IS NOT NULL OR recording_id IS NOT NULL OR input_source IS NOT NULL",
            name="ck_transcoding_job_has_source",
        ),
        CheckConstraint("attempt >= 0 AND max_attempts > 0", name="ck_transcoding_job_attempts"),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at",
            name="ck_transcoding_job_time_order",
        ),
        Index("idx_transcoding_queue_status", "queue", "status", "created_at"),
        Index("idx_transcoding_lease", "lease_expires_at"),
    )


class Manifest(Base, TimestampVersionMixin):
    __tablename__ = "manifests"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    stream_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("streams.id", ondelete="RESTRICT"))
    recording_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("recordings.id", ondelete="RESTRICT")
    )
    format: Mapped[ManifestFormat] = mapped_column(
        enum_type(ManifestFormat, "gntv_manifest_format"), nullable=False
    )
    kind: Mapped[ManifestKind] = mapped_column(
        enum_type(ManifestKind, "gntv_manifest_kind"), nullable=False
    )
    status: Mapped[ManifestStatus] = mapped_column(
        enum_type(ManifestStatus, "gntv_manifest_status"),
        default=ManifestStatus.BUILDING,
        nullable=False,
    )
    oss_object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    cdn_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    renditions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "stream_id IS NOT NULL OR recording_id IS NOT NULL",
            name="ck_manifest_has_source",
        ),
        CheckConstraint("generation > 0", name="ck_manifest_generation"),
        UniqueConstraint(
            "stream_id",
            "recording_id",
            "format",
            "generation",
            name="uq_manifest_source_format_generation",
        ),
        Index("idx_manifest_stream_format_status", "stream_id", "format", "status"),
        Index("idx_manifest_recording_format_status", "recording_id", "format", "status"),
    )


class Thumbnail(Base, TimestampVersionMixin):
    __tablename__ = "thumbnails"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    recording_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("recordings.id", ondelete="RESTRICT")
    )
    stream_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("streams.id", ondelete="RESTRICT"))
    media_file_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("cms_media_files.id", ondelete="SET NULL")
    )
    kind: Mapped[ThumbnailKind] = mapped_column(
        enum_type(ThumbnailKind, "gntv_thumbnail_kind"), nullable=False
    )
    timestamp_ms: Mapped[int | None] = mapped_column(BigInteger)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    oss_object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[ThumbnailStatus] = mapped_column(
        enum_type(ThumbnailStatus, "gntv_thumbnail_status"),
        default=ThumbnailStatus.QUEUED,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "recording_id IS NOT NULL OR stream_id IS NOT NULL",
            name="ck_thumbnail_has_source",
        ),
        CheckConstraint("timestamp_ms IS NULL OR timestamp_ms >= 0", name="ck_thumbnail_timestamp"),
        CheckConstraint("width > 0 AND height > 0", name="ck_thumbnail_dimensions"),
        Index("idx_thumbnail_recording_kind_time", "recording_id", "kind", "timestamp_ms"),
        Index("idx_thumbnail_stream", "stream_id"),
    )


class UserWatchHistory(Base, TimestampVersionMixin):
    __tablename__ = "user_watch_history"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    playback_session_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("playback_sessions.id", ondelete="SET NULL")
    )
    live_channel_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("live_channels.id", ondelete="SET NULL")
    )
    recording_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("recordings.id", ondelete="SET NULL")
    )
    catalog_item_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("catalog_items.id", ondelete="SET NULL")
    )
    device_id: Mapped[str] = mapped_column(String(160), nullable=False)
    watch_duration_ms: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    max_position_ms: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    completion_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    __table_args__ = (
        CheckConstraint("watch_duration_ms >= 0", name="ck_watch_history_duration"),
        CheckConstraint("max_position_ms >= 0", name="ck_watch_history_position"),
        CheckConstraint("completion_ratio >= 0.0 AND completion_ratio <= 1.0", name="ck_watch_history_completion"),
        Index("idx_watch_history_user_time", "user_id", "created_at"),
    )


class DRMPolicy(Base, TimestampVersionMixin):
    __tablename__ = "drm_policies"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(50), default="alibaba_kms", nullable=False)
    max_resolution: Mapped[str] = mapped_column(String(20), default="1080p", nullable=False)
    hdcp_enforcement: Mapped[str] = mapped_column(String(20), default="hdcp_v2_2", nullable=False)
    allow_persistent_license: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    license_duration_seconds: Mapped[int] = mapped_column(Integer, default=86400, nullable=False)
    rental_duration_seconds: Mapped[int] = mapped_column(Integer, default=172800, nullable=False)


class GeoPolicy(Base, TimestampVersionMixin):
    __tablename__ = "geo_policies"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    country_allow_list: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    country_deny_list: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    block_vpn: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    block_proxy: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fail_closed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DRMKey(Base, TimestampVersionMixin):
    __tablename__ = "drm_keys"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, unique=True, default=uuid4)
    policy_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("drm_policies.id", ondelete="RESTRICT")
    )
    asset_id: Mapped[UUID | None] = mapped_column(Uuid)
    live_channel_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("live_channels.id", ondelete="CASCADE")
    )
    encrypted_key_envelope: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(50), default="AES-128-CTR", nullable=False)
    key_rotation_interval_seconds: Mapped[int | None] = mapped_column(Integer, default=86400)

    __table_args__ = (
        Index("idx_drm_keys_asset", "asset_id"),
        Index("idx_drm_keys_channel", "live_channel_id"),
    )


class QoEEventRaw(Base, TimestampVersionMixin):
    __tablename__ = "qoe_events_raw"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    playback_session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("playback_sessions.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    client_timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    server_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    position_ms: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bitrate_bps: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    error_code: Mapped[str | None] = mapped_column(String(100))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("idx_qoe_raw_session_time", "playback_session_id", "client_timestamp_ms"),
    )


class QoESessionMetric(Base, TimestampVersionMixin):
    __tablename__ = "qoe_session_metrics"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    playback_session_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("playback_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    live_channel_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("live_channels.id", ondelete="SET NULL")
    )
    recording_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("recordings.id", ondelete="SET NULL")
    )
    startup_latency_ms: Mapped[int | None] = mapped_column(Integer)
    total_rebuffer_duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rebuffer_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rebuffer_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    average_bitrate_bps: Mapped[int | None] = mapped_column(Integer)
    total_watch_duration_ms: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    completion_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    device_category: Mapped[str] = mapped_column(String(50), default="web", nullable=False)
    network_type: Mapped[str] = mapped_column(String(50), default="unknown", nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2))
    has_error: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("idx_qoe_session_target", "live_channel_id", "recording_id", "created_at"),
    )


class QoEAggregateHourly(Base, TimestampVersionMixin):
    __tablename__ = "qoe_aggregates_hourly"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    device_category: Mapped[str] = mapped_column(String(50), default="all", nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2))
    total_sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    p50_startup_latency_ms: Mapped[int | None] = mapped_column(Integer)
    p95_startup_latency_ms: Mapped[int | None] = mapped_column(Integer)
    avg_rebuffer_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_bitrate_bps: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        Index("idx_qoe_agg_window_target", "window_start", "target_id", "device_category"),
    )


class UserPlaybackPreference(Base, TimestampVersionMixin):
    __tablename__ = "user_playback_preferences"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=True,
    )
    preferred_subtitle_lang: Mapped[str] = mapped_column(String(10), default="none", nullable=False)
    preferred_audio_lang: Mapped[str] = mapped_column(String(10), default="default", nullable=False)
    caption_font_size: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    caption_bg_opacity: Mapped[float] = mapped_column(Float, default=0.75, nullable=False)
    tv_mode_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("idx_user_pref_user", "user_id"),
    )
