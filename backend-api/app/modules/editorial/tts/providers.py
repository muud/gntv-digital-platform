"""Provider-neutral routing for the five Sheeko Xariiro production languages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping

from app.modules.editorial.tts.schemas import (
    DEFAULT_MODEL_ID,
    LanguageCapability,
    UILanguageCode,
    VoiceListResponse,
)
from app.modules.editorial.tts.service import ElevenLabsService, GeneratedAudio, TTSServiceError


LANGUAGES: tuple[LanguageCapability, ...] = (
    LanguageCapability(
        ui_code="aa",
        iso_639_3="aar",
        name="Afar",
        native_name="Qafar Af",
        provider=None,
        ai_voice_configured=False,
        official_elevenlabs_support=False,
        message="AI voice provider is not yet configured for this language.",
    ),
    LanguageCapability(
        ui_code="am",
        iso_639_3="amh",
        name="Amharic",
        native_name="አማርኛ",
        provider=None,
        ai_voice_configured=False,
        official_elevenlabs_support=False,
        message="AI voice provider is not yet configured for this language.",
    ),
    LanguageCapability(
        ui_code="om",
        iso_639_3="orm",
        name="Oromo",
        native_name="Afaan Oromoo",
        provider=None,
        ai_voice_configured=False,
        official_elevenlabs_support=False,
        message="AI voice provider is not yet configured for this language.",
    ),
    LanguageCapability(
        ui_code="so",
        iso_639_3="som",
        name="Somali",
        native_name="Af-Soomaali",
        provider="elevenlabs",
        ai_voice_configured=True,
        official_elevenlabs_support=True,
        model_id=DEFAULT_MODEL_ID,
    ),
    LanguageCapability(
        ui_code="sw",
        iso_639_3="swa",
        name="Swahili",
        native_name="Kiswahili",
        provider="elevenlabs",
        ai_voice_configured=True,
        official_elevenlabs_support=True,
        model_id=DEFAULT_MODEL_ID,
    ),
)
LANGUAGE_BY_UI_CODE = {language.ui_code: language for language in LANGUAGES}


class TextToSpeechProvider(ABC):
    """Common interface implemented by licensed speech providers."""

    provider_name: str

    @abstractmethod
    async def list_voices(self, language: UILanguageCode) -> VoiceListResponse:
        raise NotImplementedError

    @abstractmethod
    async def generate_speech(
        self,
        *,
        text: str,
        voice: str,
        language: UILanguageCode,
        settings: dict[str, object] | None = None,
    ) -> GeneratedAudio:
        raise NotImplementedError

    async def preview_speech(
        self,
        *,
        text: str,
        voice: str,
        language: UILanguageCode,
    ) -> GeneratedAudio:
        return await self.generate_speech(text=text, voice=voice, language=language)

    @abstractmethod
    def check_language_support(self, language: UILanguageCode) -> bool:
        raise NotImplementedError


class ElevenLabsProvider(TextToSpeechProvider):
    provider_name = "elevenlabs"
    _official_languages = frozenset({"so", "sw"})

    def __init__(self, service: ElevenLabsService) -> None:
        self._service = service

    def check_language_support(self, language: UILanguageCode) -> bool:
        return language in self._official_languages

    def _require_supported(self, language: UILanguageCode) -> None:
        if not self.check_language_support(language):
            raise TTSServiceError(
                422,
                "tts_language_not_supported",
                "ElevenLabs is not configured for this language.",
            )

    async def list_voices(self, language: UILanguageCode) -> VoiceListResponse:
        self._require_supported(language)
        return await self._service.list_voices()

    async def generate_speech(
        self,
        *,
        text: str,
        voice: str,
        language: UILanguageCode,
        settings: dict[str, object] | None = None,
    ) -> GeneratedAudio:
        self._require_supported(language)
        output_format = settings.get("output_format") if settings else None
        return await self._service.synthesize(
            text=text,
            voice_id=voice,
            model_id=DEFAULT_MODEL_ID,
            output_format=output_format,  # type: ignore[arg-type]
        )


class ProviderRouter:
    """Routes official ElevenLabs languages and injected licensed adapters."""

    def __init__(
        self,
        *,
        elevenlabs: ElevenLabsProvider,
        configured_adapters: Mapping[UILanguageCode, TextToSpeechProvider] | None = None,
    ) -> None:
        self._elevenlabs = elevenlabs
        self._configured_adapters = dict(configured_adapters or {})

    def provider_for(self, language: UILanguageCode) -> TextToSpeechProvider:
        if language in {"so", "sw"}:
            return self._elevenlabs
        provider = self._configured_adapters.get(language)
        if provider and provider.check_language_support(language):
            return provider
        raise TTSServiceError(
            503,
            "tts_language_not_configured",
            "AI voice provider is not yet configured for this language.",
        )

    def capabilities(self) -> list[LanguageCapability]:
        capabilities: list[LanguageCapability] = []
        for language in LANGUAGES:
            adapter = self._configured_adapters.get(language.ui_code)
            if adapter and adapter.check_language_support(language.ui_code):
                capabilities.append(
                    language.model_copy(
                        update={
                            "provider": adapter.provider_name,
                            "ai_voice_configured": True,
                            "message": None,
                        }
                    )
                )
            else:
                capabilities.append(language.model_copy())
        return capabilities
