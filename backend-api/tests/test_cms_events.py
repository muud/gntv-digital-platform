from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from app.modules.cms.events import (
    CMSAIEnrichmentRequested,
    CMSCDNCachePurgeRequested,
    CMSMediaTranscodeRequested,
    CMSSearchIndexRequested,
    CMSWorkflowTransitioned,
)
from app.modules.cms.models import WorkflowState


def test_ai_enrichment_event_payload() -> None:
    asset_id = uuid4()

    event = CMSAIEnrichmentRequested(asset_id=asset_id, source_language="so")

    assert event.event_name == "cms.ai_enrichment_requested"
    assert event.asset_id == asset_id
    assert event.source_language == "so"


def test_media_transcode_event_payload() -> None:
    event = CMSMediaTranscodeRequested(
        asset_id=uuid4(),
        source_url="oss://raw/source.mp4",
        target_bucket="gntv-streaming-media",
    )

    assert event.event_name == "cms.media_transcode_requested"
    assert event.source_url == "oss://raw/source.mp4"
    assert event.target_bucket == "gntv-streaming-media"


def test_cache_purge_event_payload() -> None:
    event = CMSCDNCachePurgeRequested(asset_id=uuid4(), urls=("https://cdn.example/master.m3u8",))

    assert event.event_name == "cms.cdn_cache_purge_requested"
    assert event.urls == ("https://cdn.example/master.m3u8",)


def test_search_index_event_payload() -> None:
    event = CMSSearchIndexRequested(asset_id=uuid4(), language_codes=("so", "en"))

    assert event.event_name == "cms.search_index_requested"
    assert event.language_codes == ("so", "en")


def test_workflow_transition_event_payload() -> None:
    event = CMSWorkflowTransitioned(
        asset_id=uuid4(),
        actor_id=7,
        old_state=WorkflowState.DRAFT,
        new_state=WorkflowState.REVIEW,
    )

    assert event.event_name == "cms.workflow_transitioned"
    assert event.old_state == WorkflowState.DRAFT
    assert event.new_state == WorkflowState.REVIEW
    assert event.actor_id == 7


def test_events_are_immutable() -> None:
    event = CMSAIEnrichmentRequested(asset_id=uuid4(), source_language="so")

    with pytest.raises(FrozenInstanceError):
        setattr(event, "source_language", "en")
