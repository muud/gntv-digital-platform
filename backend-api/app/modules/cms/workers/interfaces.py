"""Worker contracts for CMS asynchronous task dispatch."""

from typing import Protocol

from app.modules.cms.events import CMSEvent
from app.modules.cms.workers.tasks import CMSWorkerPayload


class CMSWorkerInterface(Protocol):
    """Boundary for enqueueing CMS asynchronous work."""

    def enqueue_event(self, event: CMSEvent) -> str: ...


class CMSQueuePublisherInterface(Protocol):
    """Queue adapter boundary used by CMS worker dispatch."""

    def enqueue(self, *, task_name: str, payload: CMSWorkerPayload) -> str: ...
