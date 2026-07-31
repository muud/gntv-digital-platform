"""Explicit lifecycle rules for the ingest control plane."""

from app.modules.streaming.ingest.contracts import IngestEventType
from app.modules.streaming.ingest.errors import IngestError
from app.modules.streaming.models import StreamStatus


class IngestStateMachine:
    """Resolve gateway events to durable stream states."""

    _transitions: dict[tuple[StreamStatus, IngestEventType], StreamStatus] = {
        (StreamStatus.ADMITTED, IngestEventType.STARTED): StreamStatus.LIVE,
        (StreamStatus.ADMITTED, IngestEventType.DISCONNECTED): StreamStatus.STOPPED,
        (StreamStatus.ADMITTED, IngestEventType.FAILED): StreamStatus.FAILED,
        (StreamStatus.LIVE, IngestEventType.DEGRADED): StreamStatus.DEGRADED,
        (StreamStatus.LIVE, IngestEventType.DISCONNECTED): StreamStatus.STOPPED,
        (StreamStatus.LIVE, IngestEventType.FAILED): StreamStatus.FAILED,
        (StreamStatus.DEGRADED, IngestEventType.RECOVERED): StreamStatus.LIVE,
        (StreamStatus.DEGRADED, IngestEventType.DISCONNECTED): StreamStatus.STOPPED,
        (StreamStatus.DEGRADED, IngestEventType.FAILED): StreamStatus.FAILED,
    }

    def transition(self, current: StreamStatus, event: IngestEventType) -> StreamStatus:
        target = self._transitions.get((current, event))
        if target is None:
            raise IngestError(
                "invalid_ingest_transition",
                f"Event '{event.value}' is not valid while stream is '{current.value}'",
                status_code=409,
            )
        return target


__all__ = ["IngestStateMachine"]
