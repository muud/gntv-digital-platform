from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.modules.cms.models import CMSAsset, CMSAssetTranslation, CMSMediaFile, CMSWorkflowLog, ContentType, WorkflowState
from app.modules.cms.schemas import CMSAssetCreate, CMSAssetTranslationUpsert
from app.modules.cms.services import CMSAssetNotFoundError, CMSContentService, CMSInvalidTransitionError


class FakeCMSRepository:
    def __init__(self, assets: Sequence[CMSAsset] = ()) -> None:
        self.assets = {asset.id: asset for asset in assets}
        self.created_assets: list[CMSAsset] = []
        self.translations: list[CMSAssetTranslation] = []
        self.media_files: list[CMSMediaFile] = []
        self.workflow_logs: list[CMSWorkflowLog] = []

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
        asset.id = uuid4()
        asset.publish_state = WorkflowState.DRAFT
        self.assets[asset.id] = asset
        self.created_assets.append(asset)
        return asset

    def get_asset(self, asset_id: UUID) -> CMSAsset | None:
        return self.assets.get(asset_id)

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
        del content_type, publish_state, parent_asset_id, include_deleted, limit, offset
        return list(self.assets.values())

    def update_publish_state(
        self,
        *,
        asset: CMSAsset,
        new_state: WorkflowState,
        scheduled_publish_time: datetime | None = None,
    ) -> CMSAsset:
        asset.publish_state = new_state
        asset.scheduled_publish_time = scheduled_publish_time
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
        translation = CMSAssetTranslation(
            asset_id=asset_id,
            language_code=language_code,
            title=title,
            description=description,
            summary=summary,
            tags=tags or [],
            transcript=transcript,
            subtitles_url=subtitles_url,
        )
        self.translations.append(translation)
        return translation

    def get_translation(self, *, asset_id: UUID, language_code: str) -> CMSAssetTranslation | None:
        return next(
            (
                translation
                for translation in self.translations
                if translation.asset_id == asset_id and translation.language_code == language_code
            ),
            None,
        )

    def list_translations(self, asset_id: UUID) -> Sequence[CMSAssetTranslation]:
        return [translation for translation in self.translations if translation.asset_id == asset_id]

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
            file_type=file_type,
            url=url,
            file_size=file_size,
            language_code=language_code,
            resolution=resolution,
            bitrate=bitrate,
            codec=codec,
        )
        self.media_files.append(media_file)
        return media_file

    def list_media_files(self, asset_id: UUID) -> Sequence[CMSMediaFile]:
        return [media_file for media_file in self.media_files if media_file.asset_id == asset_id]

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
        self.workflow_logs.append(workflow_log)
        return workflow_log

    def list_workflow_logs(self, asset_id: UUID) -> Sequence[CMSWorkflowLog]:
        return [workflow_log for workflow_log in self.workflow_logs if workflow_log.asset_id == asset_id]


def make_asset(state: WorkflowState) -> CMSAsset:
    asset = CMSAsset(content_type=ContentType.MOVIE)
    asset.id = uuid4()
    asset.publish_state = state
    return asset


def test_create_asset_delegates_to_repository() -> None:
    repository = FakeCMSRepository()
    service = CMSContentService(repository)

    asset = service.create_asset(CMSAssetCreate(content_type=ContentType.MOVIE, is_premium=True, age_rating="PG-13"))

    assert asset in repository.created_assets
    assert asset.content_type == ContentType.MOVIE
    assert asset.is_premium is True
    assert asset.publish_state == WorkflowState.DRAFT


def test_upsert_translation_requires_existing_asset() -> None:
    repository = FakeCMSRepository()
    service = CMSContentService(repository)

    with pytest.raises(CMSAssetNotFoundError):
        service.upsert_translation(
            asset_id=uuid4(),
            language_code="so",
            payload=CMSAssetTranslationUpsert(title="Missing"),
        )


def test_upsert_translation_delegates_payload() -> None:
    asset = make_asset(WorkflowState.DRAFT)
    repository = FakeCMSRepository([asset])
    service = CMSContentService(repository)

    translation = service.upsert_translation(
        asset_id=asset.id,
        language_code="so",
        payload=CMSAssetTranslationUpsert(title="Title", tags=["news"]),
    )

    assert translation in repository.translations
    assert translation.asset_id == asset.id
    assert translation.language_code == "so"
    assert translation.tags == ["news"]


def test_register_media_file_requires_existing_asset() -> None:
    repository = FakeCMSRepository()
    service = CMSContentService(repository)

    with pytest.raises(CMSAssetNotFoundError):
        service.register_media_file(asset_id=uuid4(), file_type="thumbnail", url="https://cdn.example/t.jpg", file_size=1)


def test_workflow_submit_transition_updates_state_and_logs() -> None:
    asset = make_asset(WorkflowState.DRAFT)
    repository = FakeCMSRepository([asset])
    service = CMSContentService(repository)

    workflow_log = service.transition_workflow(asset_id=asset.id, actor_id=42, transition="submit", comment="Ready")

    assert asset.publish_state == WorkflowState.REVIEW
    assert workflow_log.old_state == WorkflowState.DRAFT
    assert workflow_log.new_state == WorkflowState.REVIEW
    assert workflow_log.comment == "Ready"


def test_workflow_approve_schedules_when_timestamp_is_present() -> None:
    asset = make_asset(WorkflowState.EDITORIAL_APPROVAL)
    repository = FakeCMSRepository([asset])
    service = CMSContentService(repository)
    publish_at = datetime.now(UTC)

    workflow_log = service.transition_workflow(
        asset_id=asset.id,
        actor_id=42,
        transition="approve",
        scheduled_publish_time=publish_at,
    )

    assert asset.publish_state == WorkflowState.SCHEDULED
    assert asset.scheduled_publish_time == publish_at
    assert workflow_log.new_state == WorkflowState.SCHEDULED


def test_workflow_rejects_invalid_transition() -> None:
    asset = make_asset(WorkflowState.DRAFT)
    repository = FakeCMSRepository([asset])
    service = CMSContentService(repository)

    with pytest.raises(CMSInvalidTransitionError):
        service.transition_workflow(asset_id=asset.id, actor_id=42, transition="verify")
