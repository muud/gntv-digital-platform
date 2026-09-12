"""Pydantic schemas for Workflow Orchestration & Job Execution Platform."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.workflows.models import (
    WorkflowAuditAction,
    WorkflowRunStatus,
    WorkflowStatus,
    WorkflowStepStatus,
    WorkflowStepType,
    WorkflowTriggerType,
)


class WorkflowRetryPolicy(BaseModel):
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay_seconds: int = Field(default=5, ge=1, le=3600)
    exponential_backoff: bool = Field(default=True)
    retryable_errors: list[str] = Field(default_factory=lambda: ["timeout", "connection_error", "transient_error"])


class WorkflowStepDefinitionCreate(BaseModel):
    step_order: int = Field(..., ge=1)
    name: str = Field(..., min_length=2, max_length=160)
    step_type: WorkflowStepType
    config_json: dict[str, Any] | None = None
    is_required: bool = True
    timeout_seconds: int = Field(default=300, ge=1, le=86400)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay_seconds: int = Field(default=5, ge=1, le=3600)
    backoff_multiplier: int = Field(default=2, ge=1, le=10)


class WorkflowStepDefinitionUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=160)
    config_json: dict[str, Any] | None = None
    timeout_seconds: int | None = Field(None, ge=1, le=86400)
    max_retries: int | None = Field(None, ge=0, le=10)
    retry_delay_seconds: int | None = Field(None, ge=1, le=3600)
    backoff_multiplier: int | None = Field(None, ge=1, le=10)
    is_required: bool | None = None


class WorkflowStepDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    step_order: int
    name: str
    step_type: WorkflowStepType
    config_json: dict[str, Any] | None
    is_required: bool
    timeout_seconds: int
    max_retries: int
    retry_delay_seconds: int
    backoff_multiplier: int
    created_at: datetime
    updated_at: datetime


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    description: str | None = Field(None, max_length=500)
    workflow_type: str = Field(default="standard", max_length=80)
    timeout_seconds: int = Field(default=3600, ge=10, le=86400 * 7)
    retry_policy: WorkflowRetryPolicy | None = None
    steps: list[WorkflowStepDefinitionCreate] = Field(default_factory=list)

    @field_validator("steps")
    @classmethod
    def validate_steps_order(cls, steps: list[WorkflowStepDefinitionCreate]) -> list[WorkflowStepDefinitionCreate]:
        if not steps:
            return steps
        orders = [s.step_order for s in steps]
        if len(orders) != len(set(orders)):
            raise ValueError("step_order values must be unique within a workflow")
        return sorted(steps, key=lambda s: s.step_order)


class WorkflowUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=160)
    description: str | None = Field(None, max_length=500)
    workflow_type: str | None = Field(None, max_length=80)
    is_enabled: bool | None = None
    timeout_seconds: int | None = Field(None, ge=10, le=86400 * 7)
    retry_policy: WorkflowRetryPolicy | None = None


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    version: int
    workflow_type: str
    status: WorkflowStatus
    is_enabled: bool
    retry_policy_json: dict[str, Any] | None
    timeout_seconds: int
    created_by_user_id: int | None
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowStepDefinitionResponse] = Field(default_factory=list)


class WorkflowRunCreate(BaseModel):
    input_metadata: dict[str, Any] | None = None
    idempotency_key: str | None = Field(None, min_length=4, max_length=160)
    trigger_source: str | None = Field(None, max_length=120)


class WorkflowStepExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    step_definition_id: UUID | None
    step_order: int
    step_name: str
    step_type: WorkflowStepType
    status: WorkflowStepStatus
    idempotency_key: str
    retry_count: int
    max_retries: int
    retry_delay_seconds: int
    backoff_multiplier: int
    next_retry_at: datetime | None
    retryable_failure: bool
    is_required: bool
    timeout_seconds: int
    input_json: dict[str, Any] | None
    output_json: dict[str, Any] | None
    error_details_json: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    workflow_version: int
    status: WorkflowRunStatus
    trigger_type: WorkflowTriggerType
    trigger_source: str | None
    idempotency_key: str
    actor_user_id: int | None
    current_step_order: int
    retry_count: int
    input_metadata_json: dict[str, Any] | None
    output_metadata_json: dict[str, Any] | None
    error_summary: str | None
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WorkflowRunDetailResponse(WorkflowRunResponse):
    step_executions: list[WorkflowStepExecutionResponse] = Field(default_factory=list)
    workflow: WorkflowResponse | None = None


class WorkflowManualApprovalAction(BaseModel):
    notes: str | None = Field(None, max_length=1000)


class WorkflowTriggerCreate(BaseModel):
    trigger_type: WorkflowTriggerType
    name: str = Field(..., min_length=2, max_length=120)
    event_pattern: str | None = Field(None, max_length=120)
    schedule_cron: str | None = Field(None, max_length=60)
    schedule_timezone: str = Field(default="UTC", max_length=40)
    is_enabled: bool = True
    metadata_json: dict[str, Any] | None = None


class WorkflowTriggerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    trigger_type: WorkflowTriggerType
    name: str
    event_pattern: str | None
    schedule_cron: str | None
    schedule_timezone: str
    is_enabled: bool
    metadata_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class WorkflowScheduleCreate(BaseModel):
    schedule_type: str = Field(default="recurring", max_length=32)
    cron_expression: str | None = Field(None, max_length=80)
    next_run_at: datetime | None = None
    timezone: str = Field(default="UTC", max_length=40)
    is_enabled: bool = True

    @model_validator(mode="after")
    def validate_schedule(self) -> WorkflowScheduleCreate:
        if self.schedule_type not in {"one_time", "recurring"}:
            raise ValueError("schedule_type must be one_time or recurring")
        if self.schedule_type == "one_time" and self.next_run_at is None:
            raise ValueError("one_time schedules require next_run_at")
        if self.schedule_type == "recurring" and not self.cron_expression:
            raise ValueError("recurring schedules require cron_expression")
        return self


class WorkflowScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    schedule_type: str
    cron_expression: str | None
    next_run_at: datetime | None
    last_run_at: datetime | None
    timezone: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class WorkflowAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    run_id: UUID | None
    step_execution_id: UUID | None
    action: WorkflowAuditAction
    actor_user_id: int | None
    metadata_json: dict[str, Any] | None
    created_at: datetime


class WorkflowMetricsSummaryResponse(BaseModel):
    runs_queued: int
    runs_running: int
    runs_waiting: int
    runs_succeeded: int
    runs_failed: int
    runs_cancelled: int
    total_runs: int
    average_duration_seconds: float
    total_retries: int
    pending_approvals: int
