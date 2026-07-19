"""Pydantic contracts for the versioned editorial API."""

from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.editorial.models import AssignmentRole, CommentKind, NotificationChannel, Priority, WorkflowState


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class WorkflowCreate(BaseModel):
    content_id: UUID
    priority: Priority = Priority.NORMAL
    due_at: datetime | None = None


class WorkflowResponse(ORMModel):
    id: UUID
    content_id: UUID
    state: WorkflowState
    priority: Priority
    due_at: datetime | None
    scheduled_at: datetime | None
    timezone: str | None
    embargo_at: datetime | None
    unpublish_at: datetime | None
    published_at: datetime | None
    lock_version: int
    last_error: str | None
    created_by: int
    updated_by: int
    created_at: datetime
    updated_at: datetime


class TransitionRequest(BaseModel):
    target_state: WorkflowState
    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=2000)


class AssignmentUpsert(BaseModel):
    role: AssignmentRole
    user_id: int = Field(gt=0)


class AssignmentResponse(ORMModel):
    id: UUID
    workflow_id: UUID
    role: AssignmentRole
    user_id: int
    assigned_by: int
    assigned_at: datetime


class PlanningUpdate(BaseModel):
    priority: Priority | None = None
    due_at: datetime | None = None
    expected_version: int = Field(ge=1)


class CommentCreate(BaseModel):
    kind: CommentKind = CommentKind.INTERNAL
    body: str = Field(min_length=1, max_length=10000)
    mentions: list[int] = Field(default_factory=list)


class CommentResponse(ORMModel):
    id: UUID
    workflow_id: UUID
    author_id: int
    kind: CommentKind
    body: str
    mentions: list[int]
    created_at: datetime


class RevisionCreate(BaseModel):
    snapshot: dict[str, Any]
    change_summary: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)


class RevisionResponse(ORMModel):
    id: UUID
    workflow_id: UUID
    version: int
    snapshot: dict[str, Any]
    change_summary: str
    editor_id: int
    created_at: datetime


class VersionComparison(BaseModel):
    from_version: int
    to_version: int
    changes: dict[str, dict[str, Any]]


class ScheduleRequest(BaseModel):
    publish_at: datetime
    timezone: str
    embargo_at: datetime | None = None
    unpublish_at: datetime | None = None
    expected_version: int = Field(ge=1)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def valid_dates(self) -> "ScheduleRequest":
        if self.publish_at.tzinfo is None:
            raise ValueError("publish_at must include a UTC offset")
        if self.embargo_at is not None and self.embargo_at.tzinfo is None:
            raise ValueError("embargo_at must include a UTC offset")
        if self.unpublish_at is not None:
            if self.unpublish_at.tzinfo is None:
                raise ValueError("unpublish_at must include a UTC offset")
            if self.unpublish_at <= self.publish_at:
                raise ValueError("unpublish_at must be after publish_at")
        return self


class PublishRequest(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)


class WorkflowRestoreRequest(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=1000)


class ActivityResponse(ORMModel):
    id: UUID
    workflow_id: UUID
    actor_id: int
    event_type: str
    data: dict[str, Any]
    created_at: datetime


class NotificationResponse(ORMModel):
    id: UUID
    workflow_id: UUID
    recipient_id: int | None
    channel: NotificationChannel
    event_type: str
    payload: dict[str, Any]
    delivered_at: datetime | None
    created_at: datetime


class DashboardResponse(BaseModel):
    items: list[WorkflowResponse]
    total: int


class ProcessingResult(BaseModel):
    published: int = 0
    unpublished: int = 0
    failed: int = 0
