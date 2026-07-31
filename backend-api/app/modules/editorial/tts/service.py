"""Safe, mockable ElevenLabs HTTP integration."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from app.modules.editorial.tts.schemas import (
    DEFAULT_MODEL_ID,
    DEFAULT_OUTPUT_FORMAT,
    MP3OutputFormat,
    VoiceListResponse,
    VoiceSummary,
)


ELEVENLABS_BASE_URL = "https://api.elevenlabs.io"


class TTSServiceError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.safe_message = message


@dataclass
class GeneratedAudio:
    """Owned streaming response that must be closed by the API layer."""

    response: httpx.Response

    async def chunks(self) -> AsyncIterator[bytes]:
        async for chunk in self.response.aiter_bytes():
            if chunk:
                yield chunk

    async def close(self) -> None:
        await self.response.aclose()


class ElevenLabsService:
    def __init__(self, *, api_key: str | None, client: httpx.AsyncClient) -> None:
        self._api_key = api_key.strip() if api_key else None
        self._client = client

    def _headers(self, *, accept: str) -> dict[str, str]:
        if not self._api_key:
            raise TTSServiceError(
                503,
                "tts_not_configured",
                "Text-to-speech is not configured.",
            )
        return {
            "xi-api-key": self._api_key,
            "Accept": accept,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _upstream_code(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        detail = payload.get("detail")
        if not isinstance(detail, dict):
            return None
        code = detail.get("code") or detail.get("status")
        return code if isinstance(code, str) else None

    @classmethod
    def _raise_for_upstream(cls, response: httpx.Response) -> None:
        code = cls._upstream_code(response)
        if response.status_code == 404 or code == "voice_not_found":
            raise TTSServiceError(
                404,
                "tts_voice_not_found",
                "The selected voice is unavailable.",
            )
        if response.status_code == 402 or code in {
            "insufficient_credits",
            "quota_exceeded",
        }:
            raise TTSServiceError(
                402,
                "tts_insufficient_credits",
                "Text-to-speech credits are unavailable.",
            )
        if response.status_code == 401 or code in {
            "invalid_api_key",
            "missing_api_key",
            "unauthorized",
        }:
            raise TTSServiceError(
                502,
                "tts_upstream_authentication_failed",
                "The text-to-speech provider could not authenticate.",
            )
        if response.status_code == 403:
            raise TTSServiceError(
                502,
                "tts_upstream_access_denied",
                "The text-to-speech provider denied access.",
            )
        if response.status_code == 429:
            raise TTSServiceError(
                429,
                "tts_rate_limited",
                "Text-to-speech is temporarily rate limited.",
            )
        if response.status_code in {400, 422}:
            raise TTSServiceError(
                400,
                "tts_request_rejected",
                "The text-to-speech provider rejected the request.",
            )
        raise TTSServiceError(
            502,
            "tts_upstream_failure",
            "The text-to-speech provider is unavailable.",
        )

    async def _send(self, request: httpx.Request, *, stream: bool = False) -> httpx.Response:
        try:
            response = await self._client.send(request, stream=stream)
        except httpx.TimeoutException:
            raise TTSServiceError(
                504,
                "tts_upstream_timeout",
                "The text-to-speech provider timed out.",
            ) from None
        except httpx.RequestError:
            raise TTSServiceError(
                502,
                "tts_upstream_unavailable",
                "The text-to-speech provider is unavailable.",
            ) from None
        if not response.is_success:
            try:
                self._raise_for_upstream(response)
            finally:
                await response.aclose()
        return response

    async def list_voices(self) -> VoiceListResponse:
        request = self._client.build_request(
            "GET",
            f"{ELEVENLABS_BASE_URL}/v1/voices",
            headers=self._headers(accept="application/json"),
        )
        response = await self._send(request)
        try:
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("voices"), list):
                raise ValueError("invalid voices payload")
            voices: list[VoiceSummary] = []
            for raw in payload["voices"]:
                if not isinstance(raw, dict):
                    raise ValueError("invalid voice payload")
                labels = raw.get("labels") or {}
                if not isinstance(labels, dict):
                    labels = {}
                voice_id = raw.get("voice_id")
                name = raw.get("name")
                if not isinstance(voice_id, str) or not isinstance(name, str):
                    raise ValueError("invalid voice identity")
                voices.append(
                    VoiceSummary(
                        voice_id=voice_id,
                        name=name,
                        category=raw.get("category"),
                        description=raw.get("description"),
                        preview_url=raw.get("preview_url"),
                        labels={
                            str(key): str(value)
                            for key, value in labels.items()
                        },
                    )
                )
            return VoiceListResponse(voices=voices)
        except (TypeError, ValueError, ValidationError) as exc:
            raise TTSServiceError(
                502,
                "tts_invalid_upstream_response",
                "The text-to-speech provider returned an invalid response.",
            ) from exc
        finally:
            await response.aclose()

    async def synthesize(
        self,
        *,
        text: str,
        voice_id: str,
        model_id: str | None = None,
        output_format: MP3OutputFormat | None = None,
    ) -> GeneratedAudio:
        selected_format = output_format or DEFAULT_OUTPUT_FORMAT
        request = self._client.build_request(
            "POST",
            f"{ELEVENLABS_BASE_URL}/v1/text-to-speech/{voice_id}",
            headers=self._headers(accept="audio/mpeg"),
            params={"output_format": selected_format},
            json={
                "text": text,
                "model_id": model_id or DEFAULT_MODEL_ID,
            },
        )
        response = await self._send(request, stream=True)
        content_type = response.headers.get("content-type", "").lower()
        accepted_types = ("audio/mpeg", "audio/mp3", "application/octet-stream")
        if not content_type.startswith(accepted_types):
            await response.aclose()
            raise TTSServiceError(
                502,
                "tts_invalid_upstream_response",
                "The text-to-speech provider returned an invalid response.",
            )
        return GeneratedAudio(response)
