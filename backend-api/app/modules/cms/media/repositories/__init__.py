"""SQLAlchemy repository for Media Library assets."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.cms.media.models import AssetType, CMSMediaFile, ProcessingStatus, UploadStatus
from app.modules.cms.models.content import CMSContent


class MediaRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, asset: CMSMediaFile) -> CMSMediaFile:
        self.db.add(asset)
        self.db.flush()
        return asset

    def get(self, asset_id: UUID) -> CMSMediaFile | None:
        return self.db.get(CMSMediaFile, asset_id)

    def list(
        self, *, search: str | None, asset_type: AssetType | None, upload_status: UploadStatus | None,
        processing_status: ProcessingStatus | None, include_deleted: bool, limit: int, offset: int,
    ) -> tuple[Sequence[CMSMediaFile], int]:
        filters: list[Any] = []
        if not include_deleted:
            filters.append(CMSMediaFile.deleted_at.is_(None))
        if search:
            term = f"%{search}%"
            filters.append(or_(CMSMediaFile.original_filename.ilike(term), CMSMediaFile.storage_key.ilike(term)))
        if asset_type:
            filters.append(CMSMediaFile.asset_type == asset_type)
        if upload_status:
            filters.append(CMSMediaFile.upload_status == upload_status)
        if processing_status:
            filters.append(CMSMediaFile.processing_status == processing_status)
        items = self.db.execute(select(CMSMediaFile).where(*filters).order_by(CMSMediaFile.created_at.desc()).limit(limit).offset(offset)).scalars().all()
        total = self.db.execute(select(func.count()).select_from(CMSMediaFile).where(*filters)).scalar_one()
        return items, int(total)

    def update(self, asset: CMSMediaFile, values: dict[str, Any]) -> CMSMediaFile:
        for key, value in values.items():
            setattr(asset, key, value)
        return self.add(asset)

    def content(self, content_id: UUID) -> CMSContent | None:
        return self.db.get(CMSContent, content_id)

    def attach(self, asset: CMSMediaFile, content: CMSContent) -> None:
        if asset not in content.media_assets:
            content.media_assets.append(asset)
            self.db.flush()

    def detach(self, asset: CMSMediaFile, content: CMSContent) -> None:
        if asset in content.media_assets:
            content.media_assets.remove(asset)
            self.db.flush()

    def mark_deleted(self, asset: CMSMediaFile, at: datetime | None) -> None:
        asset.deleted_at = at
        self.add(asset)


__all__ = ["MediaRepository"]
