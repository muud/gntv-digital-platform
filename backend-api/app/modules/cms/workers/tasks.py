"""CMS worker task dispatch helpers."""

from typing import TYPE_CHECKING, TypeAlias

from app.modules.cms.events import (
    CMSAIEnrichmentRequested,
    CMSCDNCachePurgeRequested,
    CMSEvent,
    CMSMediaTranscodeRequested,
    CMSSearchIndexRequested,
    CMSWorkflowTransitioned,
)

if TYPE_CHECKING:
    from app.modules.cms.workers.interfaces import CMSQueuePublisherInterface

CMSWorkerPayloadValue: TypeAlias = str | int | tuple[str, ...] | None
CMSWorkerPayload: TypeAlias = dict[str, CMSWorkerPayloadValue]

AI_ENRICHMENT_TASK = "tasks.ai_enrichment_pipeline"
MEDIA_TRANSCODE_TASK = "tasks.media_transcode_pipeline"
CDN_CACHE_PURGE_TASK = "tasks.cdn_cache_purge"
SEARCH_INDEX_TASK = "tasks.search_index_asset"
WORKFLOW_TRANSITION_TASK = "tasks.workflow_transition_side_effects"


def task_name_for_event(event: CMSEvent) -> str:
    if isinstance(event, CMSAIEnrichmentRequested):
        return AI_ENRICHMENT_TASK
    if isinstance(event, CMSMediaTranscodeRequested):
        return MEDIA_TRANSCODE_TASK
    if isinstance(event, CMSCDNCachePurgeRequested):
        return CDN_CACHE_PURGE_TASK
    if isinstance(event, CMSSearchIndexRequested):
        return SEARCH_INDEX_TASK
    if isinstance(event, CMSWorkflowTransitioned):
        return WORKFLOW_TRANSITION_TASK


def payload_for_event(event: CMSEvent) -> CMSWorkerPayload:
    payload: CMSWorkerPayload = {
        "asset_id": str(event.asset_id),
        "occurred_at": event.occurred_at.isoformat(),
    }

    if isinstance(event, CMSAIEnrichmentRequested):
        payload["source_language"] = event.source_language
    elif isinstance(event, CMSMediaTranscodeRequested):
        payload["source_url"] = event.source_url
        payload["target_bucket"] = event.target_bucket
    elif isinstance(event, CMSCDNCachePurgeRequested):
        payload["urls"] = event.urls
    elif isinstance(event, CMSSearchIndexRequested):
        payload["language_codes"] = event.language_codes
    elif isinstance(event, CMSWorkflowTransitioned):
        payload["actor_id"] = event.actor_id
        payload["old_state"] = event.old_state.value if event.old_state is not None else None
        payload["new_state"] = event.new_state.value

    return payload


class CMSWorkerDispatcher:
    """Maps typed CMS events to queue tasks."""

    def __init__(self, queue_publisher: "CMSQueuePublisherInterface") -> None:
        self.queue_publisher = queue_publisher

    def enqueue_event(self, event: CMSEvent) -> str:
        return self.queue_publisher.enqueue(task_name=task_name_for_event(event), payload=payload_for_event(event))
