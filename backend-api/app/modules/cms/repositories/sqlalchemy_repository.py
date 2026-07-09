"""SQLAlchemy repository implementation for CMS persistence."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.cms.models import (
    CMSAsset,
    CMSAssetTranslation,
    CMSMediaFile,
    CMSWorkflowLog,
    ContentType,
    WorkflowState,
)
from app.modules.cms.repositories.interfaces import CMSRepositoryInterface


class SQLAlchemyCMSRepository(CMSRepositoryInterface):
    """SQLAlchemy-backed CMS repository."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_asset(
        self,
        *,
        content_type: ContentType,
        parent_asset_id: UUID | None = None,
        duration: timedelta | None = None,
        is_premium: bool = False,
        age_rating: str = "G",
        scheduled_publish_time: datetime | None = None,
    ) -> CMSAsset:
        asset = CMSAsset(
            content_type=content_type,
            parent_asset_id=parent_asset_id,
            duration=duration,
            is_premium=is_premium,
            age_rating=age_rating,
            scheduled_publish_time=scheduled_publish_time,
        )
        self.db.add(asset)
        self.db.flush()
        return asset

    def get_asset(self, asset_id: UUID) -> CMSAsset | None:
        return self.db.get(CMSAsset, asset_id)

    def list_assets(
        self,
        *,
        content_type: ContentType | None = None,
        publish_state: WorkflowState | None = None,
        parent_asset_id: UUID | None = None,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[CMSAsset]:
        statement = select(CMSAsset)
        if content_type is not None:
            statement = statement.where(CMSAsset.content_type == content_type)
        if publish_state is not None:
            statement = statement.where(CMSAsset.publish_state == publish_state)
        if parent_asset_id is not None:
            statement = statement.where(CMSAsset.parent_asset_id == parent_asset_id)
        if not include_deleted:
            statement = statement.where(CMSAsset.deleted_at.is_(None))
        statement = statement.order_by(CMSAsset.created_at.desc()).limit(limit).offset(offset)
        return self.db.execute(statement).scalars().all()

    def update_publish_state(
        self,
        *,
        asset: CMSAsset,
        new_state: WorkflowState,
        scheduled_publish_time: datetime | None = None,
    ) -> CMSAsset:
        asset.publish_state = new_state
        asset.scheduled_publish_time = scheduled_publish_time
        self.db.add(asset)
        self.db.flush()
        return asset

    def upsert_translation(
        self,
        *,
        asset_id: UUID,
        language_code: str,
        title: str,
        description: str | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
        transcript: str | None = None,
        subtitles_url: str | None = None,
    ) -> CMSAssetTranslation:
        translation = self.get_translation(asset_id=asset_id, language_code=language_code)
        if translation is None:
            translation = CMSAssetTranslation(asset_id=asset_id, language_code=language_code, title=title)

        translation.title = title
        translation.description = description
        translation.summary = summary
        translation.tags = tags or []
        translation.transcript = transcript
        translation.subtitles_url = subtitles_url
        self.db.add(translation)
        self.db.flush()
        return translation

    def get_translation(self, *, asset_id: UUID, language_code: str) -> CMSAssetTranslation | None:
        statement = select(CMSAssetTranslation).where(
            CMSAssetTranslation.asset_id == asset_id,
            CMSAssetTranslation.language_code == language_code,
        )
        return self.db.execute(statement).scalar_one_or_none()

    def list_translations(self, asset_id: UUID) -> Sequence[CMSAssetTranslation]:
        statement = (
            select(CMSAssetTranslation)
            .where(CMSAssetTranslation.asset_id == asset_id)
            .order_by(CMSAssetTranslation.language_code.asc())
        )
        return self.db.execute(statement).scalars().all()

    def add_media_file(
        self,
        *,
        asset_id: UUID,
        file_type: str,
        url: str,
        file_size: int,
        language_code: str | None = None,
        resolution: str | None = None,
        bitrate: int | None = None,
        codec: str | None = None,
    ) -> CMSMediaFile:
        media_file = CMSMediaFile(
            asset_id=asset_id,
            language_code=language_code,
            file_type=file_type,
            url=url,
            file_size=file_size,
            resolution=resolution,
            bitrate=bitrate,
            codec=codec,
        )
        self.db.add(media_file)
        self.db.flush()
        return media_file

    def list_media_files(self, asset_id: UUID) -> Sequence[CMSMediaFile]:
        statement = select(CMSMediaFile).where(CMSMediaFile.asset_id == asset_id).order_by(CMSMediaFile.created_at.desc())
        return self.db.execute(statement).scalars().all()

    def add_workflow_log(
        self,
        *,
        asset_id: UUID,
        actor_id: int,
        old_state: WorkflowState | None,
        new_state: WorkflowState,
        comment: str | None = None,
    ) -> CMSWorkflowLog:
        workflow_log = CMSWorkflowLog(
            asset_id=asset_id,
            actor_id=actor_id,
            old_state=old_state,
            new_state=new_state,
            comment=comment,
        )
        self.db.add(workflow_log)
        self.db.flush()
        return workflow_log

    def list_workflow_logs(self, asset_id: UUID) -> Sequence[CMSWorkflowLog]:
        statement = (
            select(CMSWorkflowLog).where(CMSWorkflowLog.asset_id == asset_id).order_by(CMSWorkflowLog.created_at.desc())
        )
        return self.db.execute(statement).scalars().all()
