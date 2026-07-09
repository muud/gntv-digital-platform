"""CMS event payloads for asynchronous processing."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, TypeAlias
from uuid import UUID

from app.modules.cms.models import WorkflowState

CMSEventName: TypeAlias = Literal[
    "cms.ai_enrichment_requested",
    "cms.media_transcode_requested",
    "cms.cdn_cache_purge_requested",
    "cms.search_index_requested",
    "cms.workflow_transitioned",
]


@dataclass(frozen=True, kw_only=True)
class CMSAssetEvent:
    asset_id: UUID
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, kw_only=True)
class CMSAIEnrichmentRequested(CMSAssetEvent):
    source_language: str
    event_name: CMSEventName = "cms.ai_enrichment_requested"


@dataclass(frozen=True, kw_only=True)
class CMSMediaTranscodeRequested(CMSAssetEvent):
    source_url: str
    target_bucket: str
    event_name: CMSEventName = "cms.media_transcode_requested"


@dataclass(frozen=True, kw_only=True)
class CMSCDNCachePurgeRequested(CMSAssetEvent):
    urls: tuple[str, ...]
    event_name: CMSEventName = "cms.cdn_cache_purge_requested"


@dataclass(frozen=True, kw_only=True)
class CMSSearchIndexRequested(CMSAssetEvent):
    language_codes: tuple[str, ...]
    event_name: CMSEventName = "cms.search_index_requested"


@dataclass(frozen=True, kw_only=True)
class CMSWorkflowTransitioned(CMSAssetEvent):
    old_state: WorkflowState | None
    new_state: WorkflowState
    actor_id: int
    event_name: CMSEventName = "cms.workflow_transitioned"


CMSEvent: TypeAlias = (
    CMSAIEnrichmentRequested
    | CMSMediaTranscodeRequested
    | CMSCDNCachePurgeRequested
    | CMSSearchIndexRequested
    | CMSWorkflowTransitioned
)
