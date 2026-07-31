"""Versioned, editorially authorized text-to-speech API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.models.user import User
from app.modules.editorial.api import access
from app.modules.editorial.tts.schemas import (
    LanguageCapabilityResponse,
    SpeechSynthesisRequest,
    TTSErrorResponse,
    UILanguageCode,
    VoiceListResponse,
)
from app.modules.editorial.tts.providers import ElevenLabsProvider, ProviderRouter
from app.modules.editorial.tts.service import ElevenLabsService, TTSServiceError


router = APIRouter(
    prefix="/api/v1/editorial/tts",
    tags=["CMS Editorial Text to Speech"],
)
EditorialTTSUser = Annotated[User, Depends(access(write=True))]

COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {
        "model": TTSErrorResponse,
        "description": "Missing or invalid GNTV bearer access token.",
    },
    status.HTTP_403_FORBIDDEN: {
        "model": TTSErrorResponse,
        "description": "The user lacks editorial write access.",
    },
    status.HTTP_429_TOO_MANY_REQUESTS: {
        "model": TTSErrorResponse,
        "description": "The ElevenLabs account is temporarily rate limited.",
    },
    status.HTTP_502_BAD_GATEWAY: {
        "model": TTSErrorResponse,
        "description": "ElevenLabs authentication, access, or service failure.",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": TTSErrorResponse,
        "description": "Text-to-speech is not configured.",
    },
    status.HTTP_504_GATEWAY_TIMEOUT: {
        "model": TTSErrorResponse,
        "description": "ElevenLabs did not respond before the timeout.",
    },
}
SPEECH_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    **COMMON_ERROR_RESPONSES,
    status.HTTP_400_BAD_REQUEST: {
        "model": TTSErrorResponse,
        "description": "The upstream provider rejected the synthesis request.",
    },
    status.HTTP_402_PAYMENT_REQUIRED: {
        "model": TTSErrorResponse,
        "description": "The ElevenLabs account has insufficient credits.",
    },
    status.HTTP_404_NOT_FOUND: {
        "model": TTSErrorResponse,
        "description": "The selected voice is unavailable.",
    },
}


async def get_elevenlabs_service() -> AsyncIterator[ElevenLabsService]:
    secret = settings.ELEVENLABS_API_KEY
    api_key = secret.get_secret_value() if secret is not None else None
    timeout = httpx.Timeout(30.0, connect=5.0)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
    ) as client:
        yield ElevenLabsService(api_key=api_key, client=client)


TTSService = Annotated[ElevenLabsService, Depends(get_elevenlabs_service)]


def get_provider_router(service: TTSService) -> ProviderRouter:
    return ProviderRouter(elevenlabs=ElevenLabsProvider(service))


TTSProviderRouter = Annotated[ProviderRouter, Depends(get_provider_router)]


def _http_error(exc: TTSServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.safe_message},
    )


@router.get(
    "/voices",
    response_model=VoiceListResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def list_voices(
    user: EditorialTTSUser,
    providers: TTSProviderRouter,
    language: UILanguageCode = "so",
) -> VoiceListResponse:
    del user
    try:
        return await providers.provider_for(language).list_voices(language)
    except TTSServiceError as exc:
        raise _http_error(exc) from None


@router.get("/languages", response_model=LanguageCapabilityResponse)
async def list_language_capabilities(
    user: EditorialTTSUser,
    providers: TTSProviderRouter,
) -> LanguageCapabilityResponse:
    del user
    return LanguageCapabilityResponse(languages=providers.capabilities())


@router.post(
    "/speech",
    response_class=StreamingResponse,
    responses={
        status.HTTP_200_OK: {
            "description": "Generated MP3 audio.",
            "content": {
                "audio/mpeg": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        },
        **SPEECH_ERROR_RESPONSES,
    },
)
async def synthesize_speech(
    payload: SpeechSynthesisRequest,
    user: EditorialTTSUser,
    providers: TTSProviderRouter,
) -> StreamingResponse:
    del user
    try:
        provider = providers.provider_for(payload.language)
        audio = await provider.generate_speech(
            text=payload.text,
            voice=payload.voice_id,
            language=payload.language,
            settings={"output_format": payload.output_format}
            if payload.output_format
            else None,
        )
    except TTSServiceError as exc:
        raise _http_error(exc) from None

    async def stream_audio() -> AsyncIterator[bytes]:
        try:
            async for chunk in audio.chunks():
                yield chunk
        finally:
            await audio.close()

    filename = f"gntv-tts-{uuid4().hex}.mp3"
    return StreamingResponse(
        stream_audio(),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
