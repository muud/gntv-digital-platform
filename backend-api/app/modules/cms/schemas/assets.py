"""Pydantic schemas for CMS asset transport contracts."""

from datetime import datetime, timedelta
from uuid import UUID

from pydantic import Field

from app.modules.cms.models import ContentType, WorkflowState
from app.modules.cms.schemas.base import CMSSchemaBase


class CMSAssetCreate(CMSSchemaBase):
    content_type: ContentType
    parent_asset_id: UUID | None = None
    duration: timedelta | None = None
    is_premium: bool = False
    age_rating: str = Field(default="G", max_length=10)
    scheduled_publish_time: datetime | None = None


class CMSAssetResponse(CMSSchemaBase):
    id: UUID
    content_type: ContentType
    parent_asset_id: UUID | None
    duration: timedelta | None
    publish_state: WorkflowState
    scheduled_publish_time: datetime | None
    is_premium: bool
    age_rating: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class CMSAssetTranslationUpsert(CMSSchemaBase):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    summary: str | None = Field(default=None, max_length=500)
    tags: list[str] = Field(default_factory=list)
    transcript: str | None = None
    subtitles_url: str | None = Field(default=None, max_length=2048)


class CMSAssetTranslationResponse(CMSSchemaBase):
    id: int
    asset_id: UUID
    language_code: str
    title: str
    description: str | None
    summary: str | None
    tags: list[str]
    transcript: str | None
    subtitles_url: str | None
    created_at: datetime
    updated_at: datetime


class CMSUploadUrlRequest(CMSSchemaBase):
    file_name: str = Field(min_length=1, max_length=255)
    file_size: int = Field(gt=0)
    content_type: str = Field(min_length=1, max_length=100)


class CMSUploadUrlResponse(CMSSchemaBase):
    upload_url: str
    media_file_id: UUID


class CMSMediaFileResponse(CMSSchemaBase):
    id: UUID
    asset_id: UUID
    language_code: str | None
    file_type: str
    url: str
    file_size: int
    resolution: str | None
    bitrate: int | None
    codec: str | None
    created_at: datetime


class CMSWorkflowTransitionRequest(CMSSchemaBase):
    transition: str = Field(min_length=1, max_length=50)
    comment: str | None = None


class CMSWorkflowTransitionResponse(CMSSchemaBase):
    asset_id: UUID
    old_state: WorkflowState | None
    new_state: WorkflowState
    transition_timestamp: datetime


class CMSWorkflowLogResponse(CMSSchemaBase):
    id: int
    asset_id: UUID
    actor_id: int
    old_state: WorkflowState | None
    new_state: WorkflowState
    comment: str | None
    created_at: datetime
