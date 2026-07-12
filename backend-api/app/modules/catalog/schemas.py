from datetime import date, datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field
from app.modules.catalog.models import CatalogStatus, CatalogType, CreditRole


class TaxonomyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    code: str | None = None


class PersonCreate(BaseModel):
    name: str
    biography: str | None = None
    image_asset_id: UUID | None = None


class StudioCreate(BaseModel):
    name: str
    website: str | None = None


class CreditInput(BaseModel):
    person_id: UUID
    role: CreditRole
    character_name: str | None = None
    position: int = 0


class CatalogItemCreate(BaseModel):
    catalog_type: CatalogType
    status: CatalogStatus = CatalogStatus.DRAFT
    title: str = Field(min_length=1, max_length=255)
    slug: str = Field(pattern=r"^[a-z0-9-]+$")
    synopsis: str | None = None
    parent_id: UUID | None = None
    season_number: int | None = Field(default=None, ge=1)
    episode_number: int | None = Field(default=None, ge=1)
    duration_seconds: int | None = Field(default=None, ge=0)
    release_date: date | None = None
    is_premium: bool = False
    is_kids: bool = False
    age_rating: str | None = None
    stream_url: str | None = None
    media_asset_id: UUID | None = None
    poster_asset_id: UUID | None = None
    studio_id: UUID | None = None
    genre_ids: list[UUID] = []
    language_ids: list[UUID] = []
    region_ids: list[UUID] = []
    credits: list[CreditInput] = []
    seo_title: str | None = None
    seo_description: str | None = None
    seo_keywords: list[str] = []
    metadata: dict[str, Any] = {}


class CatalogItemUpdate(BaseModel):
    title: str | None = None
    synopsis: str | None = None
    status: CatalogStatus | None = None
    duration_seconds: int | None = None
    is_premium: bool | None = None
    is_kids: bool | None = None
    age_rating: str | None = None
    stream_url: str | None = None
    media_asset_id: UUID | None = None
    poster_asset_id: UUID | None = None
    studio_id: UUID | None = None
    genre_ids: list[UUID] | None = None
    language_ids: list[UUID] | None = None
    region_ids: list[UUID] | None = None
    credits: list[CreditInput] | None = None
    seo_title: str | None = None
    seo_description: str | None = None
    seo_keywords: list[str] | None = None
    metadata: dict[str, Any] | None = None


class CreditResponse(BaseModel):
    person_id: UUID
    person_name: str
    role: CreditRole
    character_name: str | None
    position: int


class CatalogItemResponse(BaseModel):
    id: UUID
    catalog_type: CatalogType
    status: CatalogStatus
    title: str
    slug: str
    synopsis: str | None
    parent_id: UUID | None
    season_number: int | None
    episode_number: int | None
    duration_seconds: int | None
    release_date: date | None
    is_premium: bool
    is_kids: bool
    age_rating: str | None
    stream_url: str | None
    media_asset_id: UUID | None
    poster_asset_id: UUID | None
    studio_id: UUID | None
    genre_ids: list[UUID]
    language_ids: list[UUID]
    region_ids: list[UUID]
    credits: list[CreditResponse]
    seo: dict[str, Any]
    ai_metadata: dict[str, Any]
    ai_enrichment_status: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CatalogListResponse(BaseModel):
    items: list[CatalogItemResponse]
    total: int
    limit: int
    offset: int


class CollectionCreate(BaseModel):
    title: str
    slug: str
    description: str | None = None
    is_featured: bool = False
    row_style: str = "landscape"
    position: int = 0
    item_ids: list[UUID] = []


class CollectionUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    is_featured: bool | None = None
    row_style: str | None = None
    position: int | None = None
    item_ids: list[UUID] | None = None


class CollectionResponse(BaseModel):
    id: UUID
    title: str
    slug: str
    description: str | None
    is_featured: bool
    row_style: str
    position: int
    items: list[CatalogItemResponse]


class ProgressUpdate(BaseModel):
    position_seconds: int = Field(ge=0)
    duration_seconds: int = Field(gt=0)
    completed: bool = False


class ProgressResponse(BaseModel):
    item: CatalogItemResponse
    position_seconds: int
    duration_seconds: int
    completed: bool
    updated_at: datetime


class RatingUpdate(BaseModel):
    score: float = Field(ge=0, le=5)


class AIHookRequest(BaseModel):
    hook: str = Field(pattern=r"^(classify|summarize|tag|seo|recommend)$")
