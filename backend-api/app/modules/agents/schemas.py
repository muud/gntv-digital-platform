"""Validated API and model-response contracts for AI agents."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.agents.models import AgentType, ApprovalMode


class ModelPolicyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    provider: str = Field(default="mock", max_length=40)
    model_name: str = Field(default="deterministic-v1", max_length=120)
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_output_tokens: int = Field(default=1024, ge=1, le=100_000)
    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    fallback_policy: dict[str, Any] | None = None
    enabled: bool = True
    metadata_json: dict[str, Any] | None = None


class ToolPolicyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    max_tool_calls: int = Field(default=10, ge=0, le=100)
    requires_approval_for: list[str] = Field(default_factory=list)
    allowed_workflow_ids: list[str] = Field(default_factory=list)
    allowed_job_types: list[str] = Field(default_factory=list)
    allowed_event_namespaces: list[str] = Field(default_factory=lambda: ["agent."])
    enabled: bool = True


class ApprovalPolicyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    approval_mode: ApprovalMode = ApprovalMode.NONE
    tools_requiring_approval: list[str] = Field(default_factory=list)
    side_effects_require_approval: bool = False
    workflow_execution_requires_approval: bool = False
    publishing_requires_approval: bool = False
    enabled: bool = True


class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)
    description: str | None = Field(default=None, max_length=500)
    agent_type: AgentType
    system_instructions: str = Field(min_length=1, max_length=20_000)
    model_policy_id: UUID
    tool_policy_id: UUID
    approval_policy_id: UUID
    default_queue_name: str = Field(default="agents", pattern="^agents$")
    default_timeout_seconds: int = Field(default=60, ge=1, le=3600)
    max_runtime_seconds: int = Field(default=300, ge=1, le=3600)
    max_tool_calls: int = Field(default=10, ge=0, le=100)
    max_iterations: int = Field(default=10, ge=1, le=100)
    max_input_tokens: int = Field(default=4096, ge=1)
    max_output_tokens: int = Field(default=2048, ge=1)
    max_total_tokens: int = Field(default=6144, ge=1)
    max_cost_units: int = Field(default=100, ge=1)
    concurrency_limit: int = Field(default=1, ge=1, le=100)
    metadata_json: dict[str, Any] | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    metadata_json: dict[str, Any] | None = None
    model_policy_id: UUID | None = None
    tool_policy_id: UUID | None = None
    approval_policy_id: UUID | None = None


class InstructionCreate(BaseModel):
    system_instructions: str = Field(min_length=1, max_length=20_000)
    change_summary: str | None = Field(default=None, max_length=500)


class AgentRunCreate(BaseModel):
    input_json: dict[str, Any] = Field(default_factory=dict)
    context_json: dict[str, Any] = Field(default_factory=dict)
    trigger_type: str = Field(default="manual", max_length=60)
    trigger_source: str | None = Field(default=None, max_length=120)
    correlation_id: str | None = Field(default=None, max_length=160)
    causation_id: str | None = Field(default=None, max_length=160)
    idempotency_key: str | None = Field(default=None, max_length=160)


class ApprovalDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class ORMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PolicyResponse(ORMResponse):
    id: UUID
    name: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ModelPolicyResponse(PolicyResponse):
    provider: str
    model_name: str
    temperature: float
    max_output_tokens: int
    timeout_seconds: int
    fallback_policy: dict[str, Any] | None
    metadata_json: dict[str, Any] | None


class ToolPolicyResponse(PolicyResponse):
    description: str | None
    allowed_tools: list[str]
    denied_tools: list[str]
    max_tool_calls: int
    requires_approval_for: list[str]
    allowed_workflow_ids: list[str]
    allowed_job_types: list[str]
    allowed_event_namespaces: list[str]


class ApprovalPolicyResponse(PolicyResponse):
    approval_mode: str
    tools_requiring_approval: list[str]
    side_effects_require_approval: bool
    workflow_execution_requires_approval: bool
    publishing_requires_approval: bool


class AgentResponse(ORMResponse):
    id: UUID
    name: str
    slug: str
    description: str | None
    status: str
    agent_type: str
    instruction_version: int
    model_policy_id: UUID
    tool_policy_id: UUID
    approval_policy_id: UUID
    default_queue_name: str
    max_runtime_seconds: int
    max_tool_calls: int
    max_iterations: int
    max_total_tokens: int
    max_cost_units: int
    concurrency_limit: int
    metadata_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class ToolCallResponse(ORMResponse):
    id: UUID
    agent_run_id: UUID
    tool_name: str
    status: str
    sanitized_arguments_json: dict[str, Any] | None
    sanitized_result_json: dict[str, Any] | None
    safe_error_summary: str | None
    requires_approval: bool
    approved_by_user_id: int | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ApprovalResponse(ORMResponse):
    id: UUID
    agent_run_id: UUID
    tool_call_id: UUID | None
    approval_type: str
    status: str
    requested_by: str
    requested_at: datetime
    decided_by_user_id: int | None
    decided_at: datetime | None
    decision_reason: str | None
    expires_at: datetime | None


class AgentRunResponse(ORMResponse):
    id: UUID
    agent_id: UUID
    instruction_version: int
    status: str
    trigger_type: str
    trigger_source: str | None
    input_json: dict[str, Any] | None
    sanitized_context_json: dict[str, Any] | None
    output_json: dict[str, Any] | None
    safe_error_summary: str | None
    correlation_id: str
    causation_id: str | None
    idempotency_key: str
    job_id: UUID | None
    workflow_run_id: UUID | None
    current_iteration: int
    tool_call_count: int
    total_tokens: int
    cost_units: int
    runtime_seconds: float
    cancellation_requested: bool
    created_at: datetime
    updated_at: datetime
    tool_calls: list[ToolCallResponse] = Field(default_factory=list)
    approvals: list[ApprovalResponse] = Field(default_factory=list)
