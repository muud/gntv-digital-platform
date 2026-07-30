"""Strict API contracts for multilingual Sheeko Xariiro production."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.editorial.tts.schemas import MAX_TEXT_LENGTH, UILanguageCode

ReviewStatus = Literal["pending", "in_review", "approved", "changes_requested"]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=False,
    )


class EpisodeCreate(Contract):
    episode_title: str = Field(min_length=1, max_length=240)
    original_script: str = Field(default="", max_length=50_000)


class LanguageVersionUpdate(Contract):
    script: str | None = Field(default=None, max_length=50_000)
    character_assignments: list[dict[str, object]] | None = None
    athero_voice_id: str | None = Field(default=None, max_length=128)
    narrator_voice_id: str | None = Field(default=None, max_length=128)
    character_voices: dict[str, str] | None = None
    pronunciation_notes: str | None = Field(default=None, max_length=10_000)
    translation_review_status: ReviewStatus | None = None
    voice_review_status: ReviewStatus | None = None
    final_approval_status: ReviewStatus | None = None

    @model_validator(mode="after")
    def approved_version_requires_review_approvals(self) -> "LanguageVersionUpdate":
        if self.final_approval_status == "approved" and (
            self.translation_review_status not in {None, "approved"}
            or self.voice_review_status not in {None, "approved"}
        ):
            raise ValueError(
                "Final approval requires approved translation and voice reviews."
            )
        return self


class AudioAssetResponse(Contract):
    id: UUID
    scene_number: int
    character_name: str
    source: str
    provider: str | None
    filename: str
    media_url: str
    content_type: str
    version: int
    character_count: int
    created_at: datetime


class LanguageVersionResponse(Contract):
    id: UUID
    language_code: str
    iso_639_3: str
    script: str
    character_assignments: list[dict[str, object]]
    athero_voice_id: str | None
    narrator_voice_id: str | None
    character_voices: dict[str, str]
    pronunciation_notes: str
    generated_audio_url: str | None
    subtitle_url: str | None
    translation_review_status: str
    voice_review_status: str
    final_approval_status: str
    audio_assets: list[AudioAssetResponse] = Field(default_factory=list)
    updated_at: datetime


class EpisodeResponse(Contract):
    id: UUID
    episode_title: str
    slug: str
    original_script: str
    status: str
    multilingual_complete: bool
    languages: list[LanguageVersionResponse]
    created_at: datetime
    updated_at: datetime


class VoiceGenerateRequest(Contract):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    voice_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    character_name: str = Field(min_length=1, max_length=120)
    scene_number: int = Field(default=1, ge=1, le=9_999)
    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )


class SubtitleExportResponse(Contract):
    language: UILanguageCode
    filename: str
    content: str


class VoicePresetUpsert(Contract):
    preset_name: str = Field(min_length=1, max_length=80)
    character_name: str = Field(min_length=1, max_length=120)
    language_code: UILanguageCode
    provider: str = Field(min_length=1, max_length=64)
    voice_id: str = Field(min_length=1, max_length=128)
    model_id: str = Field(min_length=1, max_length=128)
    settings: dict[str, object] = Field(default_factory=dict)
    active: bool = True


class VoicePresetResponse(VoicePresetUpsert):
    id: UUID
    created_at: datetime
