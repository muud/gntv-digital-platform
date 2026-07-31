"""Authorised multilingual production API for Sheeko Xariiro Voice Studio."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import AsyncIterator
from pathlib import Path
from time import monotonic
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.modules.editorial.api import access
from app.modules.editorial.tts.api import TTSProviderRouter
from app.modules.editorial.tts.providers import LANGUAGE_BY_UI_CODE
from app.modules.editorial.tts.schemas import UILanguageCode
from app.modules.editorial.tts.service import TTSServiceError
from app.modules.sheeko_xariiro.models import (
    SheekoAudioAsset,
    SheekoGenerationAudit,
    SheekoVoicePreset,
)
from app.modules.sheeko_xariiro.schemas import (
    AudioAssetResponse,
    EpisodeCreate,
    EpisodeResponse,
    LanguageVersionResponse,
    LanguageVersionUpdate,
    VoiceGenerateRequest,
    VoicePresetResponse,
    VoicePresetUpsert,
)
from app.modules.sheeko_xariiro.service import (
    SheekoError,
    SheekoXariiroService,
    production_filename,
    subtitle_vtt,
)

router = APIRouter(
    prefix="/api/v1/sheeko-xariiro",
    tags=["Sheeko Xariiro Voice Studio"],
)
Producer = Annotated[User, Depends(access(write=True))]
Database = Annotated[Session, Depends(get_db)]
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
_generation_windows: dict[int, deque[float]] = defaultdict(deque)


def fail(exc: SheekoError | TTSServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    )


def response_for(service: SheekoXariiroService, episode_id: UUID) -> EpisodeResponse:
    episode = service.require_episode(episode_id)
    payload = EpisodeResponse.model_validate(
        {
            "id": episode.id,
            "episode_title": episode.episode_title,
            "slug": episode.slug,
            "original_script": episode.original_script,
            "status": episode.status,
            "multilingual_complete": service.multilingual_complete(episode),
            "languages": episode.languages,
            "created_at": episode.created_at,
            "updated_at": episode.updated_at,
        }
    )
    return payload


def enforce_generation_rate(user_id: int) -> None:
    now = monotonic()
    window = _generation_windows[user_id]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= 10:
        raise SheekoError(
            429,
            "generation_rate_limited",
            "Wait before submitting another paid generation.",
        )
    window.append(now)


@router.get("/voice-presets", response_model=list[VoicePresetResponse])
def list_voice_presets(
    user: Producer,
    db: Database,
    language: UILanguageCode | None = None,
) -> list[VoicePresetResponse]:
    del user
    query = select(SheekoVoicePreset).where(SheekoVoicePreset.active.is_(True))
    if language:
        query = query.where(SheekoVoicePreset.language_code == language)
    return [
        VoicePresetResponse.model_validate(row)
        for row in db.scalars(query.order_by(SheekoVoicePreset.preset_name)).all()
    ]


@router.put("/voice-presets", response_model=VoicePresetResponse)
def configure_voice_preset(
    payload: VoicePresetUpsert,
    user: Producer,
    db: Database,
) -> VoicePresetResponse:
    if "admin" not in user.role_names:
        raise HTTPException(
            403,
            detail={
                "code": "voice_preset_admin_required",
                "message": "Only a GNTV administrator can configure approved voices.",
            },
        )
    if payload.provider.lower() == "elevenlabs" and payload.language_code not in {
        "so",
        "sw",
    }:
        raise HTTPException(
            422,
            detail={
                "code": "unverified_elevenlabs_language",
                "message": "ElevenLabs is not verified for this language.",
            },
        )
    preset = db.scalar(
        select(SheekoVoicePreset).where(
            SheekoVoicePreset.preset_name == payload.preset_name,
            SheekoVoicePreset.language_code == payload.language_code,
        )
    )
    values = payload.model_dump()
    if preset:
        for field, value in values.items():
            setattr(preset, field, value)
    else:
        preset = SheekoVoicePreset(**values)
        db.add(preset)
    db.flush()
    return VoicePresetResponse.model_validate(preset)


@router.post("/episodes", response_model=EpisodeResponse, status_code=201)
def create_episode(payload: EpisodeCreate, user: Producer, db: Database) -> EpisodeResponse:
    service = SheekoXariiroService(db)
    try:
        episode = service.create_episode(payload, user.id)
        return response_for(service, episode.id)
    except SheekoError as exc:
        raise fail(exc) from None


@router.get("/episodes/{episode_id}", response_model=EpisodeResponse)
def get_episode(episode_id: UUID, user: Producer, db: Database) -> EpisodeResponse:
    del user
    service = SheekoXariiroService(db)
    try:
        return response_for(service, episode_id)
    except SheekoError as exc:
        raise fail(exc) from None


@router.patch(
    "/episodes/{episode_id}/languages/{language}",
    response_model=LanguageVersionResponse,
)
def update_language(
    episode_id: UUID,
    language: UILanguageCode,
    payload: LanguageVersionUpdate,
    user: Producer,
    db: Database,
) -> LanguageVersionResponse:
    service = SheekoXariiroService(db)
    try:
        return LanguageVersionResponse.model_validate(
            service.update_language(episode_id, language, payload, user.id)
        )
    except SheekoError as exc:
        raise fail(exc) from None


@router.post("/episodes/{episode_id}/languages/{language}/preview")
async def preview_voice(
    episode_id: UUID,
    language: UILanguageCode,
    payload: VoiceGenerateRequest,
    user: Producer,
    db: Database,
    providers: TTSProviderRouter,
) -> StreamingResponse:
    try:
        SheekoXariiroService(db).require_language(episode_id, language)
        provider = providers.provider_for(language)
        audio = await provider.preview_speech(
            text=payload.text,
            voice=payload.voice_id,
            language=language,
        )
    except (SheekoError, TTSServiceError) as exc:
        raise fail(exc) from None

    async def chunks() -> AsyncIterator[bytes]:
        try:
            async for chunk in audio.chunks():
                yield chunk
        finally:
            await audio.close()

    return StreamingResponse(
        chunks(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/episodes/{episode_id}/languages/{language}/generate",
    response_model=AudioAssetResponse,
    status_code=201,
)
async def generate_voice(
    episode_id: UUID,
    language: UILanguageCode,
    payload: VoiceGenerateRequest,
    user: Producer,
    db: Database,
    providers: TTSProviderRouter,
) -> AudioAssetResponse:
    service = SheekoXariiroService(db)
    try:
        language_version = service.require_language(episode_id, language)
        service.require_unique_generation(payload.idempotency_key)
        enforce_generation_rate(user.id)
        provider = providers.provider_for(language)
        audit = SheekoGenerationAudit(
            episode_id=episode_id,
            language_code=language,
            requested_by=user.id,
            idempotency_key=payload.idempotency_key,
            provider=provider.provider_name,
            character_count=len(payload.text),
            status="started",
        )
        db.add(audit)
        db.flush()
        audio = await provider.generate_speech(
            text=payload.text,
            voice=payload.voice_id,
            language=language,
        )
        try:
            data = b"".join([chunk async for chunk in audio.chunks()])
        finally:
            await audio.close()
        if not data:
            raise SheekoError(502, "empty_audio", "The voice provider returned empty audio.")
        version = service.next_audio_version(
            language_version.id, payload.scene_number, payload.character_name
        )
        episode = service.require_episode(episode_id)
        filename = production_filename(
            episode_slug=episode.slug,
            scene_number=payload.scene_number,
            character_name=payload.character_name,
            language=language,
            version=version,
            extension="mp3",
        )
        service.store_audio(Path(settings.MEDIA_LOCAL_ROOT), filename, data)
        asset = SheekoAudioAsset(
            language_version_id=language_version.id,
            scene_number=payload.scene_number,
            character_name=payload.character_name,
            source="generated",
            provider=provider.provider_name,
            voice_id=payload.voice_id,
            model_id=LANGUAGE_BY_UI_CODE[language].model_id,
            filename=filename,
            media_url="pending",
            content_type="audio/mpeg",
            version=version,
            character_count=len(payload.text),
            created_by=user.id,
        )
        db.add(asset)
        db.flush()
        media_url = f"/api/v1/sheeko-xariiro/audio/{asset.id}"
        asset.media_url = media_url
        language_version.generated_audio_url = media_url
        audit.status = "completed"
        db.flush()
        return AudioAssetResponse.model_validate(asset)
    except (SheekoError, TTSServiceError) as exc:
        raise fail(exc) from None


@router.post(
    "/episodes/{episode_id}/languages/{language}/audio-upload",
    response_model=AudioAssetResponse,
    status_code=201,
)
async def upload_approved_audio(
    episode_id: UUID,
    language: UILanguageCode,
    user: Producer,
    db: Database,
    character_name: str,
    scene_number: int = 1,
    audio: UploadFile = File(...),
) -> AudioAssetResponse:
    allowed = {
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
    }
    extension = allowed.get((audio.content_type or "").lower())
    if not extension:
        raise HTTPException(
            415,
            detail={"code": "unsupported_audio_type", "message": "Upload WAV or MP3 audio."},
        )
    data = await audio.read(MAX_UPLOAD_BYTES + 1)
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            detail={"code": "invalid_audio_size", "message": "Audio must be 1 byte to 50 MB."},
        )
    service = SheekoXariiroService(db)
    try:
        language_version = service.require_language(episode_id, language)
        episode = service.require_episode(episode_id)
        version = service.next_audio_version(
            language_version.id, scene_number, character_name
        )
        filename = production_filename(
            episode_slug=episode.slug,
            scene_number=scene_number,
            character_name=character_name,
            language=language,
            version=version,
            extension=extension,
        )
        service.store_audio(Path(settings.MEDIA_LOCAL_ROOT), filename, data)
        asset = SheekoAudioAsset(
            language_version_id=language_version.id,
            scene_number=scene_number,
            character_name=character_name,
            source="uploaded",
            filename=filename,
            media_url="pending",
            content_type=audio.content_type or "application/octet-stream",
            version=version,
            character_count=0,
            created_by=user.id,
        )
        db.add(asset)
        db.flush()
        media_url = f"/api/v1/sheeko-xariiro/audio/{asset.id}"
        asset.media_url = media_url
        language_version.generated_audio_url = media_url
        db.flush()
        return AudioAssetResponse.model_validate(asset)
    except SheekoError as exc:
        raise fail(exc) from None


@router.get("/episodes/{episode_id}/languages/{language}/subtitles")
def export_subtitles(
    episode_id: UUID,
    language: UILanguageCode,
    user: Producer,
    db: Database,
) -> PlainTextResponse:
    del user
    service = SheekoXariiroService(db)
    try:
        version = service.require_language(episode_id, language)
        episode = service.require_episode(episode_id)
    except SheekoError as exc:
        raise fail(exc) from None
    filename = f"sheeko-xariiro_{episode.slug}_{language}.vtt"
    return PlainTextResponse(
        subtitle_vtt(version.script),
        media_type="text/vtt",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/audio/{asset_id}")
def download_audio(
    asset_id: UUID,
    user: Producer,
    db: Database,
) -> FileResponse:
    del user
    asset = db.scalar(select(SheekoAudioAsset).where(SheekoAudioAsset.id == asset_id))
    if not asset:
        raise HTTPException(
            404,
            detail={"code": "audio_not_found", "message": "Audio asset not found."},
        )
    path = Path(settings.MEDIA_LOCAL_ROOT).resolve() / "sheeko-xariiro" / asset.filename
    if not path.is_file():
        raise HTTPException(
            404,
            detail={"code": "audio_file_missing", "message": "Audio file is unavailable."},
        )
    return FileResponse(
        path,
        media_type=asset.content_type,
        filename=asset.filename,
    )
