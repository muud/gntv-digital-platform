from uuid import uuid4

from app.modules.cms.events import (
    CMSAIEnrichmentRequested,
    CMSCDNCachePurgeRequested,
    CMSMediaTranscodeRequested,
    CMSSearchIndexRequested,
    CMSWorkflowTransitioned,
)
from app.modules.cms.models import WorkflowState
from app.modules.cms.workers import (
    AI_ENRICHMENT_TASK,
    CDN_CACHE_PURGE_TASK,
    MEDIA_TRANSCODE_TASK,
    SEARCH_INDEX_TASK,
    WORKFLOW_TRANSITION_TASK,
    CMSWorkerDispatcher,
    CMSWorkerPayload,
    payload_for_event,
    task_name_for_event,
)


class FakeQueuePublisher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, CMSWorkerPayload]] = []

    def enqueue(self, *, task_name: str, payload: CMSWorkerPayload) -> str:
        self.calls.append((task_name, payload))
        return "task-123"


def test_task_name_mapping_for_ai_event() -> None:
    event = CMSAIEnrichmentRequested(asset_id=uuid4(), source_language="so")

    assert task_name_for_event(event) == AI_ENRICHMENT_TASK


def test_task_name_mapping_for_media_event() -> None:
    event = CMSMediaTranscodeRequested(
        asset_id=uuid4(),
        source_url="oss://raw/source.mp4",
        target_bucket="gntv-streaming-media",
    )

    assert task_name_for_event(event) == MEDIA_TRANSCODE_TASK


def test_task_name_mapping_for_cdn_event() -> None:
    event = CMSCDNCachePurgeRequested(asset_id=uuid4(), urls=("https://cdn.example/master.m3u8",))

    assert task_name_for_event(event) == CDN_CACHE_PURGE_TASK


def test_task_name_mapping_for_search_event() -> None:
    event = CMSSearchIndexRequested(asset_id=uuid4(), language_codes=("so", "en"))

    assert task_name_for_event(event) == SEARCH_INDEX_TASK


def test_workflow_event_payload() -> None:
    asset_id = uuid4()
    event = CMSWorkflowTransitioned(
        asset_id=asset_id,
        actor_id=99,
        old_state=WorkflowState.DRAFT,
        new_state=WorkflowState.REVIEW,
    )

    assert task_name_for_event(event) == WORKFLOW_TRANSITION_TASK
    assert payload_for_event(event) == {
        "asset_id": str(asset_id),
        "occurred_at": event.occurred_at.isoformat(),
        "actor_id": 99,
        "old_state": "draft",
        "new_state": "review",
    }


def test_dispatcher_enqueues_event_payload() -> None:
    publisher = FakeQueuePublisher()
    dispatcher = CMSWorkerDispatcher(publisher)
    event = CMSAIEnrichmentRequested(asset_id=uuid4(), source_language="so")

    task_id = dispatcher.enqueue_event(event)

    assert task_id == "task-123"
    assert publisher.calls == [
        (
            AI_ENRICHMENT_TASK,
            {
                "asset_id": str(event.asset_id),
                "occurred_at": event.occurred_at.isoformat(),
                "source_language": "so",
            },
        )
    ]
