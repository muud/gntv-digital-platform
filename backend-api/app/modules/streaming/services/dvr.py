"""Sprint 6.3 DVR, live time-shift, and catch-up service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from app.modules.streaming.models import DVRSegmentIndex
from app.modules.streaming.repositories.dvr import DVRRepository
from app.modules.streaming.schemas import ApsaraCallbackEvent, DVRSegmentIngestResponse, DVRSegmentResponse
from app.modules.streaming.services.dvr_timeline import DVRTimelineStore

ALLOWED_SEGMENT_EVENTS = {"DVRSegmentCreated", "RecordFileCreated", "RecordComplete"}
HLS_MEDIA_TYPE = "application/vnd.apple.mpegurl"


def normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def build_hls_playlist(segments: list[DVRSegmentIndex], *, endlist: bool) -> str:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    if not segments:
        lines.extend(["#EXT-X-TARGETDURATION:1", "#EXT-X-MEDIA-SEQUENCE:0"])
        if endlist:
            lines.append("#EXT-X-ENDLIST")
        return "\n".join(lines) + "\n"

    target_duration = max(1, int(max(segment.duration_seconds for segment in segments) + 0.999))
    lines.append(f"#EXT-X-TARGETDURATION:{target_duration}")
    lines.append(f"#EXT-X-MEDIA-SEQUENCE:{segments[0].sequence_number}")
    for segment in segments:
        lines.append(f"#EXT-X-PROGRAM-DATE-TIME:{normalize_utc(segment.segment_start_at).isoformat()}")
        lines.append(f"#EXTINF:{segment.duration_seconds:.3f},")
        lines.append(segment.segment_uri)
    if endlist:
        lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


class DVRService:
    def __init__(self, repository: DVRRepository, timeline_store: DVRTimelineStore) -> None:
        self.repository = repository
        self.timeline_store = timeline_store

    async def ingest_apsara_segment(self, payload: ApsaraCallbackEvent) -> DVRSegmentIngestResponse:
        if payload.event_type not in ALLOWED_SEGMENT_EVENTS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "unsupported_apsara_dvr_event"},
            )
        if payload.event_id:
            duplicate = self.repository.segment_by_provider_event_id(payload.event_id)
            if duplicate is not None:
                return DVRSegmentIngestResponse(
                    provider_event_id=payload.event_id,
                    idempotency_outcome="duplicate",
                    correlation_id=str(duplicate.id),
                    segment=DVRSegmentResponse.model_validate(duplicate),
                )

        channel = None
        if payload.live_channel_id is not None:
            channel = self.repository.channel(payload.live_channel_id)
        if channel is None:
            channel = self.repository.channel_by_code(payload.channel_code)
        if channel is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "live_channel_not_found"},
            )
        if not channel.dvr_enabled:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "dvr_not_enabled"},
            )

        start_at = payload.segment_start_at or payload.event_time
        end_at = payload.segment_end_at
        duration = payload.duration_seconds
        if end_at is None and duration is not None:
            end_at = start_at + timedelta(seconds=duration)
        if duration is None and end_at is not None:
            duration = (normalize_utc(end_at) - normalize_utc(start_at)).total_seconds()
        if payload.segment_uri is None or payload.sequence_number is None or end_at is None or duration is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "dvr_segment_payload_incomplete"},
            )

        segment = self.repository.add_segment(
            DVRSegmentIndex(
                live_channel_id=channel.id,
                stream_id=payload.stream_id,
                live_event_id=payload.live_event_id,
                recording_id=payload.recording_id,
                rendition=payload.rendition,
                sequence_number=payload.sequence_number,
                segment_uri=payload.segment_uri,
                segment_start_at=normalize_utc(start_at),
                segment_end_at=normalize_utc(end_at),
                duration_seconds=float(duration),
                provider_event_id=payload.event_id,
                apsara_object_key=payload.recording_object_key,
                metadata_json={
                    "application": payload.application,
                    "stream_identifier": payload.stream_identifier,
                    "payload_version": payload.payload_version,
                    **payload.data,
                },
            )
        )
        await self.timeline_store.add_segment(segment)
        await self.timeline_store.set_live_edge(channel.id, "hls", segment.sequence_number)
        return DVRSegmentIngestResponse(
            provider_event_id=payload.event_id,
            idempotency_outcome="accepted",
            correlation_id=str(uuid4()),
            segment=DVRSegmentResponse.model_validate(segment),
        )

    def live_dvr_manifest(
        self,
        channel_id: UUID,
        *,
        time_shift_seconds: int = 0,
        rendition: str = "source",
        now: datetime | None = None,
    ) -> str:
        channel = self.repository.channel(channel_id)
        if channel is None or not channel.is_public:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "channel_not_found"})
        if not channel.dvr_enabled:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "dvr_not_enabled"})
        if time_shift_seconds < 0 or time_shift_seconds > channel.dvr_window_seconds:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "time_shift_outside_dvr_window"},
            )

        edge = normalize_utc(now or datetime.now(UTC)) - timedelta(seconds=time_shift_seconds)
        start_at = edge - timedelta(seconds=max(30, min(channel.dvr_window_seconds, 300)))
        segments = list(
            self.repository.segments_for_channel_window(
                channel.id,
                start_at=start_at,
                end_at=edge + timedelta(seconds=1),
                rendition=rendition,
            )
        )
        return build_hls_playlist(segments, endlist=False)

    def catchup_playlist(self, live_event_id: UUID, *, rendition: str = "source") -> str:
        event = self.repository.live_event(live_event_id)
        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "live_event_not_found"})
        channel = self.repository.channel(event.live_channel_id)
        if channel is None or not channel.dvr_enabled:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "catchup_not_available"})
        recording = self.repository.recording_for_event(live_event_id)
        if recording is None:
            start_at = normalize_utc(event.actual_start_at or event.scheduled_start_at)
            end_at = normalize_utc(event.actual_end_at or event.scheduled_end_at)
            segments = list(
                self.repository.segments_for_channel_window(
                    channel.id,
                    start_at=start_at,
                    end_at=end_at,
                    rendition=rendition,
                    limit=5000,
                )
            )
        else:
            segments = list(self.repository.segments_for_recording(recording, rendition=rendition))
        return build_hls_playlist(segments, endlist=True)

    async def prune_retention(self, channel_id: UUID, *, now: datetime | None = None) -> int:
        channel = self.repository.channel(channel_id)
        if channel is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "channel_not_found"})
        cutoff = normalize_utc(now or datetime.now(UTC)) - timedelta(days=channel.catchup_retention_days)
        count = self.repository.mark_pruned_before(channel.id, cutoff)
        await self.timeline_store.prune_before(channel.id, cutoff.timestamp())
        return count
