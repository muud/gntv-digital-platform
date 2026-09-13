"""Pydantic schemas for events, webhooks, DLQ, and event correlation tracing."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.events.models import (
    DeadLetterStatus,
    EventProcessingStatus,
    OutboundDeliveryStatus,
    WebhookDeliveryStatus,
)


class EventPublishRequest(BaseModel):
    """Schema for publishing an internal or external domain event."""

    event_type: str = Field(..., min_length=3, max_length=120)
    event_version: int = Field(default=1, ge=1)
    source: str = Field(..., min_length=2, max_length=120)
    tenant_id: str | None = Field(default=None, max_length=120)
    aggregate_type: str | None = Field(default=None, max_length=80)
    aggregate_id: str | None = Field(default=None, max_length=120)
    correlation_id: str | None = Field(default=None, max_length=120)
    causation_id: str | None = Field(default=None, max_length=120)
    idempotency_key: str | None = Field(default=None, max_length=160)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class DomainEventResponse(BaseModel):
    """Schema for returning persisted domain events."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    event_version: int
    source: str
    tenant_id: str | None = None
    aggregate_type: str | None = None
    aggregate_id: str | None = None
    correlation_id: str
    causation_id: str | None = None
    idempotency_key: str
    payload_json: dict[str, Any] | None = None
    status: EventProcessingStatus
    error_details_json: dict[str, Any] | None = None
    retry_count: int
    max_retries: int
    occurred_at: datetime
    received_at: datetime
    created_at: datetime
    updated_at: datetime


class WebhookSourceCreateRequest(BaseModel):
    """Schema for registering a new inbound webhook source."""

    source_key: str = Field(..., min_length=2, max_length=80)
    name: str = Field(..., min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    provider_type: str = Field(default="hmac_sha256", max_length=60)
    secret: str = Field(..., min_length=16, max_length=128, exclude=True)
    header_name: str = Field(default="X-Hub-Signature-256", max_length=80)
    timestamp_header: str | None = Field(default="X-GNTV-Timestamp", max_length=80)
    timestamp_tolerance_seconds: int = Field(default=300, ge=10, le=3600)
    payload_size_limit_bytes: int = Field(default=1_048_576, ge=1, le=10_485_760)
    event_type_mapping: dict[str, str] = Field(default_factory=dict)
    is_enabled: bool = True


class WebhookSourceUpdateRequest(BaseModel):
    """Schema for updating an inbound webhook source."""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    header_name: str | None = Field(default=None, max_length=80)
    timestamp_header: str | None = Field(default=None, max_length=80)
    timestamp_tolerance_seconds: int | None = Field(default=None, ge=10, le=3600)
    payload_size_limit_bytes: int | None = Field(
        default=None, ge=1, le=10_485_760
    )
    event_type_mapping: dict[str, str] | None = None
    is_enabled: bool | None = None


class WebhookSourceResponse(BaseModel):
    """Schema for inbound webhook sources."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_key: str
    name: str
    description: str | None = None
    provider_type: str
    header_name: str
    timestamp_header: str | None = None
    timestamp_tolerance_seconds: int
    payload_size_limit_bytes: int
    event_type_mapping_json: dict[str, Any] | None = None
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class WebhookDeliveryResponse(BaseModel):
    """Schema for inbound webhook deliveries."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    external_event_id: str | None = None
    delivery_fingerprint: str
    signature_valid: bool
    mapped_event_type: str | None = None
    status: WebhookDeliveryStatus
    linked_event_id: UUID | None = None
    safe_payload_json: dict[str, Any] | None = None
    rejection_reason: str | None = None
    received_at: datetime
    created_at: datetime


class OutboundSubscriptionCreateRequest(BaseModel):
    """Schema for creating an outbound webhook subscription."""

    name: str = Field(..., min_length=2, max_length=120)
    endpoint_url: str = Field(..., min_length=8, max_length=500)
    event_patterns: list[str] = Field(default_factory=list)
    secret: str = Field(..., min_length=16, max_length=128, exclude=True)
    max_retries: int = Field(default=3, ge=0, le=10)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    is_enabled: bool = True


class OutboundSubscriptionResponse(BaseModel):
    """Schema for outbound webhook subscriptions."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    endpoint_url: str
    event_patterns_json: list[str]
    is_enabled: bool
    max_retries: int
    timeout_seconds: int
    created_at: datetime
    updated_at: datetime


class OutboundDeliveryResponse(BaseModel):
    """Schema for outbound webhook deliveries."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subscription_id: UUID
    event_id: UUID
    status: OutboundDeliveryStatus
    attempt_count: int
    next_retry_at: datetime | None = None
    response_status_code: int | None = None
    response_body_truncated: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DeadLetterResponse(BaseModel):
    """Schema for dead letter queue records."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_id: UUID | None = None
    outbound_delivery_id: UUID | None = None
    reason: str
    retry_count: int
    status: DeadLetterStatus
    dismissed_by_user_id: int | None = None
    dismissed_at: datetime | None = None
    created_at: datetime


class EventMetricsSummary(BaseModel):
    """Aggregate metrics summary for events, webhooks, and DLQ."""

    total_events: int
    events_by_status: dict[str, int]
    total_webhook_deliveries: int
    deliveries_by_status: dict[str, int]
    active_sources_count: int
    pending_dead_letters_count: int
    events_received: int
    events_processed: int
    events_failed: int
    duplicate_events: int
    webhook_verification_failures: int
    webhook_delivery_success_rate: float
    webhook_delivery_failures: int
    dead_letter_count: int
    event_triggered_workflow_runs: int
    average_event_processing_latency_ms: float


class EventTraceResponse(BaseModel):
    """End-to-end trace correlation linking webhooks, domain events, workflow runs, deliveries, and DLQ."""

    correlation_id: str
    event: DomainEventResponse | None = None
    webhook_delivery: WebhookDeliveryResponse | None = None
    workflow_runs: list[dict[str, Any]] = Field(default_factory=list)
    outbound_deliveries: list[OutboundDeliveryResponse] = Field(default_factory=list)
    dead_letters: list[DeadLetterResponse] = Field(default_factory=list)
    audit_logs: list[dict[str, Any]] = Field(default_factory=list)
