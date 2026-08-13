"""API contracts for SSAI, FAST packaging, and ad tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.monetization.models import AdBreakType, AdCampaignStatus, AdCreativeType, AdImpressionEventType, TrackingEventStatus


class MonetizationContract(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class AdCampaignCreateRequest(MonetizationContract):
    name: str = Field(min_length=1, max_length=160)
    status: AdCampaignStatus = AdCampaignStatus.ACTIVE
    vast_tag_url: str | None = Field(default=None, max_length=1024)
    vmap_tag_url: str | None = Field(default=None, max_length=1024)
    start_at: datetime | None = None
    end_at: datetime | None = None


class AdCampaignResponse(MonetizationContract):
    id: UUID
    owner_user_id: int | None
    name: str
    status: AdCampaignStatus
    vast_tag_url: str | None
    vmap_tag_url: str | None
    created_at: datetime
    updated_at: datetime


class AdCreativeCreateRequest(MonetizationContract):
    campaign_id: UUID | None = None
    name: str = Field(min_length=1, max_length=160)
    creative_type: AdCreativeType = AdCreativeType.VIDEO
    media_url: str = Field(min_length=1, max_length=2048)
    duration_seconds: float = Field(gt=0)
    mime_type: str = Field(default="video/mp2t", max_length=100)


class AdCreativeResponse(MonetizationContract):
    id: UUID
    campaign_id: UUID
    name: str
    creative_type: AdCreativeType
    media_url: str
    duration_seconds: float
    mime_type: str


class AdBreakCreateRequest(MonetizationContract):
    campaign_id: UUID | None = None
    target_id: str = Field(min_length=1, max_length=160)
    break_type: AdBreakType = AdBreakType.MIDROLL
    time_offset_seconds: float = Field(default=0, ge=0)
    duration_seconds: float = Field(gt=0)
    scte35_event_id: str | None = Field(default=None, max_length=120)
    scte35_cue: str | None = None


class AdBreakResponse(MonetizationContract):
    id: UUID
    campaign_id: UUID | None
    target_id: str
    break_type: AdBreakType
    time_offset_seconds: float
    duration_seconds: float
    scte35_event_id: str | None
    scte35_cue: str | None


class TrackingBeaconRequest(MonetizationContract):
    campaign_id: UUID | str | None = None
    creative_id: UUID | str | None = None
    break_id: UUID | str | None = None
    session_id: str = Field(min_length=1, max_length=128)
    event_type: AdImpressionEventType
    idempotency_key: str = Field(min_length=8, max_length=160)
    signature: str = Field(min_length=16, max_length=128)
    tracking_url: str | None = Field(default=None, max_length=2048)


class TrackingBeaconResponse(MonetizationContract):
    impression_id: UUID | str
    event_id: UUID | str | None = None
    status: TrackingEventStatus | str = "accepted"
    idempotency_outcome: Literal["accepted", "duplicate"] | str = "accepted"
    recorded_at: datetime | None = None


AdBeaconRequest = TrackingBeaconRequest
AdBeaconResponse = TrackingBeaconResponse


class VastMediaFile(MonetizationContract):
    url: str
    delivery: str | None = None
    type: str | None = None
    bitrate: int | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None


VASTMediaFile = VastMediaFile


class VastTrackingUrl(MonetizationContract):
    event: str
    url: str


VASTTrackingUrl = VastTrackingUrl


class VastCreative(MonetizationContract):
    ad_id: str = "ad_1"
    title: str = ""
    duration_seconds: float = 15.0
    media_files: list[VastMediaFile] = Field(default_factory=list)
    impression_urls: list[str] = Field(default_factory=list)
    tracking_urls: list[VastTrackingUrl] = Field(default_factory=list)
    impressions: list[str] = Field(default_factory=list)
    tracking: dict[str, list[str]] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


VASTAdData = VastCreative


class VMAPAdBreakData(MonetizationContract):
    break_id: str
    time_offset: str
    break_type: str = "linear"
    vast_ad: VASTAdData | None = None
    vast_ad_data: str | None = None
    ad_tag_uri: str | None = None


VmapAdBreak = VMAPAdBreakData


class Scte35Cue(MonetizationContract):
    cue_type: Literal["cue-out", "cue-in"]
    event_id: str
    duration_seconds: float | None = Field(default=None, ge=0)

    @field_validator("event_id")
    @classmethod
    def event_id_not_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("event_id cannot be empty")
        return normalized
