"""Service contracts for CMS application behavior."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.modules.cms.models import CMSAsset, CMSAssetTranslation, CMSMediaFile, CMSWorkflowLog
from app.modules.cms.schemas import CMSAssetCreate, CMSAssetTranslationUpsert


class CMSContentServiceInterface(Protocol):
    """Application boundary for CMS content operations."""

    def create_asset(self, payload: CMSAssetCreate) -> CMSAsset: ...

    def upsert_translation(
        self,
        *,
        asset_id: UUID,
        language_code: str,
        payload: CMSAssetTranslationUpsert,
    ) -> CMSAssetTranslation: ...

    def register_media_file(
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
    ) -> CMSMediaFile: ...

    def transition_workflow(
        self,
        *,
        asset_id: UUID,
        actor_id: int,
        transition: str,
        comment: str | None = None,
        scheduled_publish_time: datetime | None = None,
    ) -> CMSWorkflowLog: ...


class CMSServiceInterface(CMSContentServiceInterface, Protocol):
    """Combined CMS service boundary."""
