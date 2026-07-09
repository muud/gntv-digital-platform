from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.cms.models import ContentType, WorkflowState
from app.modules.cms.schemas import (
    CMSAssetCreate,
    CMSAssetResponse,
    CMSAssetTranslationUpsert,
    CMSUploadUrlRequest,
    CMSWorkflowTransitionResponse,
)


def test_asset_create_accepts_approved_api_payload() -> None:
    parent_id = uuid4()

    payload = CMSAssetCreate.model_validate(
        {
            "content_type": "movie",
            "parent_asset_id": parent_id,
            "duration": timedelta(hours=1, minutes=45),
            "is_premium": True,
            "age_rating": "PG-13",
        }
    )

    assert payload.content_type == ContentType.MOVIE
    assert payload.parent_asset_id == parent_id
    assert payload.duration == timedelta(hours=1, minutes=45)
    assert payload.is_premium is True
    assert payload.age_rating == "PG-13"


def test_asset_create_rejects_unknown_content_type() -> None:
    with pytest.raises(ValidationError):
        CMSAssetCreate.model_validate({"content_type": "unknown"})


def test_translation_upsert_defaults_tags() -> None:
    payload = CMSAssetTranslationUpsert(title="Hogaamiyeyaasha Geeska Afrika")

    assert payload.title == "Hogaamiyeyaasha Geeska Afrika"
    assert payload.tags == []


def test_upload_url_request_requires_positive_file_size() -> None:
    with pytest.raises(ValidationError):
        CMSUploadUrlRequest(file_name="clip.mp4", file_size=0, content_type="video/mp4")


def test_asset_response_supports_from_attributes() -> None:
    asset_id = uuid4()
    created_at = datetime.now(UTC)

    class AssetRecord:
        id = asset_id
        content_type = ContentType.ARTICLE
        parent_asset_id = None
        duration = None
        publish_state = WorkflowState.DRAFT
        scheduled_publish_time = None
        is_premium = False
        age_rating = "G"
        updated_at = created_at
        deleted_at = None

        def __init__(self, created_at: datetime) -> None:
            self.created_at = created_at

    record = AssetRecord(created_at)

    response = CMSAssetResponse.model_validate(record)

    assert response.id == asset_id
    assert response.content_type == ContentType.ARTICLE
    assert response.publish_state == WorkflowState.DRAFT


def test_workflow_transition_response_shape() -> None:
    asset_id = uuid4()
    timestamp = datetime.now(UTC)

    response = CMSWorkflowTransitionResponse.model_validate(
        {
            "asset_id": asset_id,
            "old_state": "draft",
            "new_state": "review",
            "transition_timestamp": timestamp,
        }
    )

    assert response.asset_id == asset_id
    assert response.old_state == WorkflowState.DRAFT
    assert response.new_state == WorkflowState.REVIEW
    assert response.transition_timestamp == timestamp
