"""Strict REST contracts for the Sprint 5.3 Processing Operations Center."""

from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.streaming.media.profiles import RenditionName
from app.modules.streaming.models import (
    ManifestFormat,
    ManifestKind,
    ManifestStatus,
    ThumbnailKind,
    ThumbnailStatus,
)


class ProcessingContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


ProcessingJobType = Literal["vod_transcode", "live_transcode", "manifest", "thumbnail"]
ProcessingQueue = Literal["transcode-cpu", "transcode-accelerated", "manifest", "thumbnail"]
ProcessingPermission = Literal["channel:read-operations", "stream:control"]


class ProcessingErrorDetail(ProcessingContract):
    code: Literal["processing_not_found", "processing_conflict"]
    message: str


class ProcessingForbiddenDetail(ProcessingContract):
    code: Literal["streaming_forbidden"]
    required_scope: ProcessingPermission


class ProcessingErrorResponse(ProcessingContract):
    detail: str | ProcessingErrorDetail | ProcessingForbiddenDetail


class ProcessingJobCreateRequest(ProcessingContract):
    idempotency_key: str = Field(min_length=8, max_length=128)
    job_type: ProcessingJobType
    input_url: str = Field(min_length=1, max_length=2048)
    output_prefix: str = Field(min_length=1, max_length=512)
    renditions: tuple[RenditionName, ...] = ("1080p", "720p", "480p")
    queue: ProcessingQueue | None = None
    stream_id: UUID | None = None
    recording_id: UUID | None = None
    max_attempts: int = Field(default=3, ge=1, le=10)
    timeout_seconds: float = Field(default=900, ge=1, le=86_400)
    workspace: str | None = Field(default=None, min_length=1, max_length=1024)
    thumbnail_kinds: tuple[Literal["poster", "preview", "timeline"], ...] = (
        "poster",
        "preview",
        "timeline",
    )
    thumbnail_interval_seconds: int = Field(default=10, ge=1, le=3600)

    @model_validator(mode="after")
    def valid_task_shape(self) -> Self:
        if not self.renditions or len(set(self.renditions)) != len(self.renditions):
            raise ValueError("renditions must be a non-empty unique list")
        if len(set(self.thumbnail_kinds)) != len(self.thumbnail_kinds):
            raise ValueError("thumbnail_kinds must be unique")
        expected = {
            "vod_transcode": {"transcode-cpu", "transcode-accelerated"},
            "live_transcode": {"transcode-cpu", "transcode-accelerated"},
            "manifest": {"manifest"},
            "thumbnail": {"thumbnail"},
        }[self.job_type]
        if self.queue is not None and self.queue not in expected:
            raise ValueError("queue is not approved for this processing job type")
        if self.job_type in {"manifest", "thumbnail"} and self.workspace is None:
            raise ValueError("workspace is required for manifest and thumbnail jobs")
        return self


class ProcessingJobResponse(ProcessingContract):
    job_id: UUID
    job_type: ProcessingJobType
    status: str
    queue: str
    attempt: int
    max_attempts: int
    progress: float
    metrics: dict[str, Any]
    worker_id: str | None
    error_code: str | None
    error_detail: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ProcessingJobPage(ProcessingContract):
    items: list[ProcessingJobResponse]
    total: int


class ProcessingJobCancelResponse(ProcessingContract):
    job_id: UUID
    status: Literal["CANCELLED"]
    terminated_at: datetime


class WorkerHardware(ProcessingContract):
    device: str | None = None
    cpu_usage_pct: float | None = None
    gpu_usage_pct: float | None = None
    vram_allocated_mb: int | None = None
    temperature_celsius: float | None = None


class WorkerStatusResponse(ProcessingContract):
    worker_id: str
    hostname: str | None = None
    queue: str
    status: str
    healthy: bool
    last_heartbeat: datetime
    hardware: WorkerHardware = Field(default_factory=WorkerHardware)


class QueueStatus(ProcessingContract):
    messages_queued: int
    messages_leased: int
    messages_running: int
    messages_retrying: int
    active_workers: int


class QueueTelemetryResponse(ProcessingContract):
    broker: str
    queues: dict[str, QueueStatus]


class ManifestStatusResponse(ProcessingContract):
    manifest_id: UUID
    stream_id: UUID | None
    recording_id: UUID | None
    format: ManifestFormat
    kind: ManifestKind
    status: ManifestStatus
    manifest_path: str
    generation: int
    renditions: list[dict[str, Any]]
    published_at: datetime | None


class ManifestPage(ProcessingContract):
    items: list[ManifestStatusResponse]
    total: int


class ManifestValidationRequest(ProcessingContract):
    manifest_url: str = Field(min_length=1, max_length=1024)


class ManifestValidationResponse(ProcessingContract):
    valid: bool
    format: ManifestFormat | None
    conformance: str
    validations: dict[str, Any]


class ThumbnailStatusResponse(ProcessingContract):
    thumbnail_id: UUID
    stream_id: UUID | None
    recording_id: UUID | None
    media_file_id: UUID | None
    kind: ThumbnailKind
    timestamp_ms: int | None
    width: int
    height: int
    status: ThumbnailStatus
    asset_path: str


class ThumbnailPage(ProcessingContract):
    items: list[ThumbnailStatusResponse]
    total: int


class ProcessingMetricsResponse(ProcessingContract):
    job_id: UUID
    queue: str | None = None
    processing_duration_seconds: float | None = None
    queue_wait_time_seconds: float | None = None
    encoding_fps: float | None = None
    encoding_speed_factor: float | None = None
    cpu_usage_percent: float | None = None
    dropped_frames: int | None = None
    manifest_freshness_seconds: float | None = None
    observed_at: datetime | None = None


class MetricsPage(ProcessingContract):
    items: list[ProcessingMetricsResponse]
    total: int
