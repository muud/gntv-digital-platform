"""Persisted models for Module 8 Sprint 8.5 GNTV Autopilot."""

from __future__ import annotations

from dataclasses import dataclass
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
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.jobs.models import enum_type


@dataclass
class AutopilotKidsMetadata:
    production_id: UUID | None = None
    made_for_kids: bool = True
    child_safe: bool = True
    parental_review_required: bool = False
    reviewed_by_user_id: int | None = None
    age_band: str = "6-12"
    comments_policy: str = "disabled"
    advertising_policy: str = "none"


def utc_now() -> datetime:
    return datetime.now(UTC)


class AutopilotBrand(StrEnum):
    GNTV_DIGITAL = "GNTV_DIGITAL"
    GNTV_KIDS = "GNTV_KIDS"


class AutopilotContentType(StrEnum):
    NEWS = "NEWS"
    INTERVIEW = "INTERVIEW"
    TALK_SHOW = "TALK_SHOW"
    DOCUMENTARY = "DOCUMENTARY"
    KIDS_STORY = "KIDS_STORY"
    SHORT = "SHORT"
    SOCIAL_CLIP = "SOCIAL_CLIP"
    PROMO = "PROMO"
    LIVE_EVENT = "LIVE_EVENT"
    OTHER = "OTHER"


class ProductionStatus(StrEnum):
    DRAFT = "draft"
    RESEARCHING = "researching"
    RESEARCH_READY = "research_ready"
    SCRIPTING = "scripting"
    SCRIPT_REVIEW = "script_review"
    PRODUCTION_PLANNING = "production_planning"
    ASSET_PREPARATION = "asset_preparation"
    AWAITING_FINAL_APPROVAL = "awaiting_final_approval"
    APPROVED = "approved"
    PUBLISHING_QUEUED = "publishing_queued"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    PARTIALLY_PUBLISHED = "partially_published"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProductionPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ResearchStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    APPROVED = "approved"
    FAILED = "failed"


class ScriptStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    REVISION_REQUESTED = "revision_requested"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class AssetType(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    THUMBNAIL = "thumbnail"
    LOWER_THIRD = "lower_third"
    SUBTITLE = "subtitle"
    TRANSCRIPT = "transcript"
    SCRIPT = "script"
    RESEARCH_DOCUMENT = "research_document"
    GRAPHICS_PACKAGE = "graphics_package"
    MUSIC = "music"
    OTHER = "other"


class AssetStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalType(StrEnum):
    RESEARCH = "research"
    SCRIPT = "script"
    PRODUCTION_PLAN = "production_plan"
    FINAL_CONTENT = "final_content"
    PUBLISHING_PLAN = "publishing_plan"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PublishingPlatform(StrEnum):
    YOUTUBE = "YOUTUBE"
    FACEBOOK = "FACEBOOK"
    INSTAGRAM = "INSTAGRAM"
    TIKTOK = "TIKTOK"
    X = "X"
    WEBSITE = "WEBSITE"
    OTT = "OTT"
    IPTV = "IPTV"
    INTERNAL_ARCHIVE = "INTERNAL_ARCHIVE"


class Visibility(StrEnum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"
    INTERNAL = "internal"


class PublishAttemptStatus(StrEnum):
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    VERIFICATION_PENDING = "verification_pending"
    VERIFIED = "verified"


class PublishingPolicyCode(StrEnum):
    ALWAYS_REQUIRE_FINAL_APPROVAL = "ALWAYS_REQUIRE_FINAL_APPROVAL"
    ALLOW_SCHEDULED_APPROVED_CONTENT = "ALLOW_SCHEDULED_APPROVED_CONTENT"
    BLOCK_UNVERIFIED_RESEARCH = "BLOCK_UNVERIFIED_RESEARCH"
    REQUIRE_THUMBNAIL = "REQUIRE_THUMBNAIL"
    REQUIRE_SUBTITLES = "REQUIRE_SUBTITLES"
    REQUIRE_KIDS_METADATA = "REQUIRE_KIDS_METADATA"
    REQUIRE_EDITOR_APPROVAL = "REQUIRE_EDITOR_APPROVAL"


class AutopilotAuditAction(StrEnum):
    PRODUCTION_CREATED = "production_created"
    PRODUCTION_UPDATED = "production_updated"
    RESEARCH_STARTED = "research_started"
    RESEARCH_COMPLETED = "research_completed"
    SCRIPT_CREATED = "script_created"
    SCRIPT_APPROVED = "script_approved"
    PRODUCTION_PLAN_CREATED = "production_plan_created"
    ASSET_ADDED = "asset_added"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_APPROVED = "approval_approved"
    APPROVAL_REJECTED = "approval_rejected"
    PUBLISH_PLAN_CREATED = "publish_plan_created"
    PUBLISH_QUEUED = "publish_queued"
    PUBLISH_STARTED = "publish_started"
    PUBLISH_SUCCEEDED = "publish_succeeded"
    PUBLISH_FAILED = "publish_failed"
    PUBLISH_VERIFIED = "publish_verified"
    PRODUCTION_COMPLETED = "production_completed"
    PRODUCTION_CANCELLED = "production_cancelled"


class AutopilotProduction(Base):
    __tablename__ = "autopilot_productions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[AutopilotBrand] = mapped_column(
        enum_type(AutopilotBrand, "autopilot_brand_enum"), nullable=False
    )
    content_type: Mapped[AutopilotContentType] = mapped_column(
        enum_type(AutopilotContentType, "autopilot_content_type_enum"), nullable=False
    )
    program_name: Mapped[str | None] = mapped_column(String(160))
    language: Mapped[str] = mapped_column(String(40), nullable=False, default="English")
    audience: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[ProductionStatus] = mapped_column(
        enum_type(ProductionStatus, "autopilot_production_status_enum"),
        nullable=False,
        default=ProductionStatus.DRAFT,
    )
    priority: Mapped[ProductionPriority] = mapped_column(
        enum_type(ProductionPriority, "autopilot_production_priority_enum"),
        nullable=False,
        default=ProductionPriority.NORMAL,
    )
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    assigned_editor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    workflow_run_id: Mapped[UUID | None] = mapped_column()
    correlation_id: Mapped[str] = mapped_column(String(160), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(160))
    idempotency_key: Mapped[str | None] = mapped_column(String(160))
    target_publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    brief: Mapped[AutopilotBrief | None] = relationship(
        back_populates="production", cascade="all, delete-orphan", uselist=False
    )
    research_tasks: Mapped[list[AutopilotResearchTask]] = relationship(
        back_populates="production", cascade="all, delete-orphan"
    )
    scripts: Mapped[list[AutopilotScriptVersion]] = relationship(
        back_populates="production", cascade="all, delete-orphan"
    )
    production_plan: Mapped[AutopilotProductionPlan | None] = relationship(
        back_populates="production", cascade="all, delete-orphan", uselist=False
    )
    assets: Mapped[list[AutopilotAsset]] = relationship(
        back_populates="production", cascade="all, delete-orphan"
    )
    approvals: Mapped[list[AutopilotApproval]] = relationship(
        back_populates="production", cascade="all, delete-orphan"
    )
    publishing_plans: Mapped[list[AutopilotPublishingPlan]] = relationship(
        back_populates="production", cascade="all, delete-orphan"
    )
    attempts: Mapped[list[AutopilotPublishingAttempt]] = relationship(
        back_populates="production", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list[AutopilotAuditLog]] = relationship(
        back_populates="production", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("slug", name="uq_autopilot_production_slug"),
        UniqueConstraint(
            "idempotency_key", name="uq_autopilot_production_idempotency"
        ),
        Index("ix_autopilot_productions_status", "status"),
        Index("ix_autopilot_productions_brand", "brand"),
        Index("ix_autopilot_productions_correlation", "correlation_id"),
    )


class AutopilotBrief(Base):
    __tablename__ = "autopilot_briefs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    production_id: Mapped[UUID] = mapped_column(
        ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False
    )
    working_title: Mapped[str] = mapped_column(String(240), nullable=False)
    editorial_goal: Mapped[str | None] = mapped_column(Text)
    target_audience: Mapped[str | None] = mapped_column(String(240))
    key_questions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    required_facts: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    required_sources: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    tone: Mapped[str | None] = mapped_column(String(80))
    language: Mapped[str] = mapped_column(String(40), nullable=False, default="English")
    estimated_duration: Mapped[str | None] = mapped_column(String(80))
    presenter: Mapped[str | None] = mapped_column(String(160))
    guests: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    location: Mapped[str | None] = mapped_column(String(160))
    production_notes: Mapped[str | None] = mapped_column(Text)
    restrictions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    production: Mapped[AutopilotProduction] = relationship(back_populates="brief")
    __table_args__ = (UniqueConstraint("production_id", name="uq_autopilot_brief"),)


class AutopilotResearchTask(Base):
    __tablename__ = "autopilot_research_tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    production_id: Mapped[UUID] = mapped_column(
        ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ResearchStatus] = mapped_column(
        enum_type(ResearchStatus, "autopilot_research_status_enum"),
        nullable=False,
        default=ResearchStatus.PENDING,
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    summary: Mapped[str | None] = mapped_column(Text)
    key_facts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    unresolved_questions: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    risks: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    editorial_notes: Mapped[str | None] = mapped_column(Text)
    generated_material_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    editor_material_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    verified_material_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    production: Mapped[AutopilotProduction] = relationship(
        back_populates="research_tasks"
    )
    __table_args__ = (
        UniqueConstraint(
            "production_id", "idempotency_key", name="uq_autopilot_research_idem"
        ),
    )


class AutopilotScriptVersion(Base):
    __tablename__ = "autopilot_script_versions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    production_id: Mapped[UUID] = mapped_column(
        ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    presenter_notes: Mapped[str | None] = mapped_column(Text)
    graphics_notes: Mapped[str | None] = mapped_column(Text)
    lower_third_notes: Mapped[str | None] = mapped_column(Text)
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    generated_by_agent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id")
    )
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[ScriptStatus] = mapped_column(
        enum_type(ScriptStatus, "autopilot_script_status_enum"),
        nullable=False,
        default=ScriptStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    production: Mapped[AutopilotProduction] = relationship(back_populates="scripts")
    __table_args__ = (
        UniqueConstraint(
            "production_id", "version", name="uq_autopilot_script_version"
        ),
    )


class AutopilotProductionPlan(Base):
    __tablename__ = "autopilot_production_plans"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    production_id: Mapped[UUID] = mapped_column(
        ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False
    )
    presenter: Mapped[str | None] = mapped_column(String(160))
    guests: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    studio_location: Mapped[str | None] = mapped_column(String(200))
    camera_requirements: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    audio_requirements: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    graphics: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    lower_thirds: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    thumbnails: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    b_roll: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    teleprompter: Mapped[str | None] = mapped_column(Text)
    music: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    subtitles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    language_tracks: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    estimated_duration: Mapped[str | None] = mapped_column(String(80))
    recording_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edit_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    production: Mapped[AutopilotProduction] = relationship(
        back_populates="production_plan"
    )
    __table_args__ = (UniqueConstraint("production_id", name="uq_autopilot_plan"),)


class AutopilotAsset(Base):
    __tablename__ = "autopilot_assets"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    production_id: Mapped[UUID] = mapped_column(
        ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False
    )
    asset_type: Mapped[AssetType] = mapped_column(
        enum_type(AssetType, "autopilot_asset_type_enum"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    storage_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[str | None] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[AssetStatus] = mapped_column(
        enum_type(AssetStatus, "autopilot_asset_status_enum"),
        nullable=False,
        default=AssetStatus.DRAFT,
    )
    checksum: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    production: Mapped[AutopilotProduction] = relationship(back_populates="assets")


class AutopilotApproval(Base):
    __tablename__ = "autopilot_approvals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    production_id: Mapped[UUID] = mapped_column(
        ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False
    )
    approval_type: Mapped[ApprovalType] = mapped_column(
        enum_type(ApprovalType, "autopilot_approval_type_enum"), nullable=False
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        enum_type(ApprovalStatus, "autopilot_approval_status_enum"),
        nullable=False,
        default=ApprovalStatus.PENDING,
    )
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decision_reason: Mapped[str | None] = mapped_column(String(1000))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    production: Mapped[AutopilotProduction] = relationship(back_populates="approvals")


class AutopilotPublishingDestination(Base):
    __tablename__ = "autopilot_publishing_destinations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    platform: Mapped[PublishingPlatform] = mapped_column(
        enum_type(PublishingPlatform, "autopilot_publishing_platform_enum"),
        nullable=False,
    )
    account_reference: Mapped[str | None] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_visibility: Mapped[Visibility] = mapped_column(
        enum_type(Visibility, "autopilot_visibility_enum"),
        nullable=False,
        default=Visibility.PRIVATE,
    )
    language: Mapped[str | None] = mapped_column(String(40))
    audience: Mapped[str | None] = mapped_column(String(160))
    publishing_policy: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    __table_args__ = (
        UniqueConstraint("name", "platform", name="uq_autopilot_destination"),
    )


class AutopilotPublishingPlan(Base):
    __tablename__ = "autopilot_publishing_plans"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    production_id: Mapped[UUID] = mapped_column(
        ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False
    )
    destination_id: Mapped[UUID] = mapped_column(
        ForeignKey("autopilot_publishing_destinations.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    hashtags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    thumbnail_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("autopilot_assets.id")
    )
    language: Mapped[str] = mapped_column(String(40), nullable=False)
    visibility: Mapped[Visibility] = mapped_column(
        enum_type(Visibility, "autopilot_plan_visibility_enum"),
        nullable=False,
        default=Visibility.PRIVATE,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    audience_classification: Mapped[str | None] = mapped_column(String(160))
    platform_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    kids_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    production: Mapped[AutopilotProduction] = relationship(
        back_populates="publishing_plans"
    )
    destination: Mapped[AutopilotPublishingDestination] = relationship()
    attempts: Mapped[list[AutopilotPublishingAttempt]] = relationship(
        back_populates="plan"
    )
    __table_args__ = (
        UniqueConstraint(
            "production_id", "destination_id", name="uq_autopilot_publish_plan_dest"
        ),
    )


class AutopilotPublishingAttempt(Base):
    __tablename__ = "autopilot_publishing_attempts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    production_id: Mapped[UUID] = mapped_column(
        ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False
    )
    publishing_plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("autopilot_publishing_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    destination_id: Mapped[UUID] = mapped_column(
        ForeignKey("autopilot_publishing_destinations.id"), nullable=False
    )
    status: Mapped[PublishAttemptStatus] = mapped_column(
        enum_type(PublishAttemptStatus, "autopilot_publish_attempt_status_enum"),
        nullable=False,
        default=PublishAttemptStatus.QUEUED,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(240))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    safe_error_summary: Mapped[str | None] = mapped_column(String(1000))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    production: Mapped[AutopilotProduction] = relationship(back_populates="attempts")
    plan: Mapped[AutopilotPublishingPlan] = relationship(back_populates="attempts")
    destination: Mapped[AutopilotPublishingDestination] = relationship()
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_autopilot_attempt_idem"),
        Index("ix_autopilot_attempt_status", "status"),
    )


class AutopilotAuditLog(Base):
    __tablename__ = "autopilot_audit_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    production_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("autopilot_productions.id", ondelete="CASCADE")
    )
    action: Mapped[AutopilotAuditAction] = mapped_column(
        enum_type(AutopilotAuditAction, "autopilot_audit_action_enum"),
        nullable=False,
    )
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    correlation_id: Mapped[str | None] = mapped_column(String(160))
    causation_id: Mapped[str | None] = mapped_column(String(160))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    production: Mapped[AutopilotProduction | None] = relationship(
        back_populates="audit_logs"
    )
    __table_args__ = (Index("ix_autopilot_audit_production", "production_id"),)
