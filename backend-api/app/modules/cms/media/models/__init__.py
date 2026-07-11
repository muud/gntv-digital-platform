"""Media Library persistence models."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Date, DateTime, Enum, ForeignKey, Index, JSON, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AssetType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    POSTER = "poster"
    THUMBNAIL = "thumbnail"
    HERO = "hero"
    CHANNEL_LOGO = "channel_logo"
    SUBTITLE = "subtitle"
    CAPTION = "caption"
    TRANSCRIPT = "transcript"
    TRAILER = "trailer"
    PREVIEW = "preview"
    ATTACHMENT = "attachment"


class UploadStatus(StrEnum):
    PENDING = "pending"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    FAILED = "failed"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class URLStrategy(StrEnum):
    PUBLIC = "public"
    SIGNED = "signed"


class CMSMediaFile(Base):
    """Canonical reusable DAM asset, retaining Module 1's table and fields."""

    __tablename__ = "cms_media_files"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    asset_type: Mapped[AssetType] = mapped_column(Enum(AssetType, name="gntv_media_asset_type", values_callable=lambda e: [x.value for x in e]), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(nullable=True)
    height: Mapped[int | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(12, 3), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    storage_provider: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    url_strategy: Mapped[URLStrategy] = mapped_column(Enum(URLStrategy, name="gntv_media_url_strategy", values_callable=lambda e: [x.value for x in e]), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    upload_status: Mapped[UploadStatus] = mapped_column(Enum(UploadStatus, name="gntv_media_upload_status", values_callable=lambda e: [x.value for x in e]), nullable=False)
    processing_status: Mapped[ProcessingStatus] = mapped_column(Enum(ProcessingStatus, name="gntv_media_processing_status", values_callable=lambda e: [x.value for x in e]), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    copyright_holder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    copyright_notice: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_starts_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    license_ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    # Legacy Module 1 compatibility fields.
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, default="")
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bitrate: Mapped[int | None] = mapped_column(nullable=True)
    codec: Mapped[str | None] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        Index("idx_cms_media_search", "asset_type", "mime_type", "created_at"),
        Index("idx_cms_media_status", "upload_status", "processing_status", "deleted_at"),
        Index("idx_cms_media_owner", "owner_id"),
        Index("idx_cms_media_checksum", "checksum"),
    )


__all__ = ["AssetType", "CMSMediaFile", "ProcessingStatus", "UploadStatus", "URLStrategy"]
