"""Five-language Sheeko Xariiro workflow and provider safety tests."""

from collections.abc import AsyncIterator, Generator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.user import Role, User
from app.modules.editorial.tts.providers import (
    LANGUAGE_BY_UI_CODE,
    LANGUAGES,
    ElevenLabsProvider,
    ProviderRouter,
    TextToSpeechProvider,
)
from app.modules.editorial.tts.schemas import DEFAULT_MODEL_ID, VoiceListResponse
from app.modules.editorial.tts.service import ElevenLabsService, TTSServiceError
from app.modules.sheeko_xariiro.models import (
    SheekoAudioAsset,
    SheekoGenerationAudit,
    SheekoLanguageVersion,
    SheekoVoicePreset,
    SheekoXariiroEpisode,
)
from app.modules.sheeko_xariiro.schemas import EpisodeCreate, LanguageVersionUpdate
from app.modules.sheeko_xariiro.service import (
    SheekoError,
    SheekoXariiroService,
    production_filename,
    subtitle_vtt,
)


class MemoryAudio:
    async def chunks(self) -> AsyncIterator[bytes]:
        yield b"ID3mock"

    async def close(self) -> None:
        return None


class LicensedAfarAdapter(TextToSpeechProvider):
    provider_name = "configured-licensed-adapter"

    def check_language_support(self, language: str) -> bool:
        return language == "aa"

    async def list_voices(self, language: str) -> VoiceListResponse:
        return VoiceListResponse(voices=[])

    async def generate_speech(
        self,
        *,
        text: str,
        voice: str,
        language: str,
        settings: dict[str, object] | None = None,
    ) -> MemoryAudio:
        del text, voice, language, settings
        return MemoryAudio()


@pytest.fixture()
def sheeko_db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables: list[Table] = [
        User.__table__,
        SheekoXariiroEpisode.__table__,
        SheekoLanguageVersion.__table__,
        SheekoAudioAsset.__table__,
        SheekoVoicePreset.__table__,
        SheekoGenerationAudit.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = local()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine, tables=reversed(tables))
        engine.dispose()


def authorised_user() -> User:
    user = User(
        id=901,
        email="producer@gntv.example",
        hashed_password="unused",
        is_active=True,
        is_verified=True,
    )
    user.roles.append(Role(name="admin"))
    return user


def test_all_five_language_codes_are_exact_and_permanent() -> None:
    assert [language.ui_code for language in LANGUAGES] == ["aa", "am", "om", "so", "sw"]
    assert [language.iso_639_3 for language in LANGUAGES] == [
        "aar",
        "amh",
        "orm",
        "som",
        "swa",
    ]
    assert LANGUAGE_BY_UI_CODE["am"].native_name == "አማርኛ"


def test_episode_creates_independent_scripts_audio_and_completion(
    sheeko_db: Session,
) -> None:
    service = SheekoXariiroService(sheeko_db)
    episode = service.create_episode(
        EpisodeCreate(episode_title="Diin iyo Bakayle", original_script="Source"),
        user_id=901,
    )
    assert {row.language_code for row in episode.languages} == {"aa", "am", "om", "so", "sw"}

    service.update_language(
        episode.id,
        "so",
        LanguageVersionUpdate(script="Sheekada Soomaaliga"),
        901,
    )
    service.update_language(
        episode.id,
        "sw",
        LanguageVersionUpdate(script="Hadithi ya Kiswahili"),
        901,
    )
    assert service.require_language(episode.id, "so").script == "Sheekada Soomaaliga"
    assert service.require_language(episode.id, "sw").script == "Hadithi ya Kiswahili"
    assert not service.multilingual_complete(service.require_episode(episode.id))

    for code in LANGUAGE_BY_UI_CODE:
        service.update_language(
            episode.id,
            code,  # type: ignore[arg-type]
            LanguageVersionUpdate(
                translation_review_status="approved",
                voice_review_status="approved",
                final_approval_status="approved",
            ),
            901,
        )
    assert service.multilingual_complete(service.require_episode(episode.id))


def test_approved_script_cannot_be_overwritten(sheeko_db: Session) -> None:
    service = SheekoXariiroService(sheeko_db)
    episode = service.create_episode(EpisodeCreate(episode_title="Locked"), 901)
    service.update_language(
        episode.id,
        "om",
        LanguageVersionUpdate(
            script="Barruu mirkanaa'e",
            translation_review_status="approved",
        ),
        901,
    )
    with pytest.raises(SheekoError, match="approved script"):
        service.update_language(
            episode.id,
            "om",
            LanguageVersionUpdate(script="Overwrite"),
            901,
        )


@pytest.mark.anyio
async def test_elevenlabs_routes_only_somali_and_swahili_with_v3() -> None:
    captured: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.read() and __import__("json").loads(request.content))
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "audio/mpeg"},
            content=b"ID3",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = ElevenLabsProvider(
            ElevenLabsService(api_key="test-secret", client=client)
        )
        router = ProviderRouter(elevenlabs=provider)
        for code in ("so", "sw"):
            audio = await router.provider_for(code).generate_speech(
                text="Test", voice="voice123", language=code
            )
            await audio.close()
        for code in ("aa", "am", "om"):
            with pytest.raises(TTSServiceError) as error:
                router.provider_for(code)
            assert error.value.code == "tts_language_not_configured"

    assert [body["model_id"] for body in captured] == [DEFAULT_MODEL_ID, DEFAULT_MODEL_ID]
    assert DEFAULT_MODEL_ID == "eleven_v3"


def test_configured_adapter_fallback_never_relabels_elevenlabs() -> None:
    service = ElevenLabsService(
        api_key="test-secret",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    router = ProviderRouter(
        elevenlabs=ElevenLabsProvider(service),
        configured_adapters={"aa": LicensedAfarAdapter()},
    )
    assert router.provider_for("aa").provider_name == "configured-licensed-adapter"
    afar = next(item for item in router.capabilities() if item.ui_code == "aa")
    assert afar.ai_voice_configured
    assert not afar.official_elevenlabs_support


def test_asset_names_and_subtitles_are_language_specific() -> None:
    somali = production_filename(
        episode_slug="diin-iyo-bakayle",
        scene_number=1,
        character_name="ATHERO",
        language="so",
        version=1,
        extension="mp3",
    )
    oromo = production_filename(
        episode_slug="diin-iyo-bakayle",
        scene_number=1,
        character_name="ATHERO",
        language="om",
        version=1,
        extension="mp3",
    )
    assert somali == "sheeko-xariiro_diin-iyo-bakayle_01_athero_so_v1.mp3"
    assert oromo.endswith("_om_v1.mp3")
    assert somali != oromo
    assert subtitle_vtt("Sheeko") == (
        "WEBVTT\n\n00:00:00.000 --> 00:00:05.000\nSheeko\n"
    )


def test_manual_audio_upload_keeps_unconfigured_language_in_production(
    sheeko_db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def override_db() -> Generator[Session, None, None]:
        try:
            yield sheeko_db
            sheeko_db.commit()
        except Exception:
            sheeko_db.rollback()
            raise

    monkeypatch.setattr(settings, "MEDIA_LOCAL_ROOT", str(tmp_path))
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = authorised_user
    try:
        client = TestClient(app)
        created = client.post(
            "/api/v1/sheeko-xariiro/episodes",
            json={"episode_title": "Afar Upload", "original_script": "Qafar script"},
        )
        assert created.status_code == 201
        episode_id = created.json()["id"]
        upload = client.post(
            f"/api/v1/sheeko-xariiro/episodes/{episode_id}/languages/aa/audio-upload",
            params={"character_name": "ATHERO", "scene_number": 1},
            files={"audio": ("approved.wav", b"RIFFmock-wave", "audio/wav")},
        )
        assert upload.status_code == 201
        payload = upload.json()
        assert payload["source"] == "uploaded"
        assert payload["filename"].endswith("_aa_v1.wav")
        assert (tmp_path / "sheeko-xariiro" / payload["filename"]).is_file()

        rejected_preset = client.put(
            "/api/v1/sheeko-xariiro/voice-presets",
            json={
                "preset_name": "ATHERO",
                "character_name": "ATHERO",
                "language_code": "aa",
                "provider": "elevenlabs",
                "voice_id": "voice123",
                "model_id": "eleven_v3",
            },
        )
        assert rejected_preset.status_code == 422
        assert rejected_preset.json()["detail"]["code"] == (
            "unverified_elevenlabs_language"
        )

        approved_preset = client.put(
            "/api/v1/sheeko-xariiro/voice-presets",
            json={
                "preset_name": "ATHERO",
                "character_name": "ATHERO",
                "language_code": "so",
                "provider": "elevenlabs",
                "voice_id": "voice123",
                "model_id": "eleven_v3",
            },
        )
        assert approved_preset.status_code == 200
        assert approved_preset.json()["voice_id"] == "voice123"
    finally:
        app.dependency_overrides.clear()


def test_api_key_never_appears_in_capabilities_or_models() -> None:
    provider = ElevenLabsProvider(
        ElevenLabsService(
            api_key="never-expose-this-key",
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(lambda request: httpx.Response(500))
            ),
        )
    )
    serialized = str(ProviderRouter(elevenlabs=provider).capabilities())
    assert "never-expose-this-key" not in serialized
    assert "ELEVENLABS_API_KEY" not in serialized
