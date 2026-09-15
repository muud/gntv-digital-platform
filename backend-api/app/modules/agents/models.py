"""Persisted models for the Sprint 8.4 AI Agent Control Plane."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.jobs.models import enum_type


def utc_now() -> datetime:
    return datetime.now(UTC)


class AgentStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class AgentType(StrEnum):
    RESEARCH_AGENT = "RESEARCH_AGENT"
    SCRIPT_WRITER_AGENT = "SCRIPT_WRITER_AGENT"
    CONTENT_SUMMARIZER_AGENT = "CONTENT_SUMMARIZER_AGENT"
    CONTENT_CLASSIFIER_AGENT = "CONTENT_CLASSIFIER_AGENT"
    EDITORIAL_ASSISTANT_AGENT = "EDITORIAL_ASSISTANT_AGENT"
    PRODUCTION_PLANNER_AGENT = "PRODUCTION_PLANNER_AGENT"
    DISTRIBUTION_PLANNER_AGENT = "DISTRIBUTION_PLANNER_AGENT"
    MONITORING_AGENT = "MONITORING_AGENT"


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    WAITING_FOR_TOOL = "waiting_for_tool"
    WAITING_FOR_HUMAN = "waiting_for_human"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    PARTIALLY_SUCCEEDED = "partially_succeeded"


class ToolCallStatus(StrEnum):
    REQUESTED = "requested"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
    CANCELLED = "cancelled"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalMode(StrEnum):
    NONE = "none"
    BEFORE_RUN = "before_run"
    SELECTED_TOOLS = "selected_tools"
    EXTERNAL_SIDE_EFFECTS = "external_side_effects"
    BEFORE_PUBLISHING = "before_publishing"
    BEFORE_WORKFLOW = "before_workflow"


class AgentAuditAction(StrEnum):
    AGENT_CREATED = "agent_created"
    AGENT_UPDATED = "agent_updated"
    AGENT_ACTIVATED = "agent_activated"
    AGENT_PAUSED = "agent_paused"
    AGENT_ARCHIVED = "agent_archived"
    AGENT_RUN_CREATED = "agent_run_created"
    AGENT_RUN_QUEUED = "agent_run_queued"
    AGENT_RUN_STARTED = "agent_run_started"
    AGENT_RUN_COMPLETED = "agent_run_completed"
    AGENT_RUN_FAILED = "agent_run_failed"
    AGENT_RUN_CANCELLED = "agent_run_cancelled"
    AGENT_RUN_BLOCKED = "agent_run_blocked"
    TOOL_REQUESTED = "tool_requested"
    TOOL_DENIED = "tool_denied"
    TOOL_APPROVED = "tool_approved"
    TOOL_EXECUTED = "tool_executed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_APPROVED = "approval_approved"
    APPROVAL_REJECTED = "approval_rejected"
    MODEL_POLICY_CHANGED = "model_policy_changed"
    TOOL_POLICY_CHANGED = "tool_policy_changed"
    APPROVAL_POLICY_CHANGED = "approval_policy_changed"


class ModelPolicy(Base):
    __tablename__ = "agent_model_policies"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="mock")
    model_name: Mapped[str] = mapped_column(
        String(120), nullable=False, default="deterministic-v1"
    )
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1024
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    fallback_policy: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ToolPolicy(Base):
    __tablename__ = "agent_tool_policies"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    allowed_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    denied_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    max_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    requires_approval_for: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    allowed_workflow_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    allowed_job_types: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    allowed_event_namespaces: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=lambda: ["agent."]
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class ApprovalPolicy(Base):
    __tablename__ = "agent_approval_policies"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    approval_mode: Mapped[ApprovalMode] = mapped_column(
        enum_type(ApprovalMode, "agent_approval_mode_enum"),
        nullable=False,
        default=ApprovalMode.NONE,
    )
    tools_requiring_approval: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    side_effects_require_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    workflow_execution_requires_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    publishing_requires_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class AgentDefinition(Base):
    __tablename__ = "agent_definitions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[AgentStatus] = mapped_column(
        enum_type(AgentStatus, "agent_status_enum"),
        nullable=False,
        default=AgentStatus.DRAFT,
    )
    agent_type: Mapped[AgentType] = mapped_column(
        enum_type(AgentType, "agent_type_enum"), nullable=False
    )
    system_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    instruction_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    model_policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_model_policies.id"), nullable=False
    )
    tool_policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_tool_policies.id"), nullable=False
    )
    approval_policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_approval_policies.id"), nullable=False
    )
    default_queue_name: Mapped[str] = mapped_column(
        String(80), nullable=False, default="agents"
    )
    default_timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60
    )
    max_runtime_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=300
    )
    max_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4096)
    max_output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2048
    )
    max_total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=6144)
    max_cost_units: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    concurrency_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    model_policy: Mapped[ModelPolicy] = relationship()
    tool_policy: Mapped[ToolPolicy] = relationship()
    approval_policy: Mapped[ApprovalPolicy] = relationship()
    instruction_versions: Mapped[list[AgentInstructionVersion]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )
    runs: Mapped[list[AgentRun]] = relationship(back_populates="agent")

    __table_args__ = (Index("ix_agent_definitions_status", "status"),)


class AgentInstructionVersion(Base):
    __tablename__ = "agent_instruction_versions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_definitions.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    system_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    agent: Mapped[AgentDefinition] = relationship(back_populates="instruction_versions")
    __table_args__ = (
        UniqueConstraint("agent_id", "version", name="uq_agent_instruction_version"),
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_definitions.id"), nullable=False
    )
    instruction_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(
        enum_type(AgentRunStatus, "agent_run_status_enum"),
        nullable=False,
        default=AgentRunStatus.QUEUED,
    )
    trigger_type: Mapped[str] = mapped_column(
        String(60), nullable=False, default="manual"
    )
    trigger_source: Mapped[str | None] = mapped_column(String(120))
    input_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sanitized_context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    safe_error_summary: Mapped[str | None] = mapped_column(String(1000))
    correlation_id: Mapped[str] = mapped_column(String(160), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(160))
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL")
    )
    workflow_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    runtime_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cancellation_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    agent: Mapped[AgentDefinition] = relationship(back_populates="runs")
    tool_calls: Mapped[list[AgentToolCall]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    approvals: Mapped[list[AgentApprovalRequest]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    __table_args__ = (
        UniqueConstraint(
            "agent_id", "idempotency_key", name="uq_agent_run_idempotency"
        ),
        Index("ix_agent_runs_status", "status"),
        Index("ix_agent_runs_correlation", "correlation_id"),
    )


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ToolCallStatus] = mapped_column(
        enum_type(ToolCallStatus, "agent_tool_call_status_enum"),
        nullable=False,
        default=ToolCallStatus.REQUESTED,
    )
    sanitized_arguments_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    sanitized_result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    safe_error_summary: Mapped[str | None] = mapped_column(String(1000))
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    run: Mapped[AgentRun] = relationship(back_populates="tool_calls")
    approval: Mapped[AgentApprovalRequest | None] = relationship(
        back_populates="tool_call", uselist=False
    )


class AgentApprovalRequest(Base):
    __tablename__ = "agent_approval_requests"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    tool_call_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_tool_calls.id", ondelete="CASCADE"), unique=True
    )
    approval_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        enum_type(ApprovalStatus, "agent_approval_status_enum"),
        nullable=False,
        default=ApprovalStatus.PENDING,
    )
    requested_by: Mapped[str] = mapped_column(
        String(120), nullable=False, default="agent"
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    decided_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(String(1000))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run: Mapped[AgentRun] = relationship(back_populates="approvals")
    tool_call: Mapped[AgentToolCall | None] = relationship(back_populates="approval")
    __table_args__ = (Index("ix_agent_approvals_status", "status"),)


class AgentAuditLog(Base):
    __tablename__ = "agent_audit_logs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    action: Mapped[AgentAuditAction] = mapped_column(
        enum_type(AgentAuditAction, "agent_audit_action_enum"), nullable=False
    )
    agent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_definitions.id", ondelete="SET NULL")
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    tool_call_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_tool_calls.id", ondelete="SET NULL")
    )
    approval_request_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_approval_requests.id", ondelete="SET NULL")
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    correlation_id: Mapped[str | None] = mapped_column(String(160))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    __table_args__ = (Index("ix_agent_audit_created", "created_at"),)
