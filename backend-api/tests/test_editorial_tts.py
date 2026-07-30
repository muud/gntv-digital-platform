"""Mocked unit and API tests for the ElevenLabs editorial TTS integration."""

import json
from collections.abc import AsyncIterator, Generator
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.dependencies.auth import get_current_user
from app.main import app
from app.models.user import Role, User
from app.modules.editorial.tts.api import get_elevenlabs_service
from app.modules.editorial.tts.schemas import (
    DEFAULT_MODEL_ID,
    DEFAULT_OUTPUT_FORMAT,
    VoiceListResponse,
    VoiceSummary,
)
from app.modules.editorial.tts.service import (
    ElevenLabsService,
    GeneratedAudio,
    TTSServiceError,
)


TEST_API_KEY = "test-only-elevenlabs-key"


def user_with_role(role: str) -> User:
    user = User(
        id=801,
        email=f"{role}@gntv.example",
        hashed_password="unused",
        is_active=True,
        is_verified=True,
    )
    user.roles.append(Role(name=role))
    return user


@pytest.mark.anyio
async def test_service_lists_only_safe_voice_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url == "https://api.elevenlabs.io/v1/voices"
        assert request.headers["xi-api-key"] == TEST_API_KEY
        return httpx.Response(
            200,
            json={
                "voices": [
                    {
                        "voice_id": "voice123",
                        "name": "Newsroom",
                        "category": "professional",
                        "description": "Broadcast voice",
                        "preview_url": "https://example.test/preview.mp3",
                        "labels": {"accent": "East African"},
                        "settings": {"stability": 0.7},
                        "sharing": {"status": "enabled"},
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = ElevenLabsService(api_key=TEST_API_KEY, client=client)
        result = await service.list_voices()

    assert result.model_dump() == {
        "voices": [
            {
                "voice_id": "voice123",
                "name": "Newsroom",
                "category": "professional",
                "description": "Broadcast voice",
                "preview_url": "https://example.test/preview.mp3",
                "labels": {"accent": "East African"},
            }
        ]
    }
    assert "settings" not in result.model_dump_json()
    assert "sharing" not in result.model_dump_json()


@pytest.mark.anyio
async def test_service_synthesizes_with_defaults_and_streams_audio() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"content-type": "audio/mpeg"},
            content=b"ID3mock-audio",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = ElevenLabsService(api_key=TEST_API_KEY, client=client)
        audio = await service.synthesize(text="War wanaagsan.", voice_id="voice123")
        data = b"".join([chunk async for chunk in audio.chunks()])
        await audio.close()

    assert captured["method"] == "POST"
    assert captured["url"].endswith(
        f"/v1/text-to-speech/voice123?output_format={DEFAULT_OUTPUT_FORMAT}"
    )
    assert captured["headers"]["xi-api-key"] == TEST_API_KEY
    assert captured["body"] == {
        "text": "War wanaagsan.",
        "model_id": DEFAULT_MODEL_ID,
    }
    assert data == b"ID3mock-audio"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status_code", "upstream_code", "expected_status", "expected_code"),
    [
        (404, "voice_not_found", 404, "tts_voice_not_found"),
        (402, "insufficient_credits", 402, "tts_insufficient_credits"),
        (401, "quota_exceeded", 402, "tts_insufficient_credits"),
        (401, "invalid_api_key", 502, "tts_upstream_authentication_failed"),
        (403, "voice_access_denied", 502, "tts_upstream_access_denied"),
        (429, "rate_limit_exceeded", 429, "tts_rate_limited"),
        (400, "invalid_parameters", 400, "tts_request_rejected"),
        (500, "internal_error", 502, "tts_upstream_failure"),
    ],
)
async def test_service_maps_upstream_errors_safely(
    status_code: int,
    upstream_code: str,
    expected_status: int,
    expected_code: str,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            request=request,
            json={
                "detail": {
                    "code": upstream_code,
                    "message": "sensitive upstream diagnostic",
                    "request_id": "provider-request-id",
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = ElevenLabsService(api_key=TEST_API_KEY, client=client)
        with pytest.raises(TTSServiceError) as captured:
            await service.synthesize(text="Test", voice_id="voice123")

    assert captured.value.status_code == expected_status
    assert captured.value.code == expected_code
    assert "sensitive upstream diagnostic" not in str(captured.value)
    assert "provider-request-id" not in str(captured.value)


@pytest.mark.anyio
async def test_service_handles_missing_configuration_timeout_and_invalid_response() -> None:
    calls = 0

    async def unused_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request, json={"voices": []})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(unused_handler)
    ) as client:
        service = ElevenLabsService(api_key=None, client=client)
        with pytest.raises(TTSServiceError) as missing:
            await service.list_voices()
    assert missing.value.status_code == 503
    assert missing.value.code == "tts_not_configured"
    assert calls == 0

    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("mock timeout", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(timeout_handler)
    ) as client:
        service = ElevenLabsService(api_key=TEST_API_KEY, client=client)
        with pytest.raises(TTSServiceError) as timeout:
            await service.list_voices()
    assert timeout.value.status_code == 504
    assert timeout.value.code == "tts_upstream_timeout"

    async def invalid_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json={"unexpected": []})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(invalid_handler)
    ) as client:
        service = ElevenLabsService(api_key=TEST_API_KEY, client=client)
        with pytest.raises(TTSServiceError) as invalid:
            await service.list_voices()
    assert invalid.value.status_code == 502
    assert invalid.value.code == "tts_invalid_upstream_response"

    async def non_audio_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "text/html"},
            content=b"<html>not audio</html>",
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(non_audio_handler)
    ) as client:
        service = ElevenLabsService(api_key=TEST_API_KEY, client=client)
        with pytest.raises(TTSServiceError) as non_audio:
            await service.synthesize(text="Test", voice_id="voice123")
    assert non_audio.value.status_code == 502
    assert non_audio.value.code == "tts_invalid_upstream_response"


class FakeAudio:
    def __init__(self) -> None:
        self.closed = False

    async def chunks(self) -> AsyncIterator[bytes]:
        yield b"ID3"
        yield b"api-audio"

    async def close(self) -> None:
        self.closed = True


class FakeTTSService:
    def __init__(self) -> None:
        self.voice_calls = 0
        self.speech_calls: list[dict[str, Any]] = []
        self.audio = FakeAudio()
        self.error: TTSServiceError | None = None

    async def list_voices(self) -> VoiceListResponse:
        self.voice_calls += 1
        if self.error:
            raise self.error
        return VoiceListResponse(
            voices=[VoiceSummary(voice_id="voice123", name="Newsroom")]
        )

    async def synthesize(self, **kwargs: Any) -> GeneratedAudio:
        self.speech_calls.append(kwargs)
        if self.error:
            raise self.error
        return self.audio  # type: ignore[return-value]


@pytest.fixture()
def tts_client() -> Generator[tuple[TestClient, FakeTTSService], None, None]:
    service = FakeTTSService()
    app.dependency_overrides[get_current_user] = lambda: user_with_role("admin")
    app.dependency_overrides[get_elevenlabs_service] = lambda: service
    try:
        yield TestClient(app), service
    finally:
        app.dependency_overrides.clear()


def test_tts_api_lists_voices_and_streams_downloadable_mp3(
    tts_client: tuple[TestClient, FakeTTSService],
) -> None:
    client, service = tts_client

    voices = client.get("/api/v1/editorial/tts/voices")
    assert voices.status_code == 200
    assert voices.json()["voices"][0]["voice_id"] == "voice123"

    speech = client.post(
        "/api/v1/editorial/tts/speech",
        json={"text": "Tonight on GNTV.", "voice_id": "voice123"},
    )
    assert speech.status_code == 200
    assert speech.content == b"ID3api-audio"
    assert speech.headers["content-type"].startswith("audio/mpeg")
    assert speech.headers["content-disposition"].startswith(
        'attachment; filename="gntv-tts-'
    )
    assert speech.headers["content-disposition"].endswith('.mp3"')
    assert speech.headers["cache-control"] == "no-store"
    assert service.audio.closed
    assert service.speech_calls == [
        {
            "text": "Tonight on GNTV.",
            "voice_id": "voice123",
            "model_id": "eleven_v3",
            "output_format": None,
        }
    ]


def test_tts_api_validation_rbac_and_safe_errors(
    tts_client: tuple[TestClient, FakeTTSService],
) -> None:
    client, service = tts_client
    endpoint = "/api/v1/editorial/tts/speech"

    for payload in (
        {"text": "   ", "voice_id": "voice123"},
        {"text": "Valid", "voice_id": "   "},
        {"text": "x" * 5_001, "voice_id": "voice123"},
        {
            "text": "Valid",
            "voice_id": "voice123",
            "output_format": "pcm_44100",
        },
    ):
        assert client.post(endpoint, json=payload).status_code == 422
    assert service.speech_calls == []

    app.dependency_overrides[get_current_user] = lambda: user_with_role("viewer")
    assert client.get("/api/v1/editorial/tts/voices").status_code == 403
    assert client.post(
        endpoint,
        json={"text": "Valid", "voice_id": "voice123"},
    ).status_code == 403
    assert service.voice_calls == 0
    assert service.speech_calls == []

    def unauthenticated() -> User:
        raise HTTPException(401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = unauthenticated
    assert client.get("/api/v1/editorial/tts/voices").status_code == 401
    assert service.voice_calls == 0

    app.dependency_overrides[get_current_user] = lambda: user_with_role("admin")
    service.error = TTSServiceError(
        429,
        "tts_rate_limited",
        "Text-to-speech is temporarily rate limited.",
    )
    error = client.get("/api/v1/editorial/tts/voices")
    assert error.status_code == 429
    assert error.json() == {
        "detail": {
            "code": "tts_rate_limited",
            "message": "Text-to-speech is temporarily rate limited.",
        }
    }


def test_tts_openapi_contract_is_authenticated_and_typed() -> None:
    schema = app.openapi()
    voices = schema["paths"]["/api/v1/editorial/tts/voices"]["get"]
    speech = schema["paths"]["/api/v1/editorial/tts/speech"]["post"]

    assert voices["security"] == [{"HTTPBearer": []}]
    assert speech["security"] == [{"HTTPBearer": []}]
    assert voices["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/VoiceListResponse"
    }
    assert "audio/mpeg" in speech["responses"]["200"]["content"]
    assert {"400", "401", "402", "403", "404", "429", "502", "503", "504"} <= set(
        speech["responses"]
    )
