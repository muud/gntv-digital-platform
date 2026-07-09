"""CMS content application service."""

from datetime import datetime
from uuid import UUID

from app.modules.cms.models import CMSAsset, CMSAssetTranslation, CMSMediaFile, CMSWorkflowLog, WorkflowState
from app.modules.cms.repositories import CMSRepositoryInterface
from app.modules.cms.schemas import CMSAssetCreate, CMSAssetTranslationUpsert
from app.modules.cms.services.exceptions import CMSAssetNotFoundError, CMSInvalidTransitionError
from app.modules.cms.services.interfaces import CMSServiceInterface

TransitionTarget = tuple[WorkflowState, WorkflowState]

TRANSITION_TARGETS: dict[str, TransitionTarget] = {
    "submit": (WorkflowState.DRAFT, WorkflowState.REVIEW),
    "verify": (WorkflowState.REVIEW, WorkflowState.FACT_CHECK),
    "authenticate": (WorkflowState.FACT_CHECK, WorkflowState.EDITORIAL_APPROVAL),
    "release": (WorkflowState.SCHEDULED, WorkflowState.PUBLISHED),
    "retire": (WorkflowState.PUBLISHED, WorkflowState.ARCHIVED),
    "rollback": (WorkflowState.PUBLISHED, WorkflowState.DRAFT),
    "archive_draft": (WorkflowState.DRAFT, WorkflowState.ARCHIVED),
}


class CMSContentService(CMSServiceInterface):
    """Application service for CMS asset operations."""

    def __init__(self, repository: CMSRepositoryInterface) -> None:
        self.repository = repository

    def create_asset(self, payload: CMSAssetCreate) -> CMSAsset:
        return self.repository.create_asset(
            content_type=payload.content_type,
            parent_asset_id=payload.parent_asset_id,
            duration=payload.duration,
            is_premium=payload.is_premium,
            age_rating=payload.age_rating,
            scheduled_publish_time=payload.scheduled_publish_time,
        )

    def upsert_translation(
        self,
        *,
        asset_id: UUID,
        language_code: str,
        payload: CMSAssetTranslationUpsert,
    ) -> CMSAssetTranslation:
        self._require_asset(asset_id)
        return self.repository.upsert_translation(
            asset_id=asset_id,
            language_code=language_code,
            title=payload.title,
            description=payload.description,
            summary=payload.summary,
            tags=payload.tags,
            transcript=payload.transcript,
            subtitles_url=payload.subtitles_url,
        )

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
    ) -> CMSMediaFile:
        self._require_asset(asset_id)
        return self.repository.add_media_file(
            asset_id=asset_id,
            file_type=file_type,
            url=url,
            file_size=file_size,
            language_code=language_code,
            resolution=resolution,
            bitrate=bitrate,
            codec=codec,
        )

    def transition_workflow(
        self,
        *,
        asset_id: UUID,
        actor_id: int,
        transition: str,
        comment: str | None = None,
        scheduled_publish_time: datetime | None = None,
    ) -> CMSWorkflowLog:
        asset = self._require_asset(asset_id)
        old_state = asset.publish_state
        new_state = self._resolve_transition(
            transition=transition,
            old_state=old_state,
            scheduled_publish_time=scheduled_publish_time,
        )
        self.repository.update_publish_state(
            asset=asset,
            new_state=new_state,
            scheduled_publish_time=scheduled_publish_time if new_state == WorkflowState.SCHEDULED else None,
        )
        return self.repository.add_workflow_log(
            asset_id=asset_id,
            actor_id=actor_id,
            old_state=old_state,
            new_state=new_state,
            comment=comment,
        )

    def _require_asset(self, asset_id: UUID) -> CMSAsset:
        asset = self.repository.get_asset(asset_id)
        if asset is None:
            raise CMSAssetNotFoundError(asset_id)
        return asset

    def _resolve_transition(
        self,
        *,
        transition: str,
        old_state: WorkflowState,
        scheduled_publish_time: datetime | None,
    ) -> WorkflowState:
        if transition == "approve":
            if old_state != WorkflowState.EDITORIAL_APPROVAL:
                raise CMSInvalidTransitionError(transition)
            return WorkflowState.SCHEDULED if scheduled_publish_time is not None else WorkflowState.PUBLISHED

        target = TRANSITION_TARGETS.get(transition)
        if target is None:
            raise CMSInvalidTransitionError(transition)

        source_state, target_state = target
        if old_state != source_state:
            raise CMSInvalidTransitionError(transition)
        return target_state
