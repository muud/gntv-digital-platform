"""Strict API contracts for editorial text-to-speech."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DEFAULT_MODEL_ID = "eleven_v3"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"
MAX_TEXT_LENGTH = 5_000
UI_LANGUAGE_CODES = ("aa", "am", "om", "so", "sw")
ISO_LANGUAGE_CODES = ("aar", "amh", "orm", "som", "swa")

UILanguageCode = Literal["aa", "am", "om", "so", "sw"]
ISOLanguageCode = Literal["aar", "amh", "orm", "som", "swa"]

MP3OutputFormat = Literal[
    "mp3_22050_32",
    "mp3_24000_48",
    "mp3_44100_32",
    "mp3_44100_64",
    "mp3_44100_96",
    "mp3_44100_128",
    "mp3_44100_192",
]


class TTSContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SpeechSynthesisRequest(TTSContract):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    language: UILanguageCode = "so"
    voice_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    model_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    output_format: MP3OutputFormat | None = None


class VoiceSummary(TTSContract):
    voice_id: str
    name: str
    category: str | None = None
    description: str | None = None
    preview_url: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class VoiceListResponse(TTSContract):
    voices: list[VoiceSummary]


class LanguageCapability(TTSContract):
    ui_code: UILanguageCode
    iso_639_3: ISOLanguageCode
    name: str
    native_name: str
    provider: str | None
    ai_voice_configured: bool
    official_elevenlabs_support: bool
    model_id: str | None = None
    message: str | None = None


class LanguageCapabilityResponse(TTSContract):
    languages: list[LanguageCapability]


class TTSErrorDetail(TTSContract):
    code: str
    message: str | None = None


class TTSErrorResponse(TTSContract):
    detail: TTSErrorDetail | str
