from typing import Self

from pydantic import AliasChoices, Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "GNTV DIGITAL, ALL EVERYWHERE Backend API"
    ENVIRONMENT: str = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "NODE_ENV"),
    )

    POSTGRES_USER: str = Field(validation_alias="POSTGRES_USER")
    POSTGRES_PASSWORD: str = Field(validation_alias="POSTGRES_PASSWORD")
    POSTGRES_DB: str = Field(validation_alias="POSTGRES_DB")
    POSTGRES_HOST: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    POSTGRES_PORT: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    DATABASE_URL: str | None = None

    REDIS_HOST: str = Field(default="localhost", validation_alias="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, validation_alias="REDIS_PORT")
    REDIS_URL: str | None = None

    INGEST_GATEWAY_TOKEN: str = Field(
        default="development-ingest-gateway-token",
        min_length=24,
        validation_alias="INGEST_GATEWAY_TOKEN",
    )
    INGEST_LEASE_TTL_SECONDS: int = Field(default=30, ge=10, le=300)
    INGEST_ENCODER_TTL_SECONDS: int = Field(default=60, ge=15, le=600)
    INGEST_KEY_CACHE_TTL_SECONDS: int = Field(default=30, ge=1, le=120)

    FFMPEG_BINARY: str = Field(default="ffmpeg", validation_alias="FFMPEG_BINARY")
    FFPROBE_BINARY: str = Field(default="ffprobe", validation_alias="FFPROBE_BINARY")
    MEDIA_PROCESSING_WORKSPACE_ROOT: str = Field(
        default="/tmp/gntv-transcode",
        validation_alias="MEDIA_PROCESSING_WORKSPACE_ROOT",
    )
    MEDIA_PROCESSING_OUTPUT_ROOT: str = Field(
        default="./var/streaming-media",
        validation_alias="MEDIA_PROCESSING_OUTPUT_ROOT",
    )
    FFMPEG_TERMINATE_GRACE_SECONDS: float = Field(default=3.0, ge=0.1, le=30)
    MEDIA_WORKER_LEASE_SECONDS: int = Field(default=30, ge=10, le=300)
    MEDIA_TELEMETRY_TTL_SECONDS: int = Field(default=120, ge=30, le=3600)
    MEDIA_GPU_WORKERS_ENABLED: bool = Field(
        default=False,
        validation_alias="MEDIA_GPU_WORKERS_ENABLED",
    )

    JWT_SECRET_KEY: str = Field(default="super-secret-jwt-key", validation_alias="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    EMAIL_FROM: str = Field(default="no-reply@gntv.com", validation_alias="EMAIL_FROM")
    EMAIL_API_KEY: str = Field(default="", validation_alias="EMAIL_API_KEY")
    EMAIL_ENDPOINT: str = Field(default="https://dm.aliyuncs.com", validation_alias="EMAIL_ENDPOINT")

    ELEVENLABS_API_KEY: SecretStr | None = Field(
        default=None,
        validation_alias="ELEVENLABS_API_KEY",
    )

    OSS_BUCKET_NAME: str = Field(default="", validation_alias="OSS_BUCKET_NAME")
    OSS_ENDPOINT: str = Field(default="", validation_alias="OSS_ENDPOINT")
    OSS_ACCESS_KEY_ID: str = Field(default="", validation_alias="OSS_ACCESS_KEY_ID")
    OSS_ACCESS_KEY_SECRET: str = Field(default="", validation_alias="OSS_ACCESS_KEY_SECRET")
    MEDIA_STORAGE_PROVIDER: str = Field(default="local", validation_alias="MEDIA_STORAGE_PROVIDER")
    MEDIA_LOCAL_ROOT: str = Field(default="./var/media", validation_alias="MEDIA_LOCAL_ROOT")
    MEDIA_PUBLIC_BASE_URL: str = Field(default="/media", validation_alias="MEDIA_PUBLIC_BASE_URL")
    MEDIA_SIGNING_SECRET: str = Field(default="development-media-secret", validation_alias="MEDIA_SIGNING_SECRET")
    MEDIA_MAX_FILE_SIZE: int = Field(default=5_368_709_120, validation_alias="MEDIA_MAX_FILE_SIZE")
    MEDIA_URL_TTL_SECONDS: int = Field(default=900, validation_alias="MEDIA_URL_TTL_SECONDS")

    PLAYBACK_SIGNING_SECRET: SecretStr = Field(
        default=SecretStr("development-playback-signing-secret"),
        min_length=32,
        validation_alias="PLAYBACK_SIGNING_SECRET",
    )
    PLAYBACK_TOKEN_TTL_SECONDS: int = Field(
        default=600,
        ge=30,
        le=3600,
        validation_alias="PLAYBACK_TOKEN_TTL_SECONDS",
    )
    PLAYBACK_PUBLIC_BASE_URL: str = Field(
        default="https://stream.gntv.com",
        validation_alias=AliasChoices("PLAYBACK_PUBLIC_BASE_URL", "ALIBABA_CDN_PLAY_DOMAIN"),
    )

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, value: str | None, info: ValidationInfo) -> str:
        if value:
            return value
        values = info.data
        return (
            f"postgresql://{values.get('POSTGRES_USER')}:{values.get('POSTGRES_PASSWORD')}"
            f"@{values.get('POSTGRES_HOST')}:{values.get('POSTGRES_PORT')}/{values.get('POSTGRES_DB')}"
        )

    @field_validator("REDIS_URL", mode="before")
    @classmethod
    def assemble_redis_url(cls, value: str | None, info: ValidationInfo) -> str:
        if value:
            return value
        values = info.data
        return f"redis://{values.get('REDIS_HOST')}:{values.get('REDIS_PORT')}/0"

    @model_validator(mode="after")
    def reject_default_ingest_token_in_production(self) -> Self:
        if (
            self.ENVIRONMENT.lower() in {"production", "staging"}
            and self.INGEST_GATEWAY_TOKEN == "development-ingest-gateway-token"
        ):
            raise ValueError("INGEST_GATEWAY_TOKEN must be configured outside development")
        return self

    @model_validator(mode="after")
    def reject_default_playback_secret_in_production(self) -> Self:
        if (
            self.ENVIRONMENT.lower() in {"production", "staging"}
            and self.PLAYBACK_SIGNING_SECRET.get_secret_value()
            == "development-playback-signing-secret"
        ):
            raise ValueError("PLAYBACK_SIGNING_SECRET must be configured outside development")
        return self


settings = Settings()  # type: ignore[call-arg]
