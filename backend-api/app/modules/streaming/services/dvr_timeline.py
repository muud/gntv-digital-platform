"""Redis-backed DVR timeline primitives for Sprint 6.3."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Protocol
from uuid import UUID

from redis.asyncio import Redis

from app.modules.streaming.models import DVRSegmentIndex


def timeline_key(channel_id: UUID) -> str:
    return f"dvr:timeline:{channel_id}"


def live_edge_key(channel_id: UUID, manifest_format: str) -> str:
    return f"manifest:live_edge:{channel_id}:{manifest_format}"


def segment_payload(segment: DVRSegmentIndex) -> dict[str, Any]:
    return {
        "id": str(segment.id),
        "live_channel_id": str(segment.live_channel_id),
        "stream_id": str(segment.stream_id) if segment.stream_id else None,
        "live_event_id": str(segment.live_event_id) if segment.live_event_id else None,
        "recording_id": str(segment.recording_id) if segment.recording_id else None,
        "rendition": segment.rendition,
        "sequence_number": segment.sequence_number,
        "segment_uri": segment.segment_uri,
        "segment_start_at": segment.segment_start_at.isoformat(),
        "segment_end_at": segment.segment_end_at.isoformat(),
        "duration_seconds": segment.duration_seconds,
        "provider_event_id": segment.provider_event_id,
        "apsara_object_key": segment.apsara_object_key,
        "is_pruned": segment.is_pruned,
        "metadata_json": segment.metadata_json,
    }


class DVRTimelineStore(Protocol):
    async def add_segment(self, segment: DVRSegmentIndex) -> None: ...

    async def set_live_edge(self, channel_id: UUID, manifest_format: str, sequence_number: int) -> None: ...

    async def prune_before(self, channel_id: UUID, cutoff_epoch: float) -> None: ...


class RedisDVRTimelineStore:
    def __init__(self, client: Redis) -> None:
        self.client = client

    async def add_segment(self, segment: DVRSegmentIndex) -> None:
        await self.client.zadd(
            timeline_key(segment.live_channel_id),
            {json.dumps(segment_payload(segment), separators=(",", ":")): segment.segment_start_at.timestamp()},
        )

    async def set_live_edge(self, channel_id: UUID, manifest_format: str, sequence_number: int) -> None:
        await self.client.set(live_edge_key(channel_id, manifest_format), str(sequence_number))

    async def prune_before(self, channel_id: UUID, cutoff_epoch: float) -> None:
        await self.client.zremrangebyscore(timeline_key(channel_id), "-inf", cutoff_epoch)


class InMemoryDVRTimelineStore:
    def __init__(self) -> None:
        self.segments: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        self.live_edges: dict[tuple[UUID, str], int] = {}

    async def add_segment(self, segment: DVRSegmentIndex) -> None:
        payload = segment_payload(segment)
        bucket = self.segments[segment.live_channel_id]
        bucket[:] = [item for item in bucket if item["id"] != payload["id"]]
        bucket.append(payload)
        bucket.sort(key=lambda item: (item["segment_start_at"], item["sequence_number"]))

    async def set_live_edge(self, channel_id: UUID, manifest_format: str, sequence_number: int) -> None:
        self.live_edges[(channel_id, manifest_format)] = sequence_number

    async def prune_before(self, channel_id: UUID, cutoff_epoch: float) -> None:
        def keep(item: dict[str, Any]) -> bool:
            from datetime import datetime

            return datetime.fromisoformat(str(item["segment_end_at"])).timestamp() >= cutoff_epoch

        self.segments[channel_id] = [item for item in self.segments[channel_id] if keep(item)]

    def export(self, channel_id: UUID) -> Sequence[dict[str, Any]]:
        return tuple(self.segments[channel_id])
