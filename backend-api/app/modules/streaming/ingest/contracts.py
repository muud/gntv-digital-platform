"""Strict contracts exchanged with trusted RTMP/SRT gateway adapters."""

from datetime import datetime
from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress, SecretStr, field_validator

from app.modules.streaming.models import StreamProtocol, StreamStatus


class IngestContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EncoderRegistrationRequest(IngestContract):
    encoder_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    connection_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    gateway_node: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    protocol: StreamProtocol
    source_ip: IPvAnyAddress
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    firmware: str | None = Field(default=None, max_length=120)
    capabilities: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("capabilities")
    @classmethod
    def normalize_capabilities(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().lower() for value in values]
        if any(not value or len(value) > 64 for value in normalized):
            raise ValueError("capabilities must contain non-empty values of at most 64 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("capabilities must be unique")
        return normalized


class EncoderRegistrationResponse(IngestContract):
    registration_id: UUID
    encoder_id: str
    protocol: StreamProtocol
    expires_at: datetime


class AdmissionBase(IngestContract):
    stream_key: SecretStr
    encoder_registration_id: UUID
    encoder_id: str = Field(min_length=1, max_length=128)
    connection_id: str = Field(min_length=8, max_length=128)
    gateway_node: str = Field(min_length=1, max_length=160)
    source_ip: IPvAnyAddress
    live_event_id: UUID | None = None


class RTMPAdmissionRequest(AdmissionBase):
    application: str = Field(min_length=1, max_length=120)
    stream_name: str = Field(min_length=1, max_length=255)
    tls: bool


class SRTAdmissionRequest(AdmissionBase):
    stream_id: str = Field(min_length=1, max_length=255)
    mode: Literal["caller", "listener"]
    encryption: Literal["aes128", "aes256"]
    latency_ms: int = Field(ge=20, le=8000)


class IngestAdmissionResponse(IngestContract):
    stream_id: UUID
    live_channel_id: UUID
    protocol: StreamProtocol
    status: StreamStatus
    lease_expires_at: datetime
    status_url: str


class IngestEventType(StrEnum):
    STARTED = "started"
    DEGRADED = "degraded"
    RECOVERED = "recovered"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


class IngestHealthMetrics(IngestContract):
    bitrate_kbps: int | None = Field(default=None, ge=0, le=1_000_000)
    packet_loss_percent: float | None = Field(default=None, ge=0, le=100)
    rtt_ms: float | None = Field(default=None, ge=0, le=120_000)
    retransmissions: int | None = Field(default=None, ge=0)
    receiver_buffer_ms: int | None = Field(default=None, ge=0, le=120_000)
    connection_uptime_seconds: int | None = Field(default=None, ge=0)
    input_fps: float | None = Field(default=None, ge=0, le=240)
    audio_bitrate_kbps: int | None = Field(default=None, ge=0, le=10_000)


class IngestStateEventRequest(IngestContract):
    event: IngestEventType
    expected_version: int = Field(ge=1)
    reason_code: str | None = Field(default=None, max_length=100, pattern=r"^[a-z0-9_.-]+$")
    reason_detail: str | None = Field(default=None, max_length=500)
    health: IngestHealthMetrics = Field(default_factory=IngestHealthMetrics)


class IngestHeartbeatRequest(IngestContract):
    expected_version: int = Field(ge=1)
    health: IngestHealthMetrics = Field(default_factory=IngestHealthMetrics)


class IngestSessionResponse(IngestContract):
    stream_id: UUID
    status: StreamStatus
    lock_version: int
    last_heartbeat_at: datetime | None
    lease_expires_at: datetime | None = None


class IngestHealthResponse(IngestContract):
    status: Literal["ok", "degraded"]
    database: Literal["connected", "unavailable", "not_checked"]
    redis: Literal["connected", "unavailable", "not_checked"]
    dispatcher: Literal["configured", "unavailable", "not_checked"]


IPAddress = Annotated[IPv4Address | IPv6Address, Field()]


__all__ = [
    "EncoderRegistrationRequest",
    "EncoderRegistrationResponse",
    "IngestAdmissionResponse",
    "IngestEventType",
    "IngestHealthResponse",
    "IngestHealthMetrics",
    "IngestHeartbeatRequest",
    "IngestSessionResponse",
    "IngestStateEventRequest",
    "RTMPAdmissionRequest",
    "SRTAdmissionRequest",
]
