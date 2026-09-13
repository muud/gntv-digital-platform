"""Validated public schemas for durable jobs, workers, and schedules."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.jobs.models import ScheduleMisfirePolicy, ScheduleRecurrenceType


class EnqueueJobRequest(BaseModel):
    job_type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    queue_name: str = Field(default="default", min_length=1, max_length=80)
    priority: int = Field(default=0, ge=-100, le=100)
    idempotency_key: str | None = Field(default=None, max_length=160)
    correlation_id: str | None = Field(default=None, max_length=160)
    causation_id: str | None = Field(default=None, max_length=160)
    scheduled_for: datetime | None = None
    delay_seconds: int = Field(default=0, ge=0, le=31_536_000)
    max_retries: int = Field(default=3, ge=0, le=100)
    retry_delay: int = Field(default=5, ge=0, le=86_400)
    timeout_seconds: int = Field(default=60, ge=1, le=86_400)


class JobAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    attempt_number: int
    worker_id: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    error_message: str | None
    result_json: dict[str, Any] | None


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    job_type: str
    queue_name: str
    priority: int
    status: str
    payload_json: dict[str, Any] | None
    result_json: dict[str, Any] | None
    idempotency_key: str | None
    correlation_id: str
    causation_id: str | None
    scheduled_for: datetime | None
    available_at: datetime
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    retry_count: int
    max_retries: int
    retry_delay: int
    timeout_seconds: int
    worker_id: str | None
    lease_expires_at: datetime | None
    last_heartbeat_at: datetime | None
    error_details_json: dict[str, Any] | None
    cancel_requested: bool
    schedule_id: UUID | None
    attempts: list[JobAttemptResponse] = Field(default_factory=list)


class WorkerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    worker_id: str
    queues_json: list[str]
    concurrency: int
    status: str
    started_at: datetime
    last_heartbeat_at: datetime
    active_job_count: int
    completed_job_count: int
    failed_job_count: int
    version: str
    metadata_json: dict[str, Any] | None = None


class ScheduleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    job_type: str = Field(min_length=1, max_length=100)
    queue_name: str = Field(default="default", min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
    recurrence_type: ScheduleRecurrenceType
    interval_seconds: int | None = Field(default=None, ge=1)
    cron_expression: str | None = Field(default=None, max_length=80)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    enabled: bool = True
    next_run_at: datetime | None = None
    misfire_policy: ScheduleMisfirePolicy = ScheduleMisfirePolicy.RUN_ONCE
    max_concurrent_runs: int = Field(default=1, ge=1, le=100)
    catch_up_limit: int = Field(default=3, ge=1, le=100)

    @model_validator(mode="after")
    def validate_recurrence(self) -> ScheduleCreateRequest:
        if self.recurrence_type == ScheduleRecurrenceType.INTERVAL and not self.interval_seconds:
            raise ValueError("interval_seconds is required for interval schedules")
        if self.recurrence_type == ScheduleRecurrenceType.CRON and not self.cron_expression:
            raise ValueError("cron_expression is required for cron schedules")
        return self


class ScheduleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    queue_name: str | None = Field(default=None, min_length=1, max_length=80)
    payload: dict[str, Any] | None = None
    interval_seconds: int | None = Field(default=None, ge=1)
    cron_expression: str | None = Field(default=None, max_length=80)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    next_run_at: datetime | None = None
    misfire_policy: ScheduleMisfirePolicy | None = None
    max_concurrent_runs: int | None = Field(default=None, ge=1, le=100)
    catch_up_limit: int | None = Field(default=None, ge=1, le=100)


class ScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str | None
    job_type: str
    queue_name: str
    payload_json: dict[str, Any] | None
    recurrence_type: str
    interval_seconds: int | None
    cron_expression: str | None
    timezone: str
    is_enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    misfire_policy: str
    max_concurrent_runs: int
    catch_up_limit: int
    active_run_count: int
    created_at: datetime
    updated_at: datetime


class DeadLetterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    job_id: UUID
    status: str
    reason: str
    error_details_json: dict[str, Any] | None
    retry_count: int
    created_at: datetime
    updated_at: datetime


class JobMetricsResponse(BaseModel):
    queued_jobs: int
    running_jobs: int
    scheduled_jobs: int
    succeeded_jobs: int
    failed_jobs: int
    dead_letter_jobs: int
    retries: int
    oldest_queued_job_age_seconds: float | None
    worker_heartbeat_age_seconds: float | None
    average_job_duration_seconds: float | None
    scheduler_lag_seconds: float | None
    jobs_by_type: dict[str, int]
    jobs_by_queue: dict[str, int]
