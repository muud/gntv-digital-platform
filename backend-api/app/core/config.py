from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "GNTV DIGITAL, ALL EVERYWHERE Backend API"
    ENVIRONMENT: str = Field(default="development", validation_alias="ENVIRONMENT")

    POSTGRES_USER: str = Field(validation_alias="POSTGRES_USER")
    POSTGRES_PASSWORD: str = Field(validation_alias="POSTGRES_PASSWORD")
    POSTGRES_DB: str = Field(validation_alias="POSTGRES_DB")
    POSTGRES_HOST: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    POSTGRES_PORT: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    DATABASE_URL: str | None = None

    REDIS_HOST: str = Field(default="localhost", validation_alias="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, validation_alias="REDIS_PORT")
    REDIS_URL: str | None = None

    JWT_SECRET_KEY: str = Field(default="super-secret-jwt-key", validation_alias="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    EMAIL_FROM: str = Field(default="no-reply@gntv.com", validation_alias="EMAIL_FROM")
    EMAIL_API_KEY: str = Field(default="", validation_alias="EMAIL_API_KEY")
    EMAIL_ENDPOINT: str = Field(default="https://dm.aliyuncs.com", validation_alias="EMAIL_ENDPOINT")

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


settings = Settings()  # type: ignore[call-arg]
