"""Narrow Celery producer for approved Sprint 5.3 media queues."""

from asyncio import to_thread
from typing import Any, Protocol, cast

from celery import Celery  # type: ignore[import-untyped]

from app.core.config import settings


class ProcessingDispatcher(Protocol):
    async def enqueue(
        self, *, task_name: str, queue: str, payload: dict[str, Any], task_id: str
    ) -> str: ...
    async def cancel(self, task_id: str) -> None: ...


class CeleryProcessingDispatcher:
    allowed_routes = {
        "transcode-cpu": "streaming.media.transcode_cpu",
        "transcode-accelerated": "streaming.media.transcode_accelerated",
        "manifest": "streaming.media.manifest",
        "thumbnail": "streaming.media.thumbnail",
    }

    def __init__(self, celery_app: Celery | None = None) -> None:
        self.app = celery_app or Celery("gntv-processing-dispatch", broker=str(settings.REDIS_URL))

    async def enqueue(
        self, *, task_name: str, queue: str, payload: dict[str, Any], task_id: str
    ) -> str:
        if self.allowed_routes.get(queue) != task_name:
            raise ValueError("task route is outside the approved processing queues")
        result = await to_thread(
            self.app.send_task,
            task_name,
            kwargs={"payload": payload},
            queue=queue,
            task_id=task_id,
        )
        return cast(str, result.id)

    async def cancel(self, task_id: str) -> None:
        await to_thread(self.app.control.revoke, task_id, terminate=True, signal="SIGTERM")


dispatcher = CeleryProcessingDispatcher()
