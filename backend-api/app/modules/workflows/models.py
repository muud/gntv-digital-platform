"""SQLAlchemy models for Workflow Orchestration & Job Execution Platform."""

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
    return Enum(enum, name=name, values_callable=lambda values: [item.value for item in values])


class WorkflowStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class WorkflowRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIALLY_SUCCEEDED = "partially_succeeded"


class WorkflowStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class WorkflowStepType(StrEnum):
    HTTP_INTERNAL = "HTTP_INTERNAL"
    CONTENT_VALIDATE = "CONTENT_VALIDATE"
    CONTENT_PUBLISH_REQUEST = "CONTENT_PUBLISH_REQUEST"
    DISTRIBUTION_REQUEST = "DISTRIBUTION_REQUEST"
    REPORT_GENERATION = "REPORT_GENERATION"
    NOTIFICATION_EVENT = "NOTIFICATION_EVENT"
    MANUAL_APPROVAL = "MANUAL_APPROVAL"
    DELAY = "DELAY"
    CONDITIONAL = "CONDITIONAL"


class WorkflowTriggerType(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    INTERNAL_EVENT = "internal_event"


class WorkflowAuditAction(StrEnum):
    WORKFLOW_CREATED = "workflow_created"
    WORKFLOW_UPDATED = "workflow_updated"
    WORKFLOW_ACTIVATED = "workflow_activated"
    WORKFLOW_PAUSED = "workflow_paused"
    RUN_QUEUED = "run_queued"
    RUN_STARTED = "run_started"
    STEP_STARTED = "step_started"
    STEP_SUCCEEDED = "step_succeeded"
    STEP_FAILED = "step_failed"
    APPROVAL_REQUESTED = "approval_requested"
    STEP_APPROVED = "step_approved"
    STEP_REJECTED = "step_rejected"
    RUN_SUCCEEDED = "run_succeeded"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"


class Workflow(Base):
    """Workflow definition model."""

    __tablename__ = "workflows"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    workflow_type: Mapped[str] = mapped_column(String(80), nullable=False, default="standard")
    status: Mapped[WorkflowStatus] = mapped_column(
        enum_type(WorkflowStatus, "workflow_status_enum"),
        nullable=False,
        default=WorkflowStatus.DRAFT,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    retry_policy_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    steps: Mapped[list[WorkflowStepDefinition]] = relationship(
        "WorkflowStepDefinition",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowStepDefinition.step_order",
    )
    runs: Mapped[list[WorkflowRun]] = relationship(
        "WorkflowRun",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    triggers: Mapped[list[WorkflowTrigger]] = relationship(
        "WorkflowTrigger",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    schedules: Mapped[list[WorkflowSchedule]] = relationship(
        "WorkflowSchedule",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    audit_logs: Mapped[list[WorkflowAuditLog]] = relationship(
        "WorkflowAuditLog",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_workflow_name_version"),
        Index("ix_workflows_status", "status"),
        Index("ix_workflows_name_version", "name", "version"),
    )


class WorkflowStepDefinition(Base):
    """Ordered step definition belonging to a workflow."""

    __tablename__ = "workflow_step_definitions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    step_type: Mapped[WorkflowStepType] = mapped_column(
        enum_type(WorkflowStepType, "workflow_step_type_enum"),
        nullable=False,
    )
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    backoff_multiplier: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="steps")

    __table_args__ = (
        UniqueConstraint("workflow_id", "step_order", name="uq_workflow_step_order"),
        Index("ix_workflow_steps_workflow", "workflow_id", "step_order"),
    )


class WorkflowRun(Base):
    """Workflow execution instance."""

    __tablename__ = "workflow_runs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[WorkflowRunStatus] = mapped_column(
        enum_type(WorkflowRunStatus, "workflow_run_status_enum"),
        nullable=False,
        default=WorkflowRunStatus.QUEUED,
    )
    trigger_type: Mapped[WorkflowTriggerType] = mapped_column(
        enum_type(WorkflowTriggerType, "workflow_trigger_type_enum"),
        nullable=False,
        default=WorkflowTriggerType.MANUAL,
    )
    trigger_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    current_step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="runs")
    step_executions: Mapped[list[WorkflowStepExecution]] = relationship(
        "WorkflowStepExecution",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="WorkflowStepExecution.step_order",
    )
    audit_logs: Mapped[list[WorkflowAuditLog]] = relationship(
        "WorkflowAuditLog",
        back_populates="run",
    )

    __table_args__ = (
        UniqueConstraint("workflow_id", "idempotency_key", name="uq_workflow_run_idempotency"),
        Index("ix_workflow_runs_workflow_status", "workflow_id", "status"),
        Index("ix_workflow_runs_status_created", "status", "created_at"),
    )


class WorkflowStepExecution(Base):
    """Step execution instance within a workflow run."""

    __tablename__ = "workflow_step_executions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False)
    step_definition_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("workflow_step_definitions.id", ondelete="SET NULL"), nullable=True
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    step_name: Mapped[str] = mapped_column(String(160), nullable=False)
    step_type: Mapped[WorkflowStepType] = mapped_column(
        enum_type(WorkflowStepType, "workflow_step_type_enum"),
        nullable=False,
    )
    status: Mapped[WorkflowStepStatus] = mapped_column(
        enum_type(WorkflowStepStatus, "workflow_step_status_enum"),
        nullable=False,
        default=WorkflowStepStatus.PENDING,
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    backoff_multiplier: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retryable_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    input_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    run: Mapped[WorkflowRun] = relationship("WorkflowRun", back_populates="step_executions")

    __table_args__ = (
        UniqueConstraint("run_id", "step_order", name="uq_run_step_order"),
        UniqueConstraint("run_id", "idempotency_key", name="uq_run_step_idempotency"),
        Index("ix_workflow_step_executions_run", "run_id", "status"),
    )


class WorkflowTrigger(Base):
    """Trigger definition for workflows."""

    __tablename__ = "workflow_triggers"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    trigger_type: Mapped[WorkflowTriggerType] = mapped_column(
        enum_type(WorkflowTriggerType, "workflow_trigger_type_enum"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    event_pattern: Mapped[str | None] = mapped_column(String(120), nullable=True)
    schedule_cron: Mapped[str | None] = mapped_column(String(60), nullable=True)
    schedule_timezone: Mapped[str] = mapped_column(String(40), nullable=False, default="UTC")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="triggers")

    __table_args__ = (
        Index("ix_workflow_triggers_workflow", "workflow_id", "is_enabled"),
    )


class WorkflowSchedule(Base):
    """Schedule entity for recurring or one-off scheduled runs."""

    __tablename__ = "workflow_schedules"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(32), nullable=False, default="recurring")
    cron_expression: Mapped[str | None] = mapped_column(String(80), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(40), nullable=False, default="UTC")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="schedules")

    __table_args__ = (
        Index("ix_workflow_schedules_next_run", "is_enabled", "next_run_at"),
    )


class WorkflowAuditLog(Base):
    """Append-only audit log for workflow actions and execution lifecycle events."""

    __tablename__ = "workflow_audit_logs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True)
    step_execution_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("workflow_step_executions.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[WorkflowAuditAction] = mapped_column(
        enum_type(WorkflowAuditAction, "workflow_audit_action_enum"),
        nullable=False,
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    workflow: Mapped[Workflow] = relationship("Workflow", back_populates="audit_logs")
    run: Mapped[WorkflowRun | None] = relationship("WorkflowRun", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_workflow_audit_logs_workflow_created", "workflow_id", "created_at"),
        Index("ix_workflow_audit_logs_run_created", "run_id", "created_at"),
    )
