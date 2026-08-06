"""Pydantic v2 API and domain contracts for Module 5 streaming."""

from datetime import datetime
from enum import StrEnum
from ipaddress import ip_network
from typing import Any, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.streaming.models import (
    ChannelStatus,
    LiveEventStatus,
    ManifestFormat,
    ManifestKind,
    ManifestStatus,
    PlaybackSessionStatus,
    RecordingPolicy,
    RecordingStatus,
    StreamProtocol,
    StreamStatus,
    ThumbnailKind,
    ThumbnailStatus,
    TranscodingJobStatus,
    TranscodingJobType,
)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ApiErrorResponse(ContractModel):
    code: str
    message: str
    request_id: str | None = None
    details: dict[str, Any] | None = None


class CursorPageMeta(ContractModel):
    next_cursor: str | None = None
    has_more: bool = False
    limit: int = Field(ge=1, le=100)


class IngestPolicy(ContractModel):
    allowed_protocols: set[StreamProtocol] = Field(min_length=1)
    redundancy: Literal["primary_only", "primary_backup"] = "primary_only"


class LiveChannelCreateRequest(ContractModel):
    channel_code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=220, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    catalog_item_id: UUID | None = None
    ingest_policy: IngestPolicy
    transcode_profile: str = Field(min_length=1, max_length=100)
    recording_policy: RecordingPolicy = RecordingPolicy.MANUAL
    fallback_media_id: UUID | None = None
    is_public: bool = False
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    primary_ingest_host: str | None = Field(default=None, max_length=500)
    backup_ingest_host: str | None = Field(default=None, max_length=500)
    dvr_window_seconds: int = Field(default=7200, ge=0, le=604800)
    catchup_retention_days: int = Field(default=7, ge=0, le=365)
    dvr_enabled: bool = False

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def valid_backup_policy(self) -> Self:
        if self.ingest_policy.redundancy == "primary_backup" and not self.backup_ingest_host:
            raise ValueError("backup_ingest_host is required for primary_backup redundancy")
        return self


class LiveChannelResponse(ContractModel):
    id: UUID
    catalog_item_id: UUID | None
    channel_code: str
    name: str
    slug: str
    status: ChannelStatus
    ingest_policy: dict[str, Any]
    transcode_profile: str
    recording_policy: RecordingPolicy
    fallback_media_id: UUID | None
    is_public: bool
    timezone: str
    current_event_id: UUID | None
    primary_ingest_host: str | None
    backup_ingest_host: str | None
    dvr_window_seconds: int = 7200
    catchup_retention_days: int = 7
    dvr_enabled: bool = False
    created_at: datetime
    updated_at: datetime
    lock_version: int


class LiveChannelPageResponse(ContractModel):
    items: list[LiveChannelResponse]
    page: CursorPageMeta


class LiveEventResponse(ContractModel):
    id: UUID
    live_channel_id: UUID
    content_id: UUID | None
    catalog_item_id: UUID | None
    title: str
    status: LiveEventStatus
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    actual_start_at: datetime | None
    actual_end_at: datetime | None
    recording_required: bool
    created_at: datetime
    updated_at: datetime
    lock_version: int


class StreamCreateRequest(ContractModel):
    live_channel_id: UUID
    live_event_id: UUID | None = None
    protocol: StreamProtocol
    stream_key_id: UUID
    requested_profile: str | None = Field(default=None, max_length=100)


class StreamStartRequest(ContractModel):
    stream_id: UUID
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)


class StopMode(StrEnum):
    GRACEFUL = "graceful"
    EMERGENCY = "emergency"


class StreamStopRequest(ContractModel):
    stream_id: UUID
    expected_version: int = Field(ge=1)
    mode: StopMode = StopMode.GRACEFUL
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def emergency_requires_reason(self) -> Self:
        if self.mode == StopMode.EMERGENCY and not self.reason:
            raise ValueError("reason is required for emergency stop")
        return self


class StreamResponse(ContractModel):
    id: UUID
    live_channel_id: UUID
    live_event_id: UUID | None
    stream_key_id: UUID
    protocol: StreamProtocol
    status: StreamStatus
    gateway_node: str | None
    worker_node: str | None
    source_metadata: dict[str, Any]
    health: dict[str, Any]
    started_at: datetime | None
    stopped_at: datetime | None
    last_heartbeat_at: datetime | None
    failure_code: str | None
    failure_detail: str | None
    created_at: datetime
    updated_at: datetime
    lock_version: int


class StreamAcceptedResponse(ContractModel):
    stream: StreamResponse
    ingest_destination: str
    status_url: str


class StreamPageResponse(ContractModel):
    items: list[StreamResponse]
    page: CursorPageMeta


class StreamCommandAcceptedResponse(ContractModel):
    command_id: UUID
    stream_id: UUID
    status: Literal["accepted"] = "accepted"
    status_url: str


class StreamKeyRotateRequest(ContractModel):
    expected_version: int = Field(ge=1)
    overlap_seconds: int = Field(default=0, ge=0, le=3600)
    allowed_protocols: set[StreamProtocol] = Field(min_length=1)
    allowed_cidrs: list[str] = Field(default_factory=list, max_length=32)
    expires_at: datetime | None = None
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("allowed_cidrs")
    @classmethod
    def valid_cidrs(cls, values: list[str]) -> list[str]:
        for value in values:
            ip_network(value, strict=False)
        return values


class StreamKeyCreatedResponse(ContractModel):
    id: UUID
    live_channel_id: UUID
    stream_key: str
    key_prefix: str
    allowed_protocols: list[StreamProtocol]
    expires_at: datetime | None
    created_at: datetime


class ApsaraCallbackEvent(ContractModel):
    event_id: str = Field(min_length=1, max_length=200)
    event_type: str = Field(min_length=1, max_length=120)
    event_time: datetime
    application: str = Field(min_length=1, max_length=120)
    channel_code: str = Field(min_length=1, max_length=80)
    stream_identifier: str = Field(min_length=1, max_length=255)
    payload_version: str = Field(min_length=1, max_length=20)
    recording_object_key: str | None = Field(default=None, max_length=1024)
    live_channel_id: UUID | None = None
    live_event_id: UUID | None = None
    stream_id: UUID | None = None
    recording_id: UUID | None = None
    segment_uri: str | None = Field(default=None, max_length=2048)
    sequence_number: int | None = Field(default=None, ge=0)
    segment_start_at: datetime | None = None
    segment_end_at: datetime | None = None
    duration_seconds: float | None = Field(default=None, gt=0)
    rendition: str = Field(default="source", min_length=1, max_length=80)
    data: dict[str, Any] = Field(default_factory=dict)


class CallbackAcceptedResponse(ContractModel):
    provider_event_id: str
    idempotency_outcome: Literal["accepted", "duplicate"]
    correlation_id: str


class PlaybackResolveQuery(ContractModel):
    protocol: ManifestFormat | None = None
    device_id: str = Field(min_length=1, max_length=160)


class PlaybackMode(StrEnum):
    LIVE = "live"
    VOD = "vod"


class PlaybackTokenRequest(ContractModel):
    live_channel_id: UUID | None = None
    recording_id: UUID | None = None
    catalog_item_id: UUID | None = None
    device_id: str = Field(min_length=1, max_length=160)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    requested_protocol: ManifestFormat | None = None

    @model_validator(mode="after")
    def exactly_one_target(self) -> Self:
        if sum(value is not None for value in (self.live_channel_id, self.recording_id, self.catalog_item_id)) != 1:
            raise ValueError("exactly one playback target is required")
        return self


class PlaybackAuthorizationResponse(ContractModel):
    playback_session_id: UUID
    playback_url: str
    manifest_type: Literal["hls"] = "hls"
    expires_at: datetime
    content_id: UUID
    playback_mode: PlaybackMode
    heartbeat_interval_seconds: int = Field(gt=0)
    policy_version: int = Field(ge=1)


class PlaybackTokenResponse(ContractModel):
    playback_session_id: UUID
    token: str
    expires_at: datetime
    protocol: ManifestFormat
    policy_version: int = Field(ge=1)
    heartbeat_interval_seconds: int = Field(gt=0)
    signed_url: str


class PlaybackPathValidationResponse(ContractModel):
    valid: Literal[True] = True
    path: str
    expires_at: datetime
    playback_session_id: UUID
    policy_version: int = Field(ge=1)


class PlaybackSessionResponse(ContractModel):
    id: UUID
    user_id: int | None
    live_channel_id: UUID | None
    recording_id: UUID | None
    catalog_item_id: UUID | None
    device_id: str
    status: PlaybackSessionStatus
    country_code: str | None
    started_at: datetime | None
    last_seen_at: datetime | None
    expires_at: datetime
    position_ms: int
    policy_version: int


class PlaybackHeartbeatRequest(ContractModel):
    position_ms: int = Field(default=0, ge=0)
    state: PlaybackSessionStatus = PlaybackSessionStatus.PLAYING
    bitrate_bps: int | None = Field(default=None, ge=0)


class PlaybackHeartbeatResponse(ContractModel):
    session_id: UUID
    status: PlaybackSessionStatus
    next_heartbeat_seconds: int = Field(gt=0)
    position_ms: int = Field(ge=0)


class PlaybackStopRequest(ContractModel):
    position_ms: int = Field(default=0, ge=0)


class PlaybackStopResponse(ContractModel):
    session_id: UUID
    status: Literal["ended"] = "ended"
    final_position_ms: int = Field(ge=0)


class PlaybackRevokeRequest(ContractModel):
    reason: str | None = Field(default=None, max_length=500)


class PlaybackRevokeResponse(ContractModel):
    session_id: UUID
    status: Literal["revoked"] = "revoked"


class RecordingResponse(ContractModel):
    id: UUID
    stream_id: UUID
    live_event_id: UUID | None
    media_file_id: UUID | None
    status: RecordingStatus
    duration_ms: int | None
    size_bytes: int | None
    started_at: datetime
    ended_at: datetime | None
    retention_until: datetime | None
    start_sequence_number: int | None = None
    end_sequence_number: int | None = None
    epg_event_id: str | None = None
    created_at: datetime
    updated_at: datetime
    lock_version: int


class RecordingPageResponse(ContractModel):
    items: list[RecordingResponse]
    page: CursorPageMeta


class TranscodingJobResponse(ContractModel):
    id: UUID
    stream_id: UUID | None
    recording_id: UUID | None
    job_type: TranscodingJobType
    queue: str
    capability: str | None
    status: TranscodingJobStatus
    attempt: int
    max_attempts: int
    worker_id: str | None
    lease_expires_at: datetime | None
    progress: dict[str, Any]
    error_code: str | None
    started_at: datetime | None
    completed_at: datetime | None


class ManifestResponse(ContractModel):
    id: UUID
    stream_id: UUID | None
    recording_id: UUID | None
    format: ManifestFormat
    kind: ManifestKind
    status: ManifestStatus
    cdn_path: str
    generation: int
    renditions: list[dict[str, Any]]
    published_at: datetime | None
    revoked_at: datetime | None


class ThumbnailResponse(ContractModel):
    id: UUID
    recording_id: UUID | None
    stream_id: UUID | None
    media_file_id: UUID | None
    kind: ThumbnailKind
    timestamp_ms: int | None
    width: int
    height: int
    status: ThumbnailStatus


class DVRSegmentResponse(ContractModel):
    id: UUID
    live_channel_id: UUID
    stream_id: UUID | None
    live_event_id: UUID | None
    recording_id: UUID | None
    rendition: str
    sequence_number: int
    segment_uri: str
    segment_start_at: datetime
    segment_end_at: datetime
    duration_seconds: float
    provider_event_id: str | None
    apsara_object_key: str | None
    is_pruned: bool
    metadata_json: dict[str, Any]


class DVRSegmentIngestResponse(ContractModel):
    provider_event_id: str
    idempotency_outcome: Literal["accepted", "duplicate"]
    correlation_id: str
    segment: DVRSegmentResponse


class DRMTokenRequest(ContractModel):
    target_id: UUID
    device_id: str = Field(min_length=1, max_length=160)
    drm_system: Literal["widevine", "fairplay", "playready"]
    session_id: UUID | None = None


class DRMTokenResponse(ContractModel):
    drm_token: str
    license_server_url: str
    expires_at: datetime


class DRMLicenseChallengeRequest(ContractModel):
    challenge_b64: str = Field(min_length=1)


class GeoCheckResponse(ContractModel):
    allowed: bool
    country_code: str
    is_vpn: bool
    is_proxy: bool
    reason: str | None = None


class WatermarkTokenResponse(ContractModel):
    session_id: UUID
    text: str
    opacity: float
    ab_sequence: str
    interval_seconds: int
