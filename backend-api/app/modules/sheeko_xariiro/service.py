"""Business rules for multilingual review, safe naming, and audio persistence."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.modules.editorial.tts.providers import LANGUAGE_BY_UI_CODE
from app.modules.editorial.tts.schemas import UILanguageCode
from app.modules.sheeko_xariiro.models import (
    SheekoAudioAsset,
    SheekoGenerationAudit,
    SheekoLanguageVersion,
    SheekoXariiroEpisode,
)
from app.modules.sheeko_xariiro.schemas import EpisodeCreate, LanguageVersionUpdate


class SheekoError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def safe_slug(value: str, fallback: str = "episode") -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug[:180] or fallback


def production_filename(
    *,
    episode_slug: str,
    scene_number: int,
    character_name: str,
    language: UILanguageCode,
    version: int,
    extension: str,
) -> str:
    character = safe_slug(character_name, "character")
    return (
        f"sheeko-xariiro_{episode_slug}_{scene_number:02d}_{character}_"
        f"{language}_v{version}.{extension}"
    )


def subtitle_vtt(script: str) -> str:
    text = script.strip() or "[Script pending]"
    return f"WEBVTT\n\n00:00:00.000 --> 00:00:05.000\n{text}\n"


class SheekoXariiroService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_episode(self, payload: EpisodeCreate, user_id: int) -> SheekoXariiroEpisode:
        base_slug = safe_slug(payload.episode_title)
        slug = base_slug
        counter = 2
        while self.db.scalar(
            select(SheekoXariiroEpisode.id).where(SheekoXariiroEpisode.slug == slug)
        ):
            slug = f"{base_slug}-{counter}"
            counter += 1
        episode = SheekoXariiroEpisode(
            episode_title=payload.episode_title,
            slug=slug,
            original_script=payload.original_script,
            created_by=user_id,
        )
        for code, language in LANGUAGE_BY_UI_CODE.items():
            episode.languages.append(
                SheekoLanguageVersion(
                    language_code=code,
                    iso_639_3=language.iso_639_3,
                )
            )
        self.db.add(episode)
        self.db.flush()
        return self.require_episode(episode.id)

    def require_episode(self, episode_id: UUID) -> SheekoXariiroEpisode:
        episode = self.db.scalar(
            select(SheekoXariiroEpisode)
            .options(
                selectinload(SheekoXariiroEpisode.languages).selectinload(
                    SheekoLanguageVersion.audio_assets
                )
            )
            .where(SheekoXariiroEpisode.id == episode_id)
        )
        if not episode:
            raise SheekoError(404, "sheeko_episode_not_found", "Episode not found.")
        return episode

    def require_language(
        self, episode_id: UUID, language: UILanguageCode
    ) -> SheekoLanguageVersion:
        version = self.db.scalar(
            select(SheekoLanguageVersion)
            .options(selectinload(SheekoLanguageVersion.audio_assets))
            .where(
                SheekoLanguageVersion.episode_id == episode_id,
                SheekoLanguageVersion.language_code == language,
            )
        )
        if not version:
            raise SheekoError(
                404, "sheeko_language_not_found", "Episode language version not found."
            )
        return version

    def update_language(
        self,
        episode_id: UUID,
        language: UILanguageCode,
        payload: LanguageVersionUpdate,
        user_id: int,
    ) -> SheekoLanguageVersion:
        version = self.require_language(episode_id, language)
        changes = payload.model_dump(exclude_unset=True)
        requested_script = changes.get("script")
        if (
            requested_script is not None
            and requested_script != version.script
            and version.translation_review_status == "approved"
        ):
            raise SheekoError(
                409,
                "approved_script_locked",
                "An approved script cannot be overwritten. Return it to review first.",
            )
        final_status = changes.get("final_approval_status")
        translation_status = changes.get(
            "translation_review_status", version.translation_review_status
        )
        voice_status = changes.get("voice_review_status", version.voice_review_status)
        if final_status == "approved" and (
            translation_status != "approved" or voice_status != "approved"
        ):
            raise SheekoError(
                409,
                "reviews_not_approved",
                "Translation and voice reviews must be approved first.",
            )
        for field, value in changes.items():
            setattr(version, field, value)
        if changes.get("translation_review_status") == "approved":
            version.reviewed_by = user_id
        if final_status == "approved":
            version.approved_by = user_id
        self.db.flush()
        return version

    @staticmethod
    def multilingual_complete(episode: SheekoXariiroEpisode) -> bool:
        required = set(LANGUAGE_BY_UI_CODE)
        approved = {
            version.language_code
            for version in episode.languages
            if version.final_approval_status == "approved"
        }
        return approved == required

    def next_audio_version(
        self, language_version_id: UUID, scene_number: int, character_name: str
    ) -> int:
        assets = self.db.scalars(
            select(SheekoAudioAsset).where(
                SheekoAudioAsset.language_version_id == language_version_id,
                SheekoAudioAsset.scene_number == scene_number,
                SheekoAudioAsset.character_name == character_name,
            )
        ).all()
        return max((asset.version for asset in assets), default=0) + 1

    def require_unique_generation(self, idempotency_key: str) -> None:
        if self.db.scalar(
            select(SheekoGenerationAudit.id).where(
                SheekoGenerationAudit.idempotency_key == idempotency_key
            )
        ):
            raise SheekoError(
                409,
                "duplicate_generation",
                "This generation request has already been submitted.",
            )

    @staticmethod
    def store_audio(root: Path, filename: str, data: bytes) -> Path:
        target_dir = root.resolve() / "sheeko-xariiro"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        target.write_bytes(data)
        return target
