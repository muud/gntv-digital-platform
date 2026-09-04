"""Module 5 streaming, distribution, and geo-fencing foundation.

Revision ID: 202607211200
Revises: 202607131200

This migration intentionally freezes the Module 5 schema instead of
importing application Base.metadata. Historical migrations must not change
when later ORM models evolve.
"""

from alembic import op
import sqlalchemy as sa


revision = "202607211200"
down_revision = "202607131200"
branch_labels = None
depends_on = None


metadata = sa.MetaData()


def enum_type(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name)


# ---------------------------------------------------------------------------
# Existing tables referenced by Module 5.
# These are metadata placeholders only; this migration does NOT create them.
# ---------------------------------------------------------------------------

sa.Table(
    "users",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
)

sa.Table(
    "catalog_items",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
)

sa.Table(
    "cms_media_files",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
)

sa.Table(
    "cms_content",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
)


# ---------------------------------------------------------------------------
# Historical Module 5 enums
# ---------------------------------------------------------------------------

channel_status = enum_type(
    "gntv_channel_status",
    "draft",
    "ready",
    "live",
    "degraded",
    "offline",
    "maintenance",
)

recording_policy = enum_type(
    "gntv_recording_policy",
    "always",
    "event",
    "manual",
    "never",
)

live_event_status = enum_type(
    "gntv_live_event_status",
    "scheduled",
    "ready",
    "live",
    "completed",
    "cancelled",
    "failed",
)

stream_protocol = enum_type(
    "gntv_stream_protocol",
    "rtmp",
    "srt",
)

stream_status = enum_type(
    "gntv_stream_status",
    "requested",
    "admitted",
    "probing",
    "starting",
    "live",
    "degraded",
    "stopping",
    "finalizing",
    "stopped",
    "retrying",
    "failed",
)

stream_key_status = enum_type(
    "gntv_stream_key_status",
    "active",
    "revoked",
    "expired",
)

recording_status = enum_type(
    "gntv_recording_status",
    "recording",
    "finalizing",
    "ready",
    "partial",
    "failed",
    "deleted",
)

playback_session_status = enum_type(
    "gntv_playback_session_status",
    "authorized",
    "playing",
    "paused",
    "ended",
    "revoked",
    "expired",
)

transcoding_job_type = enum_type(
    "gntv_transcoding_job_type",
    "probe",
    "live_transcode",
    "package",
    "finalize",
    "thumbnail",
)

transcoding_job_status = enum_type(
    "gntv_transcoding_job_status",
    "queued",
    "leased",
    "running",
    "retrying",
    "succeeded",
    "failed",
    "cancelled",
)

manifest_format = enum_type(
    "gntv_manifest_format",
    "hls",
    "dash",
)

manifest_kind = enum_type(
    "gntv_manifest_kind",
    "live",
    "event",
    "vod",
)

manifest_status = enum_type(
    "gntv_manifest_status",
    "building",
    "ready",
    "stale",
    "revoked",
    "failed",
)

thumbnail_kind = enum_type(
    "gntv_thumbnail_kind",
    "poster",
    "keyframe",
    "sprite",
    "preview",
)

thumbnail_status = enum_type(
    "gntv_thumbnail_status",
    "queued",
    "ready",
    "failed",
    "deleted",
)

distribution_target_type = enum_type(
    "gntv_distribution_target_type",
    "alibaba_cdn",
    "rtmp_relay",
    "youtube_live",
    "facebook_live",
)

distribution_target_status = enum_type(
    "gntv_distribution_target_status",
    "draft",
    "active",
    "disabled",
    "degraded",
    "failed",
)

geo_policy_mode = enum_type(
    "gntv_geo_policy_mode",
    "allowlist",
    "blocklist",
    "global",
)

geo_policy_status = enum_type(
    "gntv_geo_policy_status",
    "draft",
    "active",
    "disabled",
)

cdn_sync_status = enum_type(
    "gntv_cdn_sync_status",
    "pending",
    "synced",
    "failed",
)


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lock_version", sa.Integer, nullable=False),
    ]


live_channels = sa.Table(
    "live_channels",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "catalog_item_id",
        sa.Uuid,
        sa.ForeignKey("catalog_items.id", ondelete="SET NULL"),
    ),
    sa.Column("channel_code", sa.String(80), nullable=False, unique=True),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("slug", sa.String(220), nullable=False, unique=True),
    sa.Column("status", channel_status, nullable=False),
    sa.Column("ingest_policy", sa.JSON, nullable=False),
    sa.Column("transcode_profile", sa.String(100), nullable=False),
    sa.Column("recording_policy", recording_policy, nullable=False),
    sa.Column(
        "fallback_media_id",
        sa.Uuid,
        sa.ForeignKey("cms_media_files.id", ondelete="SET NULL"),
    ),
    sa.Column("is_public", sa.Boolean, nullable=False),
    sa.Column("timezone", sa.String(64), nullable=False),
    # Historical FK is added after live_events exists to break the cycle.
    sa.Column("current_event_id", sa.Uuid),
    sa.Column("primary_ingest_host", sa.String(500)),
    sa.Column("backup_ingest_host", sa.String(500)),
    sa.Column(
        "created_by",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column(
        "updated_by",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    *timestamp_columns(),
    sa.Index("idx_live_channels_status", "status"),
    sa.Index("idx_live_channels_catalog", "catalog_item_id"),
)


live_events = sa.Table(
    "live_events",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "live_channel_id",
        sa.Uuid,
        sa.ForeignKey("live_channels.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column(
        "content_id",
        sa.Uuid,
        sa.ForeignKey("cms_content.id", ondelete="SET NULL"),
    ),
    sa.Column(
        "catalog_item_id",
        sa.Uuid,
        sa.ForeignKey("catalog_items.id", ondelete="SET NULL"),
    ),
    sa.Column("title", sa.String(255), nullable=False),
    sa.Column("status", live_event_status, nullable=False),
    sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("actual_start_at", sa.DateTime(timezone=True)),
    sa.Column("actual_end_at", sa.DateTime(timezone=True)),
    sa.Column("recording_required", sa.Boolean, nullable=False),
    sa.Column(
        "created_by",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column(
        "updated_by",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    *timestamp_columns(),
    sa.CheckConstraint(
        "scheduled_end_at > scheduled_start_at",
        name="ck_live_event_schedule_order",
    ),
    sa.CheckConstraint(
        "actual_end_at IS NULL OR actual_start_at IS NULL "
        "OR actual_end_at >= actual_start_at",
        name="ck_live_event_actual_order",
    ),
    sa.Index(
        "idx_live_events_channel_schedule",
        "live_channel_id",
        "scheduled_start_at",
    ),
    sa.Index(
        "idx_live_events_status_schedule",
        "status",
        "scheduled_start_at",
    ),
)


stream_keys = sa.Table(
    "stream_keys",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "live_channel_id",
        sa.Uuid,
        sa.ForeignKey("live_channels.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("key_prefix", sa.String(32), nullable=False, unique=True),
    sa.Column("secret_hash", sa.String(255), nullable=False),
    sa.Column("status", stream_key_status, nullable=False),
    sa.Column("allowed_protocols", sa.JSON, nullable=False),
    sa.Column("allowed_cidrs", sa.JSON, nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True)),
    sa.Column("last_used_at", sa.DateTime(timezone=True)),
    sa.Column(
        "created_by",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column(
        "revoked_by",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    ),
    *timestamp_columns(),
    sa.Index(
        "idx_stream_keys_channel_status",
        "live_channel_id",
        "status",
    ),
    sa.Index("idx_stream_keys_expiry", "expires_at"),
)


streams = sa.Table(
    "streams",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "live_channel_id",
        sa.Uuid,
        sa.ForeignKey("live_channels.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column(
        "live_event_id",
        sa.Uuid,
        sa.ForeignKey("live_events.id", ondelete="SET NULL"),
    ),
    sa.Column(
        "stream_key_id",
        sa.Uuid,
        sa.ForeignKey("stream_keys.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("protocol", stream_protocol, nullable=False),
    sa.Column("status", stream_status, nullable=False),
    sa.Column("gateway_node", sa.String(160)),
    sa.Column("worker_node", sa.String(160)),
    sa.Column("source_metadata", sa.JSON, nullable=False),
    sa.Column("health", sa.JSON, nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("stopped_at", sa.DateTime(timezone=True)),
    sa.Column("last_heartbeat_at", sa.DateTime(timezone=True)),
    sa.Column("failure_code", sa.String(100)),
    sa.Column("failure_detail", sa.Text),
    sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
    sa.Column(
        "created_by",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column(
        "updated_by",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    *timestamp_columns(),
    sa.Index("idx_streams_channel_status", "live_channel_id", "status"),
    sa.Index("idx_streams_status_heartbeat", "status", "last_heartbeat_at"),
    sa.Index("idx_streams_event", "live_event_id"),
)


recordings = sa.Table(
    "recordings",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "stream_id",
        sa.Uuid,
        sa.ForeignKey("streams.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column(
        "live_event_id",
        sa.Uuid,
        sa.ForeignKey("live_events.id", ondelete="SET NULL"),
    ),
    sa.Column(
        "media_file_id",
        sa.Uuid,
        sa.ForeignKey("cms_media_files.id", ondelete="SET NULL"),
    ),
    sa.Column("status", recording_status, nullable=False),
    sa.Column("oss_prefix", sa.String(1024), nullable=False),
    sa.Column("duration_ms", sa.BigInteger),
    sa.Column("size_bytes", sa.BigInteger),
    sa.Column("checksum", sa.String(128)),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("ended_at", sa.DateTime(timezone=True)),
    sa.Column("retention_until", sa.DateTime(timezone=True)),
    sa.Column("failure_code", sa.String(100)),
    sa.Column("failure_detail", sa.Text),
    sa.Column(
        "created_by",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column(
        "updated_by",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    *timestamp_columns(),
    sa.CheckConstraint(
        "duration_ms IS NULL OR duration_ms >= 0",
        name="ck_recording_duration",
    ),
    sa.CheckConstraint(
        "size_bytes IS NULL OR size_bytes >= 0",
        name="ck_recording_size",
    ),
    sa.CheckConstraint(
        "ended_at IS NULL OR ended_at >= started_at",
        name="ck_recording_time_order",
    ),
    sa.Index("idx_recordings_stream", "stream_id"),
    sa.Index("idx_recordings_event", "live_event_id"),
    sa.Index("idx_recordings_status_ended", "status", "ended_at"),
)


playback_sessions = sa.Table(
    "playback_sessions",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "user_id",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="SET NULL"),
    ),
    sa.Column(
        "live_channel_id",
        sa.Uuid,
        sa.ForeignKey("live_channels.id", ondelete="RESTRICT"),
    ),
    sa.Column(
        "recording_id",
        sa.Uuid,
        sa.ForeignKey("recordings.id", ondelete="RESTRICT"),
    ),
    sa.Column(
        "catalog_item_id",
        sa.Uuid,
        sa.ForeignKey("catalog_items.id", ondelete="RESTRICT"),
    ),
    sa.Column("device_id", sa.String(160), nullable=False),
    sa.Column("token_jti_hash", sa.String(128), nullable=False, unique=True),
    sa.Column("status", playback_session_status, nullable=False),
    sa.Column("country_code", sa.String(2)),
    sa.Column("ip_hash", sa.String(128)),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("last_seen_at", sa.DateTime(timezone=True)),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("position_ms", sa.BigInteger, nullable=False),
    sa.Column("policy_version", sa.Integer, nullable=False),
    *timestamp_columns(),
    sa.CheckConstraint(
        "(CASE WHEN live_channel_id IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN recording_id IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN catalog_item_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
        name="ck_playback_exactly_one_target",
    ),
    sa.CheckConstraint(
        "position_ms >= 0",
        name="ck_playback_position",
    ),
    sa.CheckConstraint(
        "country_code IS NULL OR length(country_code) = 2",
        name="ck_playback_country_code",
    ),
    sa.Index("idx_playback_sessions_user_status", "user_id", "status"),
    sa.Index(
        "idx_playback_sessions_channel_status",
        "live_channel_id",
        "status",
    ),
    sa.Index(
        "idx_playback_sessions_recording_status",
        "recording_id",
        "status",
    ),
    sa.Index("idx_playback_sessions_expiry", "expires_at"),
)


transcoding_jobs = sa.Table(
    "transcoding_jobs",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "stream_id",
        sa.Uuid,
        sa.ForeignKey("streams.id", ondelete="RESTRICT"),
    ),
    sa.Column(
        "recording_id",
        sa.Uuid,
        sa.ForeignKey("recordings.id", ondelete="RESTRICT"),
    ),
    sa.Column("job_type", transcoding_job_type, nullable=False),
    sa.Column("queue", sa.String(80), nullable=False),
    sa.Column("capability", sa.String(100)),
    sa.Column("input_source", sa.String(2048)),
    sa.Column("output_prefix", sa.String(512)),
    sa.Column("renditions", sa.JSON, nullable=False),
    sa.Column("status", transcoding_job_status, nullable=False),
    sa.Column("attempt", sa.Integer, nullable=False),
    sa.Column("max_attempts", sa.Integer, nullable=False),
    sa.Column("worker_id", sa.String(160)),
    sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
    sa.Column("progress", sa.JSON, nullable=False),
    sa.Column("error_code", sa.String(100)),
    sa.Column("error_detail", sa.Text),
    sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
    *timestamp_columns(),
    sa.CheckConstraint(
        "stream_id IS NOT NULL OR recording_id IS NOT NULL "
        "OR input_source IS NOT NULL",
        name="ck_transcoding_job_has_source",
    ),
    sa.CheckConstraint(
        "attempt >= 0 AND max_attempts > 0",
        name="ck_transcoding_job_attempts",
    ),
    sa.CheckConstraint(
        "completed_at IS NULL OR started_at IS NULL "
        "OR completed_at >= started_at",
        name="ck_transcoding_job_time_order",
    ),
    sa.Index(
        "idx_transcoding_jobs_queue_status",
        "queue",
        "status",
    ),
    sa.Index(
        "idx_transcoding_jobs_lease",
        "lease_expires_at",
    ),
)


manifests = sa.Table(
    "manifests",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "stream_id",
        sa.Uuid,
        sa.ForeignKey("streams.id", ondelete="RESTRICT"),
    ),
    sa.Column(
        "recording_id",
        sa.Uuid,
        sa.ForeignKey("recordings.id", ondelete="RESTRICT"),
    ),
    sa.Column("format", manifest_format, nullable=False),
    sa.Column("kind", manifest_kind, nullable=False),
    sa.Column("status", manifest_status, nullable=False),
    sa.Column("oss_object_key", sa.String(1024), nullable=False),
    sa.Column("cdn_path", sa.String(1024), nullable=False),
    sa.Column("generation", sa.Integer, nullable=False),
    sa.Column("renditions", sa.JSON, nullable=False),
    sa.Column("published_at", sa.DateTime(timezone=True)),
    sa.Column("revoked_at", sa.DateTime(timezone=True)),
    *timestamp_columns(),
    sa.CheckConstraint(
        "stream_id IS NOT NULL OR recording_id IS NOT NULL",
        name="ck_manifest_has_source",
    ),
    sa.CheckConstraint(
        "generation > 0",
        name="ck_manifest_generation",
    ),
    sa.UniqueConstraint(
        "stream_id",
        "recording_id",
        "format",
        "generation",
        name="uq_manifest_source_format_generation",
    ),
    sa.Index(
        "idx_manifests_stream_format_status",
        "stream_id",
        "format",
        "status",
    ),
    sa.Index(
        "idx_manifests_recording_format_status",
        "recording_id",
        "format",
        "status",
    ),
)


thumbnails = sa.Table(
    "thumbnails",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "recording_id",
        sa.Uuid,
        sa.ForeignKey("recordings.id", ondelete="RESTRICT"),
    ),
    sa.Column(
        "stream_id",
        sa.Uuid,
        sa.ForeignKey("streams.id", ondelete="RESTRICT"),
    ),
    sa.Column(
        "media_file_id",
        sa.Uuid,
        sa.ForeignKey("cms_media_files.id", ondelete="SET NULL"),
    ),
    sa.Column("kind", thumbnail_kind, nullable=False),
    sa.Column("timestamp_ms", sa.BigInteger),
    sa.Column("width", sa.Integer, nullable=False),
    sa.Column("height", sa.Integer, nullable=False),
    sa.Column("oss_object_key", sa.String(1024), nullable=False),
    sa.Column("status", thumbnail_status, nullable=False),
    *timestamp_columns(),
    sa.CheckConstraint(
        "recording_id IS NOT NULL OR stream_id IS NOT NULL",
        name="ck_thumbnail_has_source",
    ),
    sa.CheckConstraint(
        "timestamp_ms IS NULL OR timestamp_ms >= 0",
        name="ck_thumbnail_timestamp",
    ),
    sa.CheckConstraint(
        "width > 0 AND height > 0",
        name="ck_thumbnail_dimensions",
    ),
    sa.Index(
        "idx_thumbnails_recording_kind_time",
        "recording_id",
        "kind",
        "timestamp_ms",
    ),
    sa.Index("idx_thumbnails_stream", "stream_id"),
)


distribution_targets = sa.Table(
    "distribution_targets",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "live_channel_id",
        sa.Uuid,
        sa.ForeignKey("live_channels.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("name", sa.String(160), nullable=False),
    sa.Column("target_type", distribution_target_type, nullable=False),
    sa.Column("status", distribution_target_status, nullable=False),
    sa.Column("endpoint_ciphertext", sa.LargeBinary, nullable=False),
    sa.Column("credential_ciphertext", sa.LargeBinary, nullable=False),
    sa.Column("kms_key_id", sa.String(255), nullable=False),
    sa.Column("encrypted_data_key", sa.LargeBinary, nullable=False),
    sa.Column("public_config", sa.JSON, nullable=False),
    sa.Column("last_health_at", sa.DateTime(timezone=True)),
    sa.Column("last_success_at", sa.DateTime(timezone=True)),
    sa.Column("failure_code", sa.String(100)),
    sa.Column("failure_detail", sa.String(500)),
    sa.Column(
        "created_by",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column(
        "updated_by",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    *timestamp_columns(),
    sa.UniqueConstraint(
        "live_channel_id",
        "name",
        name="uq_distribution_target_channel_name",
    ),
    sa.Index(
        "idx_distribution_targets_channel_status",
        "live_channel_id",
        "status",
    ),
    sa.Index(
        "idx_distribution_targets_type_status",
        "target_type",
        "status",
    ),
)


geofencing_policies = sa.Table(
    "geofencing_policies",
    metadata,
    sa.Column("id", sa.Uuid, primary_key=True),
    sa.Column(
        "content_id",
        sa.Uuid,
        sa.ForeignKey("cms_content.id", ondelete="RESTRICT"),
    ),
    sa.Column(
        "catalog_item_id",
        sa.Uuid,
        sa.ForeignKey("catalog_items.id", ondelete="RESTRICT"),
    ),
    sa.Column(
        "live_channel_id",
        sa.Uuid,
        sa.ForeignKey("live_channels.id", ondelete="RESTRICT"),
    ),
    sa.Column("policy_mode", geo_policy_mode, nullable=False),
    sa.Column("allowed_countries", sa.JSON, nullable=False),
    sa.Column("blocked_countries", sa.JSON, nullable=False),
    sa.Column("status", geo_policy_status, nullable=False),
    sa.Column("starts_at", sa.DateTime(timezone=True)),
    sa.Column("ends_at", sa.DateTime(timezone=True)),
    sa.Column("policy_version", sa.Integer, nullable=False),
    sa.Column("cdn_sync_status", cdn_sync_status, nullable=False),
    sa.Column("cdn_synced_at", sa.DateTime(timezone=True)),
    sa.Column(
        "created_by",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column(
        "updated_by",
        sa.Integer,
        sa.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    *timestamp_columns(),
    sa.CheckConstraint(
        "(CASE WHEN content_id IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN catalog_item_id IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN live_channel_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
        name="ck_geofence_exactly_one_target",
    ),
    sa.CheckConstraint(
        "ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at",
        name="ck_geofence_time_order",
    ),
    sa.CheckConstraint(
        "policy_version > 0",
        name="ck_geofence_policy_version",
    ),
    sa.Index(
        "idx_geofencing_policies_content_status",
        "content_id",
        "status",
    ),
    sa.Index(
        "idx_geofencing_policies_catalog_status",
        "catalog_item_id",
        "status",
    ),
    sa.Index(
        "idx_geofencing_policies_channel_status",
        "live_channel_id",
        "status",
    ),
    sa.Index(
        "idx_geofencing_policies_sync",
        "cdn_sync_status",
    ),
)


MODULE5_TABLES = (
    live_channels,
    live_events,
    stream_keys,
    streams,
    recordings,
    playback_sessions,
    transcoding_jobs,
    manifests,
    thumbnails,
    distribution_targets,
    geofencing_policies,
)


def upgrade() -> None:
    bind = op.get_bind()

    for table in MODULE5_TABLES:
        table.create(bind, checkfirst=True)

    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_live_channels_current_event",
            "live_channels",
            "live_events",
            ["current_event_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name != "sqlite":
        op.drop_constraint(
            "fk_live_channels_current_event",
            "live_channels",
            type_="foreignkey",
        )

    for table in reversed(MODULE5_TABLES):
        table.drop(bind, checkfirst=True)
