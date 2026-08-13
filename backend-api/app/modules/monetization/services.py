"""SSAI manifest stitching, FAST packaging, and signed tracking beacons."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
from uuid import UUID

from fastapi import HTTPException, status

from app.core.config import settings
from app.models.user import User
from app.modules.monetization.models import (
    AdBreak,
    AdCampaign,
    AdCreative,
    AdImpression,
    AdImpressionEventType,
    AdTrackingEvent,
    TrackingEventStatus,
)
from app.modules.monetization.repository import MonetizationRepository
from app.modules.monetization.schemas import (
    AdBreakCreateRequest,
    AdCampaignCreateRequest,
    AdCreativeCreateRequest,
    TrackingBeaconRequest,
    TrackingBeaconResponse,
)

HLS_MEDIA_TYPE = "application/vnd.apple.mpegurl"


@dataclass(frozen=True)
class HlsSegment:
    uri: str
    duration_seconds: float
    kind: str = "content"


def user_can_manage_campaign(user: User, campaign: AdCampaign | None = None) -> bool:
    roles = set(user.role_names)
    if roles & {"admin", "chief_editor", "producer"} or "*" in user.permission_names or "monetization:write" in user.permission_names:
        return True
    return campaign is not None and campaign.owner_user_id == user.id


def user_can_read_campaign(user: User, campaign: AdCampaign | None) -> bool:
    return user_can_manage_campaign(user, campaign) or "monetization:read" in user.permission_names


def sign_beacon_payload(*, idempotency_key: str, session_id: str, event_type: str) -> str:
    secret = settings.PLAYBACK_SIGNING_SECRET.get_secret_value()
    payload = f"{idempotency_key}:{session_id}:{event_type}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def event_value(event_type: AdImpressionEventType | str) -> str:
    return event_type.value if isinstance(event_type, AdImpressionEventType) else str(event_type)


def _default_content_segments(target_id: str) -> list[HlsSegment]:
    return [
        HlsSegment(uri=f"https://stream.gntv.example/fast/{target_id}/content-{index}.ts", duration_seconds=6.0)
        for index in range(10)
    ]


def build_ssai_manifest(
    *,
    target_id: str,
    content_segments: list[HlsSegment],
    breaks: list[tuple[AdBreak, list[AdCreative]]],
) -> str:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    all_durations = [segment.duration_seconds for segment in content_segments]
    all_durations.extend(creative.duration_seconds for _break, creatives in breaks for creative in creatives)
    target_duration = max(1, int(max(all_durations or [6.0]) + 0.999))
    lines.append(f"#EXT-X-TARGETDURATION:{target_duration}")
    lines.append("#EXT-X-MEDIA-SEQUENCE:0")
    break_by_segment = {int(ad_break.time_offset_seconds // 6): (ad_break, creatives) for ad_break, creatives in breaks}

    for index, segment in enumerate(content_segments):
        if index in break_by_segment:
            ad_break, creatives = break_by_segment[index]
            lines.append("#EXT-X-DISCONTINUITY")
            lines.append(
                '#EXT-X-DATERANGE:ID="ad-{id}",CLASS="gntv-ad-break",START-DATE="{start}",'
                'PLANNED-DURATION={duration:.3f},X-GNTV-TARGET="{target}"'.format(
                    id=ad_break.id,
                    start=datetime.now(UTC).isoformat(),
                    duration=ad_break.duration_seconds,
                    target=target_id,
                )
            )
            for creative in creatives:
                lines.append(f"#EXTINF:{creative.duration_seconds:.3f},")
                lines.append(creative.media_url)
            lines.append("#EXT-X-DISCONTINUITY")
        lines.append(f"#EXTINF:{segment.duration_seconds:.3f},")
        lines.append(segment.uri)
    return "\n".join(lines) + "\n"


class MonetizationService:
    def __init__(self, repository: MonetizationRepository) -> None:
        self.repository = repository

    def create_campaign(self, payload: AdCampaignCreateRequest, user: User) -> AdCampaign:
        if not user_can_manage_campaign(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "campaign_create_forbidden"})
        campaign = AdCampaign(
            owner_user_id=user.id,
            name=payload.name,
            status=payload.status,
            vast_tag_url=payload.vast_tag_url,
            vmap_tag_url=payload.vmap_tag_url,
            start_at=payload.start_at,
            end_at=payload.end_at,
        )
        return self.repository.add_campaign(campaign)

    def get_campaign(self, campaign_id: UUID | str, user: User) -> AdCampaign:
        campaign = self.repository.campaign(UUID(str(campaign_id)))
        if campaign is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "campaign_not_found"})
        if not user_can_read_campaign(user, campaign):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "campaign_read_forbidden"})
        return campaign

    def list_campaigns(self, user: User) -> list[AdCampaign]:
        campaigns = self.repository.list_campaigns()
        return [c for c in campaigns if user_can_read_campaign(user, c)]

    def create_creative(self, payload: AdCreativeCreateRequest, user: User) -> AdCreative:
        if payload.campaign_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "campaign_id_required"})
        campaign = self.repository.campaign(payload.campaign_id)
        if campaign is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "campaign_not_found"})
        if not user_can_manage_campaign(user, campaign):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "campaign_write_forbidden"})
        return self.repository.add_creative(
            AdCreative(
                campaign_id=payload.campaign_id,
                name=payload.name,
                creative_type=payload.creative_type,
                media_url=payload.media_url,
                duration_seconds=payload.duration_seconds,
                mime_type=payload.mime_type,
            )
        )

    def create_break(self, payload: AdBreakCreateRequest, user: User) -> AdBreak:
        campaign = self.repository.campaign(payload.campaign_id) if payload.campaign_id else None
        if payload.campaign_id is not None and campaign is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "campaign_not_found"})
        if not user_can_manage_campaign(user, campaign):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "campaign_write_forbidden"})
        return self.repository.add_break(
            AdBreak(
                campaign_id=payload.campaign_id,
                target_id=payload.target_id,
                break_type=payload.break_type,
                time_offset_seconds=payload.time_offset_seconds,
                duration_seconds=payload.duration_seconds,
                scte35_event_id=payload.scte35_event_id,
                scte35_cue=payload.scte35_cue,
            )
        )

    def ssai_manifest(self, target_id: str) -> str:
        ad_breaks = self.repository.breaks_for_target(target_id)
        resolved: list[tuple[AdBreak, list[AdCreative]]] = []
        for ad_break in ad_breaks:
            creatives = self.repository.creatives_for_campaign(ad_break.campaign_id) if ad_break.campaign_id else []
            if creatives:
                resolved.append((ad_break, creatives))
        return build_ssai_manifest(target_id=target_id, content_segments=_default_content_segments(target_id), breaks=resolved)

    def generate_ssai_manifest_for_target(self, target_id: str) -> str:
        return self.ssai_manifest(target_id)

    def record_beacon(self, payload: TrackingBeaconRequest, user: User | None = None) -> TrackingBeaconResponse:
        expected_signature = sign_beacon_payload(
            idempotency_key=payload.idempotency_key,
            session_id=payload.session_id,
            event_type=event_value(payload.event_type),
        )
        if not hmac.compare_digest(payload.signature, expected_signature):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "invalid_tracking_signature"})

        existing = self.repository.impression_by_idempotency_key(payload.idempotency_key)
        if existing is not None:
            event = self.repository.add_tracking_event(
                AdTrackingEvent(
                    impression_id=existing.id,
                    event_type=payload.event_type,
                    tracking_url=payload.tracking_url,
                    signature=payload.signature,
                    status=TrackingEventStatus.DUPLICATE,
                )
            )
            return TrackingBeaconResponse(
                impression_id=existing.id,
                event_id=event.id,
                status=TrackingEventStatus.DUPLICATE,
                idempotency_outcome="duplicate",
            )

        impression = self.repository.add_impression(
            AdImpression(
                campaign_id=UUID(str(payload.campaign_id)) if payload.campaign_id else None,
                creative_id=UUID(str(payload.creative_id)) if payload.creative_id else None,
                break_id=UUID(str(payload.break_id)) if payload.break_id else None,
                session_id=payload.session_id,
                user_id=user.id if user else None,
                event_type=payload.event_type,
                idempotency_key=payload.idempotency_key,
            )
        )
        event = self.repository.add_tracking_event(
            AdTrackingEvent(
                impression_id=impression.id,
                event_type=payload.event_type,
                tracking_url=payload.tracking_url,
                signature=payload.signature,
                status=TrackingEventStatus.ACCEPTED,
            )
        )
        return TrackingBeaconResponse(
            impression_id=impression.id,
            event_id=event.id,
            status=TrackingEventStatus.ACCEPTED,
            idempotency_outcome="accepted",
        )

    process_beacon = record_beacon
