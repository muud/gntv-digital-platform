"""Strict Celery payloads for media worker queues."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.streaming.media.profiles import RenditionName


class MediaContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TranscodeTaskPayload(MediaContract):
    job_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)
    input_source: str = Field(min_length=1, max_length=2048)
    output_prefix: str = Field(min_length=1, max_length=512)
    renditions: tuple[RenditionName, ...] = ("1080p", "720p", "480p")
    enqueued_at: datetime
    attempt: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=3, ge=1, le=10)
    timeout_seconds: float = Field(default=900, ge=1, le=86_400)
    live: bool = True

    @field_validator("renditions")
    @classmethod
    def exact_unique_renditions(
        cls, values: tuple[RenditionName, ...]
    ) -> tuple[RenditionName, ...]:
        if not values or len(set(values)) != len(values):
            raise ValueError("renditions must be a non-empty unique list")
        return values


class ManifestTaskPayload(MediaContract):
    job_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)
    workspace: str = Field(min_length=1, max_length=1024)
    output_prefix: str = Field(min_length=1, max_length=512)
    renditions: tuple[RenditionName, ...] = ("1080p", "720p", "480p")
    enqueued_at: datetime


class ThumbnailTaskPayload(MediaContract):
    job_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=128)
    input_source: str = Field(min_length=1, max_length=2048)
    workspace: str = Field(min_length=1, max_length=1024)
    kinds: tuple[Literal["poster", "preview", "timeline"], ...] = (
        "poster",
        "preview",
        "timeline",
    )
    interval_seconds: int = Field(default=10, ge=1, le=3600)
    enqueued_at: datetime
    timeout_seconds: float = Field(default=300, ge=1, le=3600)

    @model_validator(mode="after")
    def unique_kinds(self) -> Self:
        if len(set(self.kinds)) != len(self.kinds):
            raise ValueError("thumbnail kinds must be unique")
        return self


class ProbeVideoStream(MediaContract):
    codec_type: Literal["video"]
    codec_name: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    pix_fmt: str | None = None
    avg_frame_rate: str


class ProbeAudioStream(MediaContract):
    codec_type: Literal["audio"]
    codec_name: str
    sample_rate: int = Field(gt=0)
    channels: int = Field(gt=0)


class ProbeResult(MediaContract):
    format_name: str
    duration_seconds: float | None = Field(default=None, ge=0)
    video: ProbeVideoStream
    audio: ProbeAudioStream


__all__ = [
    "ManifestTaskPayload",
    "ProbeAudioStream",
    "ProbeResult",
    "ProbeVideoStream",
    "ThumbnailTaskPayload",
    "TranscodeTaskPayload",
]
