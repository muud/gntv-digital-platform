"""Pydantic contracts for the Media Library API."""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.cms.media.models import AssetType, ProcessingStatus, UploadStatus, URLStrategy


class UploadRequest(BaseModel):
    asset_type: AssetType
    filename: str = Field(min_length=1, max_length=512)
    mime_type: str = Field(min_length=3, max_length=255)
    file_size: int = Field(gt=0)
    checksum: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    language_code: str | None = Field(default=None, max_length=10)
    url_strategy: URLStrategy = URLStrategy.SIGNED
    metadata: dict[str, Any] = Field(default_factory=dict)


class UploadTarget(BaseModel):
    asset_id: UUID
    method: Literal["PUT"] = "PUT"
    upload_url: str
    headers: dict[str, str]
    expires_at: datetime


class ConfirmUploadRequest(BaseModel):
    checksum: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


class AssetUpdate(BaseModel):
    language_code: str | None = Field(default=None, max_length=10)
    copyright_holder: str | None = Field(default=None, max_length=255)
    copyright_notice: str | None = None
    license_starts_at: date | None = None
    license_ends_at: date | None = None
    url_strategy: URLStrategy | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("license_ends_at")
    @classmethod
    def validate_license_dates(cls, value: date | None, info: Any) -> date | None:
        starts = info.data.get("license_starts_at")
        if value is not None and starts is not None and value < starts:
            raise ValueError("license_ends_at must not precede license_starts_at")
        return value


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_type: AssetType
    original_filename: str
    storage_filename: str
    mime_type: str
    file_size: int
    width: int | None
    height: int | None
    duration_seconds: float | None
    language_code: str | None
    storage_provider: str
    storage_key: str
    url_strategy: URLStrategy
    download_url: str | None
    checksum: str
    upload_status: UploadStatus
    processing_status: ProcessingStatus
    owner_id: int
    copyright_holder: str | None
    copyright_notice: str | None
    license_starts_at: date | None
    license_ends_at: date | None
    created_by: int
    updated_by: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    metadata: dict[str, Any]


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int
    limit: int
    offset: int


class ContentAttachmentRequest(BaseModel):
    content_id: UUID


class BulkActionRequest(BaseModel):
    asset_ids: list[UUID] = Field(min_length=1, max_length=100)
    action: Literal["delete", "restore"]


class BulkActionResponse(BaseModel):
    affected: int


class DirectUploadResponse(BaseModel):
    asset: AssetResponse


__all__ = [
    "AssetListResponse", "AssetResponse", "AssetUpdate", "BulkActionRequest", "BulkActionResponse",
    "ConfirmUploadRequest", "ContentAttachmentRequest", "DirectUploadResponse", "UploadRequest", "UploadTarget",
]
