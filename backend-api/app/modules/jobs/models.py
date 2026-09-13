"""Data models and enums for durable background jobs, workers, schedules and dead letters."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class EnumType(TypeDecorator[str]):
    """Platform-independent Enum type decorator."""

    impl = String
    cache_ok = True

    def __init__(self, enum_class: type[StrEnum], name: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.enum_class = enum_class
        self.name = name

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, self.enum_class):
            return str(value.value)
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return self.enum_class(value)


def enum_type(enum_class: type[StrEnum], name: str) -> EnumType:
    return EnumType(enum_class, name)


class JobStatus(StrEnum):
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    CLAIMED = "claimed"
    RUNNING = "running"
    WAITING_RETRY = "waiting_retry"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEAD_LETTERED = "dead_lettered"


class JobAttemptStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class WorkerStatus(StrEnum):
    ONLINE = "online"
    DRAINING = "draining"
    OFFLINE = "offline"
    UNHEALTHY = "unhealthy"
    DEAD = "dead"


class ScheduleRecurrenceType(StrEnum):
    ONE_TIME = "one_time"
    INTERVAL = "interval"
    CRON = "cron"


class ScheduleMisfirePolicy(StrEnum):
    SKIP = "skip"
    RUN_ONCE = "run_once"
    CATCH_UP_LIMITED = "catch_up_limited"


class JobDeadLetterStatus(StrEnum):
    OPEN = "open"
    RETRIED = "retried"
    REQUEUED = "requeued"
    DISMISSED = "dismissed"


class JobAuditAction(StrEnum):
    JOB_ENQUEUED = "job_enqueued"
    JOB_CLAIMED = "job_claimed"
    JOB_STARTED = "job_started"
    JOB_SUCCEEDED = "job_succeeded"
    JOB_FAILED = "job_failed"
    JOB_RETRY_SCHEDULED = "job_retry_scheduled"
    JOB_CANCELLED = "job_cancelled"
    JOB_DEAD_LETTERED = "job_dead_lettered"
    JOB_RETRIED = "job_retried"
    WORKER_STARTED = "worker_started"
    WORKER_HEARTBEAT = "worker_heartbeat"
    WORKER_DRAINING = "worker_draining"
    WORKER_OFFLINE = "worker_offline"
    SCHEDULE_CREATED = "schedule_created"
    SCHEDULE_UPDATED = "schedule_updated"
    SCHEDULE_TRIGGERED = "schedule_triggered"
    SCHEDULE_MISFIRED = "schedule_misfired"
    SCHEDULE_ENABLED = "schedule_enabled"
    SCHEDULE_DISABLED = "schedule_disabled"
    DLQ_REQUEUED = "dlq_requeued"
    DLQ_DISMISSED = "dlq_dismissed"
    JOB_QUEUED = "job_queued"


class DurableJob(Base):
    """Persisted background job."""

    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    queue_name: Mapped[str] = mapped_column(
        String(80), nullable=False, default="default"
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[JobStatus] = mapped_column(
        enum_type(JobStatus, "job_status_enum"),
        nullable=False,
        default=JobStatus.QUEUED,
    )
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(160), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_delay: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_details_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    schedule_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_schedules.id", ondelete="SET NULL"), nullable=True
    )

    attempts: Mapped[list[JobAttempt]] = relationship(
        "JobAttempt",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobAttempt.attempt_number",
    )
    dead_letter: Mapped[JobDeadLetter | None] = relationship(
        "JobDeadLetter",
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
    )
    audit_logs: Mapped[list[JobAuditLog]] = relationship(
        "JobAuditLog", back_populates="job"
    )

    __table_args__ = (
        UniqueConstraint("job_type", "idempotency_key", name="uq_jobs_type_idempotency"),
        Index("ix_jobs_job_type", "job_type"),
        Index("ix_jobs_queue_name", "queue_name"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_priority", "priority"),
        Index("ix_jobs_correlation_id", "correlation_id"),
        Index("ix_jobs_available_at", "available_at"),
        Index("ix_jobs_worker_id", "worker_id"),
        Index("ix_jobs_lease_expires_at", "lease_expires_at"),
        Index(
            "ix_jobs_claim_poll",
            "queue_name",
            "status",
            "priority",
            "available_at",
        ),
        Index("ix_jobs_idempotency", "job_type", "idempotency_key"),
    )


class JobAttempt(Base):
    """Immutable execution attempt record."""

    __tablename__ = "job_attempts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str] = mapped_column(String(120), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[JobAttemptStatus] = mapped_column(
        enum_type(JobAttemptStatus, "job_attempt_status_enum"),
        nullable=False,
        default=JobAttemptStatus.RUNNING,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    job: Mapped[DurableJob] = relationship("DurableJob", back_populates="attempts")

    __table_args__ = (
        Index("ix_job_attempts_job_id", "job_id"),
        Index("ix_job_attempts_worker_id", "worker_id"),
    )


class WorkerRecord(Base):
    """Worker node registration and heartbeat record."""

    __tablename__ = "workers"

    worker_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    hostname: Mapped[str | None] = mapped_column(String(160), nullable=True)
    queues_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[WorkerStatus] = mapped_column(
        enum_type(WorkerStatus, "worker_status_enum"),
        nullable=False,
        default=WorkerStatus.ONLINE,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    active_job_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_job_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    failed_job_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[str] = mapped_column(
        String(60), nullable=False, default="1.0.0"
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )

    __table_args__ = (
        Index("ix_workers_status", "status"),
        Index("ix_workers_last_heartbeat_at", "last_heartbeat_at"),
    )


class JobSchedule(Base):
    """Persisted recurring job schedule."""

    __tablename__ = "job_schedules"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    queue_name: Mapped[str] = mapped_column(
        String(80), nullable=False, default="default"
    )
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    recurrence_type: Mapped[ScheduleRecurrenceType] = mapped_column(
        enum_type(ScheduleRecurrenceType, "schedule_recurrence_type_enum"),
        nullable=False,
    )
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cron_expression: Mapped[str | None] = mapped_column(String(80), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    misfire_policy: Mapped[ScheduleMisfirePolicy] = mapped_column(
        enum_type(ScheduleMisfirePolicy, "schedule_misfire_policy_enum"),
        nullable=False,
        default=ScheduleMisfirePolicy.RUN_ONCE,
    )
    max_concurrent_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    catch_up_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    active_run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claimed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    audit_logs: Mapped[list[JobAuditLog]] = relationship(
        "JobAuditLog", back_populates="schedule"
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_job_schedules_name"),
        Index("ix_job_schedules_is_enabled", "is_enabled"),
        Index("ix_job_schedules_next_run_at", "next_run_at"),
        Index("ix_job_schedules_job_type", "job_type"),
    )


class ScheduleExecution(Base):
    """Immutable record preventing duplicate enqueue for a schedule occurrence."""

    __tablename__ = "job_schedule_executions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    schedule_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_schedules.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="enqueued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        UniqueConstraint("schedule_id", "scheduled_for", name="uq_job_schedule_execution_occurrence"),
        Index("ix_job_schedule_executions_schedule", "schedule_id"),
    )

class JobDeadLetter(Base):
    """Terminal dead-letter queue entry."""

    __tablename__ = "job_dead_letters"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[JobDeadLetterStatus] = mapped_column(
        enum_type(JobDeadLetterStatus, "job_dead_letter_status_enum"),
        nullable=False,
        default=JobDeadLetterStatus.OPEN,
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    error_details_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    job: Mapped[DurableJob] = relationship("DurableJob", back_populates="dead_letter")

    __table_args__ = (
        Index("ix_job_dead_letters_job_id", "job_id"),
        Index("ix_job_dead_letters_status", "status"),
    )


class JobAuditLog(Base):
    """Append-only audit trail for background job and scheduler operations."""

    __tablename__ = "job_audit_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    action: Mapped[JobAuditAction] = mapped_column(
        enum_type(JobAuditAction, "job_audit_action_enum"), nullable=False
    )
    job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    schedule_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_schedules.id", ondelete="SET NULL"), nullable=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    job: Mapped[DurableJob | None] = relationship(
        "DurableJob", back_populates="audit_logs"
    )
    schedule: Mapped[JobSchedule | None] = relationship(
        "JobSchedule", back_populates="audit_logs"
    )

    __table_args__ = (
        Index("ix_job_audit_logs_action", "action"),
        Index("ix_job_audit_logs_job_id", "job_id"),
        Index("ix_job_audit_logs_schedule_id", "schedule_id"),
        Index("ix_job_audit_logs_created_at", "created_at"),
    )
