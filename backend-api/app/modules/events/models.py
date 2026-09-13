"""SQLAlchemy models for Event Bus, Secure Webhooks & Automation Triggers."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


def enum_type(enum: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum, name=name, values_callable=lambda values: [item.value for item in values]
    )


class EventProcessingStatus(StrEnum):
    RECEIVED = "received"
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    PARTIALLY_PROCESSED = "partially_processed"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"
    IGNORED = "ignored"


class WebhookDeliveryStatus(StrEnum):
    RECEIVED = "received"
    VERIFIED = "verified"
    REJECTED = "rejected"
    PROCESSED = "processed"
    DUPLICATE = "duplicate"


class OutboundDeliveryStatus(StrEnum):
    PENDING = "pending"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRY_SCHEDULED = "retry_scheduled"
    DEAD_LETTERED = "dead_lettered"


class DeadLetterStatus(StrEnum):
    PENDING = "pending"
    RETRIED = "retried"
    DISMISSED = "dismissed"


class EventAuditAction(StrEnum):
    EVENT_RECEIVED = "event_received"
    EVENT_DISPATCHED = "event_dispatched"
    EVENT_PROCESSED = "event_processed"
    EVENT_FAILED = "event_failed"
    EVENT_DEAD_LETTERED = "event_dead_lettered"
    WEBHOOK_RECEIVED = "webhook_received"
    WEBHOOK_VERIFIED = "webhook_verified"
    WEBHOOK_REJECTED = "webhook_rejected"
    WEBHOOK_MAPPED = "webhook_mapped"
    WEBHOOK_DUPLICATE = "webhook_duplicate"
    OUTBOUND_DELIVERY_STARTED = "outbound_delivery_started"
    OUTBOUND_DELIVERY_SUCCEEDED = "outbound_delivery_succeeded"
    OUTBOUND_DELIVERY_FAILED = "outbound_delivery_failed"
    OUTBOUND_DELIVERY_DEAD_LETTERED = "outbound_delivery_dead_lettered"
    DEAD_LETTER_RETRIED = "dead_letter_retried"
    DEAD_LETTER_DISMISSED = "dead_letter_dismissed"
    WORKFLOW_TRIGGERED_BY_EVENT = "workflow_triggered_by_event"


class DomainEvent(Base):
    """Persisted domain event."""

    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    aggregate_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    aggregate_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[EventProcessingStatus] = mapped_column(
        enum_type(EventProcessingStatus, "event_processing_status_enum"),
        nullable=False,
        default=EventProcessingStatus.RECEIVED,
    )
    error_details_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    webhook_deliveries: Mapped[list[WebhookDelivery]] = relationship(
        "WebhookDelivery", back_populates="linked_event"
    )
    outbound_deliveries: Mapped[list[OutboundWebhookDelivery]] = relationship(
        "OutboundWebhookDelivery", back_populates="event", cascade="all, delete-orphan"
    )
    dead_letters: Mapped[list[EventDeadLetter]] = relationship(
        "EventDeadLetter", back_populates="event", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[EventAuditLog]] = relationship(
        "EventAuditLog", back_populates="event"
    )

    __table_args__ = (
        UniqueConstraint(
            "event_type", "idempotency_key", name="uq_event_type_idempotency"
        ),
        Index("ix_events_type_status", "event_type", "status"),
        Index("ix_events_correlation", "correlation_id"),
        Index("ix_events_created", "created_at"),
    )


class WebhookSource(Base):
    """Inbound webhook source provider configuration."""

    __tablename__ = "webhook_sources"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_type: Mapped[str] = mapped_column(
        String(60), nullable=False, default="hmac_sha256"
    )
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    header_name: Mapped[str] = mapped_column(
        String(80), nullable=False, default="X-Hub-Signature-256"
    )
    timestamp_header: Mapped[str | None] = mapped_column(
        String(80), nullable=True, default="X-GNTV-Timestamp"
    )
    timestamp_tolerance_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=300
    )
    payload_size_limit_bytes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1_048_576
    )
    event_type_mapping_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    deliveries: Mapped[list[WebhookDelivery]] = relationship(
        "WebhookDelivery", back_populates="source", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[EventAuditLog]] = relationship(
        "EventAuditLog", back_populates="webhook_source"
    )

    __table_args__ = (
        UniqueConstraint("source_key", name="uq_webhook_source_key"),
        Index("ix_webhook_sources_enabled", "is_enabled"),
    )


class WebhookDelivery(Base):
    """Inbound webhook delivery record."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("webhook_sources.id", ondelete="CASCADE"), nullable=False
    )
    external_event_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    delivery_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    signature_valid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    mapped_event_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        enum_type(WebhookDeliveryStatus, "webhook_delivery_status_enum"),
        nullable=False,
        default=WebhookDeliveryStatus.RECEIVED,
    )
    linked_event_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )
    safe_payload_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    source: Mapped[WebhookSource] = relationship(
        "WebhookSource", back_populates="deliveries"
    )
    linked_event: Mapped[DomainEvent | None] = relationship(
        "DomainEvent", back_populates="webhook_deliveries"
    )
    audit_logs: Mapped[list[EventAuditLog]] = relationship(
        "EventAuditLog", back_populates="webhook_delivery"
    )

    __table_args__ = (
        UniqueConstraint(
            "source_id", "delivery_fingerprint", name="uq_webhook_delivery_fingerprint"
        ),
        UniqueConstraint(
            "source_id", "external_event_id", name="uq_webhook_delivery_external_event"
        ),
        Index("ix_webhook_deliveries_source_status", "source_id", "status"),
        Index("ix_webhook_deliveries_received", "received_at"),
    )


class OutboundWebhookSubscription(Base):
    """Subscription configuration for outbound webhooks."""

    __tablename__ = "outbound_webhook_subscriptions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(500), nullable=False)
    event_patterns_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_salt: Mapped[str] = mapped_column(String(64), nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    deliveries: Mapped[list[OutboundWebhookDelivery]] = relationship(
        "OutboundWebhookDelivery",
        back_populates="subscription",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("ix_outbound_webhook_subs_enabled", "is_enabled"),)


class OutboundWebhookDelivery(Base):
    """Attempted outbound webhook delivery record."""

    __tablename__ = "outbound_webhook_deliveries"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    subscription_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("outbound_webhook_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[OutboundDeliveryStatus] = mapped_column(
        enum_type(OutboundDeliveryStatus, "outbound_delivery_status_enum"),
        nullable=False,
        default=OutboundDeliveryStatus.PENDING,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body_truncated: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    subscription: Mapped[OutboundWebhookSubscription] = relationship(
        "OutboundWebhookSubscription", back_populates="deliveries"
    )
    event: Mapped[DomainEvent] = relationship(
        "DomainEvent", back_populates="outbound_deliveries"
    )
    dead_letters: Mapped[list[EventDeadLetter]] = relationship(
        "EventDeadLetter",
        back_populates="outbound_delivery",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_outbound_deliveries_sub_status", "subscription_id", "status"),
        Index("ix_outbound_deliveries_event", "event_id"),
    )


class EventDeadLetter(Base):
    """Dead letter queue record for failed events or outbound deliveries."""

    __tablename__ = "event_dead_letters"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    event_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("events.id", ondelete="CASCADE"), nullable=True
    )
    outbound_delivery_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("outbound_webhook_deliveries.id", ondelete="CASCADE"),
        nullable=True,
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[DeadLetterStatus] = mapped_column(
        enum_type(DeadLetterStatus, "dead_letter_status_enum"),
        nullable=False,
        default=DeadLetterStatus.PENDING,
    )
    dismissed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    event: Mapped[DomainEvent | None] = relationship(
        "DomainEvent", back_populates="dead_letters"
    )
    outbound_delivery: Mapped[OutboundWebhookDelivery | None] = relationship(
        "OutboundWebhookDelivery", back_populates="dead_letters"
    )

    __table_args__ = (Index("ix_event_dead_letters_status", "status"),)


class EventAuditLog(Base):
    """Append-only audit log for event operations and webhook lifecycle."""

    __tablename__ = "event_audit_logs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    action: Mapped[EventAuditAction] = mapped_column(
        enum_type(EventAuditAction, "event_audit_action_enum"),
        nullable=False,
    )
    event_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("events.id", ondelete="SET NULL"), nullable=True
    )
    webhook_source_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("webhook_sources.id", ondelete="SET NULL"), nullable=True
    )
    webhook_delivery_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("webhook_deliveries.id", ondelete="SET NULL"), nullable=True
    )
    workflow_run_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    event: Mapped[DomainEvent | None] = relationship(
        "DomainEvent", back_populates="audit_logs"
    )
    webhook_source: Mapped[WebhookSource | None] = relationship(
        "WebhookSource", back_populates="audit_logs"
    )
    webhook_delivery: Mapped[WebhookDelivery | None] = relationship(
        "WebhookDelivery", back_populates="audit_logs"
    )

    __table_args__ = (
        Index("ix_event_audit_logs_event", "event_id"),
        Index("ix_event_audit_logs_action_created", "action", "created_at"),
    )
