"""Celery producer boundary for ingest control commands; no task executes here."""

from asyncio import to_thread
from typing import Any, Protocol, cast

from celery import Celery  # type: ignore[import-untyped]

from app.core.config import settings


class IngestDispatcherInterface(Protocol):
    async def dispatch(
        self, event_name: str, payload: dict[str, Any], *, idempotency_key: str
    ) -> str: ...
    def configured(self) -> bool: ...


class CeleryIngestDispatcher:
    """Publish named messages to the stream-control queue only."""

    allowed_events = frozenset(
        {
            "streaming.ingest.admitted",
            "streaming.ingest.started",
            "streaming.ingest.degraded",
            "streaming.ingest.recovered",
            "streaming.ingest.disconnected",
            "streaming.ingest.failed",
        }
    )

    def __init__(self, celery_app: Celery | None = None) -> None:
        self.app = celery_app or Celery("gntv-streaming-dispatch", broker=str(settings.REDIS_URL))

    async def dispatch(
        self, event_name: str, payload: dict[str, Any], *, idempotency_key: str
    ) -> str:
        if event_name not in self.allowed_events:
            raise ValueError("unsupported ingest dispatch event")
        result = await to_thread(
            self.app.send_task,
            event_name,
            kwargs={"event": payload},
            queue="stream-control",
            task_id=idempotency_key,
        )
        return cast(str, result.id)

    def configured(self) -> bool:
        return bool(self.app.conf.broker_url)


dispatcher = CeleryIngestDispatcher()


__all__ = ["CeleryIngestDispatcher", "IngestDispatcherInterface", "dispatcher"]
