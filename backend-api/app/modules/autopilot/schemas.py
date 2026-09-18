"""Pydantic contracts for Sprint 8.5 Autopilot."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.autopilot.models import (
    ApprovalType,
    AssetStatus,
    AssetType,
    AutopilotBrand,
    AutopilotContentType,
    ProductionPriority,
    PublishingPlatform,
    Visibility,
)


class ORMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProductionCreate(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=160)
    description: str | None = None
    brand: AutopilotBrand = AutopilotBrand.GNTV_DIGITAL
    content_type: AutopilotContentType = AutopilotContentType.OTHER
    program_name: str | None = Field(default=None, max_length=160)
    language: str = Field(default="English", max_length=40)
    audience: str | None = Field(default=None, max_length=160)
    priority: ProductionPriority = ProductionPriority.NORMAL
    assigned_editor_user_id: int | None = None
    target_publish_at: datetime | None = None
    correlation_id: str | None = Field(default=None, max_length=160)
    causation_id: str | None = Field(default=None, max_length=160)
    idempotency_key: str | None = Field(default=None, max_length=160)


class ProductionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=240)
    description: str | None = None
    program_name: str | None = Field(default=None, max_length=160)
    language: str | None = Field(default=None, max_length=40)
    audience: str | None = Field(default=None, max_length=160)
    priority: ProductionPriority | None = None
    assigned_editor_user_id: int | None = None
    target_publish_at: datetime | None = None


class BriefUpsert(BaseModel):
    working_title: str = Field(min_length=2, max_length=240)
    editorial_goal: str | None = None
    target_audience: str | None = Field(default=None, max_length=240)
    key_questions: list[str] = Field(default_factory=list)
    required_facts: list[str] = Field(default_factory=list)
    required_sources: list[str] = Field(default_factory=list)
    tone: str | None = Field(default=None, max_length=80)
    language: str = Field(default="English", max_length=40)
    estimated_duration: str | None = Field(default=None, max_length=80)
    presenter: str | None = Field(default=None, max_length=160)
    guests: list[str] = Field(default_factory=list)
    location: str | None = Field(default=None, max_length=160)
    production_notes: str | None = None
    restrictions: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] | None = None


class ScriptCreate(BaseModel):
    language: str = Field(default="English", max_length=40)
    title: str = Field(min_length=2, max_length=240)
    body: str = Field(min_length=1)
    presenter_notes: str | None = None
    graphics_notes: str | None = None
    lower_third_notes: str | None = None
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    generated_by_agent_run_id: UUID | None = None
    status: str = "draft"


class ProductionPlanCreate(BaseModel):
    presenter: str | None = Field(default=None, max_length=160)
    guests: list[str] = Field(default_factory=list)
    studio_location: str | None = Field(default=None, max_length=200)
    camera_requirements: list[str] = Field(default_factory=list)
    audio_requirements: list[str] = Field(default_factory=list)
    graphics: list[str] = Field(default_factory=list)
    lower_thirds: list[str] = Field(default_factory=list)
    thumbnails: list[str] = Field(default_factory=list)
    b_roll: list[str] = Field(default_factory=list)
    teleprompter: str | None = None
    music: list[str] = Field(default_factory=list)
    subtitles: list[str] = Field(default_factory=list)
    language_tracks: list[str] = Field(default_factory=list)
    estimated_duration: str | None = Field(default=None, max_length=80)
    recording_date: datetime | None = None
    edit_deadline: datetime | None = None
    metadata_json: dict[str, Any] | None = None


class AssetCreate(BaseModel):
    asset_type: AssetType
    name: str = Field(min_length=1, max_length=200)
    storage_reference: str = Field(min_length=1, max_length=500)
    mime_type: str | None = Field(default=None, max_length=120)
    language: str | None = Field(default=None, max_length=40)
    version: int = Field(default=1, ge=1)
    status: AssetStatus = AssetStatus.DRAFT
    checksum: str | None = Field(default=None, max_length=128)
    metadata_json: dict[str, Any] | None = None


class ApprovalRequestCreate(BaseModel):
    approval_type: ApprovalType
    expires_at: datetime | None = None


class ApprovalDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class DestinationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    platform: PublishingPlatform
    account_reference: str | None = Field(default=None, max_length=200)
    enabled: bool = True
    default_visibility: Visibility = Visibility.PRIVATE
    language: str | None = Field(default=None, max_length=40)
    audience: str | None = Field(default=None, max_length=160)
    publishing_policy: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] | None = None


class PublishingPlanCreate(BaseModel):
    destination_id: UUID
    title: str = Field(min_length=2, max_length=240)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    thumbnail_asset_id: UUID | None = None
    language: str = Field(default="English", max_length=40)
    visibility: Visibility = Visibility.PRIVATE
    scheduled_at: datetime | None = None
    captions: list[str] = Field(default_factory=list)
    audience_classification: str | None = Field(default=None, max_length=160)
    platform_metadata_json: dict[str, Any] | None = None
    kids_metadata_json: dict[str, Any] | None = None


class PublishRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=160)


class StageRequest(BaseModel):
    agent_id: UUID | None = None
    idempotency_key: str | None = Field(default=None, max_length=160)


class ProductionResponse(ORMResponse):
    id: UUID
    title: str
    slug: str
    brand: str
    content_type: str
    language: str
    status: str
    priority: str
    owner_user_id: int | None
    assigned_editor_user_id: int | None
    workflow_run_id: UUID | None
    correlation_id: str
    causation_id: str | None
    idempotency_key: str | None
    target_publish_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BriefResponse(ORMResponse):
    id: UUID
    production_id: UUID
    working_title: str
    editorial_goal: str | None
    target_audience: str | None
    key_questions: list[str]
    required_facts: list[str]
    required_sources: list[str]
    language: str
    metadata_json: dict[str, Any] | None


class ScriptResponse(ORMResponse):
    id: UUID
    production_id: UUID
    version: int
    language: str
    title: str
    body: str
    generated_by_agent_run_id: UUID | None
    status: str
    created_at: datetime
    approved_at: datetime | None


class AssetResponse(ORMResponse):
    id: UUID
    production_id: UUID
    asset_type: str
    name: str
    storage_reference: str
    mime_type: str | None
    language: str | None
    status: str
    checksum: str | None
    created_at: datetime
    approved_at: datetime | None


class ApprovalResponse(ORMResponse):
    id: UUID
    production_id: UUID
    approval_type: str
    status: str
    requested_by_user_id: int | None
    decided_by_user_id: int | None
    decision_reason: str | None
    requested_at: datetime
    decided_at: datetime | None
    expires_at: datetime | None


class DestinationResponse(ORMResponse):
    id: UUID
    name: str
    platform: str
    account_reference: str | None
    enabled: bool
    default_visibility: str
    language: str | None
    audience: str | None
    publishing_policy: list[str]
    metadata_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class PublishingPlanResponse(ORMResponse):
    id: UUID
    production_id: UUID
    destination_id: UUID
    title: str
    description: str | None
    tags: list[str]
    hashtags: list[str]
    thumbnail_asset_id: UUID | None
    language: str
    visibility: str
    scheduled_at: datetime | None
    captions: list[str]
    audience_classification: str | None
    platform_metadata_json: dict[str, Any] | None
    kids_metadata_json: dict[str, Any] | None
    created_at: datetime


class PublishingAttemptResponse(ORMResponse):
    id: UUID
    production_id: UUID
    publishing_plan_id: UUID
    destination_id: UUID
    status: str
    attempt_number: int
    idempotency_key: str
    provider_reference: str | None
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    safe_error_summary: str | None
    metadata_json: dict[str, Any] | None
    created_at: datetime


class ProductionDetailResponse(ProductionResponse):
    brief: BriefResponse | None = None
    scripts: list[ScriptResponse] = Field(default_factory=list)
    assets: list[AssetResponse] = Field(default_factory=list)
    approvals: list[ApprovalResponse] = Field(default_factory=list)
    publishing_plans: list[PublishingPlanResponse] = Field(default_factory=list)
    attempts: list[PublishingAttemptResponse] = Field(default_factory=list)


class MetricsResponse(BaseModel):
    productions_by_state: dict[str, int]
    awaiting_approval: int
    scheduled_publications: int
    publishing_queue_depth: int
    destination_success_failure: dict[str, dict[str, int]]
    partial_publishing_count: int
    oldest_pending_production: datetime | None
    ai_agent_usage: int
    durable_job_status: dict[str, int]
