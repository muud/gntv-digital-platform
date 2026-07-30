"""Persistence for independent scripts, voices, reviews, and audio per language."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SheekoXariiroEpisode(Base):
    __tablename__ = "sheeko_xariiro_episodes"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    episode_title: Mapped[str] = mapped_column(String(240), nullable=False)
    slug: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    original_script: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    languages: Mapped[list["SheekoLanguageVersion"]] = relationship(
        back_populates="episode",
        cascade="all, delete-orphan",
        order_by="SheekoLanguageVersion.language_code",
    )


class SheekoLanguageVersion(Base):
    __tablename__ = "sheeko_xariiro_language_versions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    episode_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("sheeko_xariiro_episodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    language_code: Mapped[str] = mapped_column(String(2), nullable=False)
    iso_639_3: Mapped[str] = mapped_column(String(3), nullable=False)
    script: Mapped[str] = mapped_column(Text, default="", nullable=False)
    character_assignments: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    athero_voice_id: Mapped[str | None] = mapped_column(String(128))
    narrator_voice_id: Mapped[str | None] = mapped_column(String(128))
    character_voices: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    pronunciation_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    generated_audio_url: Mapped[str | None] = mapped_column(String(1000))
    subtitle_url: Mapped[str | None] = mapped_column(String(1000))
    translation_review_status: Mapped[str] = mapped_column(
        String(24), default="pending", nullable=False
    )
    voice_review_status: Mapped[str] = mapped_column(
        String(24), default="pending", nullable=False
    )
    final_approval_status: Mapped[str] = mapped_column(
        String(24), default="pending", nullable=False
    )
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    episode: Mapped[SheekoXariiroEpisode] = relationship(back_populates="languages")
    audio_assets: Mapped[list["SheekoAudioAsset"]] = relationship(
        back_populates="language_version",
        cascade="all, delete-orphan",
    )
    __table_args__ = (
        UniqueConstraint("episode_id", "language_code", name="uq_sheeko_episode_language"),
        Index("idx_sheeko_language_review", "language_code", "final_approval_status"),
    )


class SheekoAudioAsset(Base):
    __tablename__ = "sheeko_xariiro_audio_assets"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    language_version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("sheeko_xariiro_language_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    scene_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    character_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    voice_id: Mapped[str | None] = mapped_column(String(128))
    model_id: Mapped[str | None] = mapped_column(String(128))
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    media_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    language_version: Mapped[SheekoLanguageVersion] = relationship(
        back_populates="audio_assets"
    )


class SheekoVoicePreset(Base):
    __tablename__ = "sheeko_xariiro_voice_presets"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    preset_name: Mapped[str] = mapped_column(String(80), nullable=False)
    character_name: Mapped[str] = mapped_column(String(120), nullable=False)
    language_code: Mapped[str] = mapped_column(String(2), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    voice_id: Mapped[str] = mapped_column(String(128), nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    settings: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint(
            "preset_name",
            "language_code",
            name="uq_sheeko_voice_preset_language",
        ),
    )


class SheekoGenerationAudit(Base):
    __tablename__ = "sheeko_xariiro_generation_audits"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    episode_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("sheeko_xariiro_episodes.id", ondelete="CASCADE")
    )
    language_code: Mapped[str] = mapped_column(String(2), nullable=False)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
