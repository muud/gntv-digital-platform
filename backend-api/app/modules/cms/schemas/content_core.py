"""Pydantic schemas for CMS Content Core."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, field_validator

from app.modules.cms.models import ContentStatus, ContentType, ContentVisibility
from app.modules.cms.schemas.base import CMSSchemaBase


class CMSSEOPayload(CMSSchemaBase):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    keywords: list[str] = Field(default_factory=list)
    canonical_url: str | None = Field(default=None, max_length=2048)
    catalog_type: str | None = Field(default=None, max_length=30)
    category: str | None = Field(default=None, max_length=120)
    presenter: str | None = Field(default=None, max_length=255)
    duration: str | None = Field(default=None, max_length=20)


class CMSTaxonomyCreate(CMSSchemaBase):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = None


class CMSCategoryCreate(CMSTaxonomyCreate):
    parent_id: UUID | None = None


class CMSLanguageCreate(CMSSchemaBase):
    code: str = Field(min_length=2, max_length=10)
    name: str = Field(min_length=1, max_length=100)
    native_name: str | None = Field(default=None, max_length=100)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.lower()


class CMSRegionCreate(CMSSchemaBase):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=1, max_length=120)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()


class CMSContentCreate(CMSSchemaBase):
    title: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    summary: str | None = Field(default=None, max_length=500)
    body: str = Field(min_length=1)
    content_type: ContentType
    language_id: UUID
    visibility: ContentVisibility = ContentVisibility.PRIVATE
    category_id: UUID | None = None
    tag_ids: list[UUID] = Field(default_factory=list)
    genre_ids: list[UUID] = Field(default_factory=list)
    region_ids: list[UUID] = Field(default_factory=list)
    featured_image_asset_id: UUID | None = None
    media_asset_ids: list[UUID] = Field(default_factory=list)
    seo: CMSSEOPayload = Field(default_factory=CMSSEOPayload)


class CMSContentUpdate(CMSSchemaBase):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    summary: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, min_length=1)
    content_type: ContentType | None = None
    language_id: UUID | None = None
    visibility: ContentVisibility | None = None
    category_id: UUID | None = None
    tag_ids: list[UUID] | None = None
    genre_ids: list[UUID] | None = None
    region_ids: list[UUID] | None = None
    featured_image_asset_id: UUID | None = None
    media_asset_ids: list[UUID] | None = None
    seo: CMSSEOPayload | None = None


class CMSContentTransitionRequest(CMSSchemaBase):
    transition: str = Field(min_length=1, max_length=50)
    editor_id: int | None = None
    scheduled_publish_at: datetime | None = None


class CMSLanguageResponse(CMSSchemaBase):
    id: UUID
    code: str
    name: str
    native_name: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CMSCategoryResponse(CMSSchemaBase):
    id: UUID
    name: str
    slug: str
    description: str | None
    parent_id: UUID | None
    created_at: datetime
    updated_at: datetime


class CMSTagResponse(CMSSchemaBase):
    id: UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


class CMSGenreResponse(CMSTagResponse):
    pass


class CMSRegionResponse(CMSSchemaBase):
    id: UUID
    code: str
    name: str
    created_at: datetime
    updated_at: datetime


class CMSContentResponse(CMSSchemaBase):
    id: UUID
    title: str
    slug: str
    summary: str | None
    body: str
    content_type: ContentType
    language_id: UUID
    status: ContentStatus
    visibility: ContentVisibility
    author_id: int
    editor_id: int | None
    category_id: UUID | None
    tag_ids: list[UUID]
    genre_ids: list[UUID]
    region_ids: list[UUID]
    featured_image_asset_id: UUID | None
    media_asset_ids: list[UUID]
    seo: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    archived_at: datetime | None


class CMSContentListResponse(CMSSchemaBase):
    items: list[CMSContentResponse]
    total: int
    limit: int
    offset: int
