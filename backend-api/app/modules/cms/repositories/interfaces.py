"""Repository contracts for CMS persistence boundaries."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.modules.cms.models import (
    CMSAsset,
    CMSAssetTranslation,
    CMSMediaFile,
    CMSWorkflowLog,
    ContentType,
    WorkflowState,
)


class CMSAssetRepositoryInterface(Protocol):
    """Persistence boundary for CMS assets."""

    def create_asset(
        self,
        *,
        content_type: ContentType,
        parent_asset_id: UUID | None = None,
        duration: timedelta | None = None,
        is_premium: bool = False,
        age_rating: str = "G",
        scheduled_publish_time: datetime | None = None,
    ) -> CMSAsset: ...

    def get_asset(self, asset_id: UUID) -> CMSAsset | None: ...

    def list_assets(
        self,
        *,
        content_type: ContentType | None = None,
        publish_state: WorkflowState | None = None,
        parent_asset_id: UUID | None = None,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[CMSAsset]: ...

    def update_publish_state(
        self,
        *,
        asset: CMSAsset,
        new_state: WorkflowState,
        scheduled_publish_time: datetime | None = None,
    ) -> CMSAsset: ...


class CMSTranslationRepositoryInterface(Protocol):
    """Persistence boundary for localized asset metadata."""

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
    ) -> CMSAssetTranslation: ...

    def get_translation(self, *, asset_id: UUID, language_code: str) -> CMSAssetTranslation | None: ...

    def list_translations(self, asset_id: UUID) -> Sequence[CMSAssetTranslation]: ...


class CMSMediaRepositoryInterface(Protocol):
    """Persistence boundary for CMS media file records."""

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
    ) -> CMSMediaFile: ...

    def list_media_files(self, asset_id: UUID) -> Sequence[CMSMediaFile]: ...


class CMSWorkflowRepositoryInterface(Protocol):
    """Persistence boundary for workflow audit records."""

    def add_workflow_log(
        self,
        *,
        asset_id: UUID,
        actor_id: int,
        old_state: WorkflowState | None,
        new_state: WorkflowState,
        comment: str | None = None,
    ) -> CMSWorkflowLog: ...

    def list_workflow_logs(self, asset_id: UUID) -> Sequence[CMSWorkflowLog]: ...


class CMSRepositoryInterface(
    CMSAssetRepositoryInterface,
    CMSTranslationRepositoryInterface,
    CMSMediaRepositoryInterface,
    CMSWorkflowRepositoryInterface,
    Protocol,
):
    """Combined CMS persistence boundary."""
