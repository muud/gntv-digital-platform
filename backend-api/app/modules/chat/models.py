"""Audience engagement live chat domain models for Module 7 Sprint 7.1."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


def enum_type(enum: type[StrEnum], name: str) -> Enum:
    return Enum(enum, name=name, values_callable=lambda values: [item.value for item in values])


class ChatRoomStatus(StrEnum):
    ACTIVE = "active"
    READ_ONLY = "read_only"
    CLOSED = "closed"


class ChatMessageStatus(StrEnum):
    PUBLISHED = "published"
    FLAGGED = "flagged"
    DELETED = "deleted"
    BLOCKED = "blocked"


class ChatRuleMatchType(StrEnum):
    EXACT = "exact"
    REGEX = "regex"
    FUZZY = "fuzzy"


class ChatModerationAction(StrEnum):
    BLOCK = "block"
    FLAG = "flag"
    MUTE = "mute"
    BAN = "ban"
    DELETE = "delete"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class ChatRoom(Base, TimestampMixin):
    __tablename__ = "chat_rooms"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    live_channel_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("live_channels.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ChatRoomStatus] = mapped_column(
        enum_type(ChatRoomStatus, "gntv_chat_room_status"),
        default=ChatRoomStatus.ACTIVE,
        nullable=False,
    )
    slow_mode_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        CheckConstraint("slow_mode_seconds >= 0", name="ck_chat_rooms_slow_mode"),
        UniqueConstraint("live_channel_id", name="uq_chat_rooms_live_channel"),
        Index("idx_chat_rooms_channel_status", "live_channel_id", "status"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    room_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    client_msg_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[ChatMessageStatus] = mapped_column(
        enum_type(ChatMessageStatus, "gntv_chat_message_status"),
        default=ChatMessageStatus.PUBLISHED,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        UniqueConstraint("room_id", "client_msg_id", name="uq_chat_messages_room_client_msg"),
        Index("idx_chat_messages_room_time", "room_id", "created_at"),
        Index("idx_chat_messages_room_status", "room_id", "status"),
        Index("idx_chat_messages_user_time", "user_id", "created_at"),
    )


class ChatModerationRule(Base):
    __tablename__ = "chat_moderation_rules"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    room_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("chat_rooms.id", ondelete="CASCADE"))
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    match_type: Mapped[ChatRuleMatchType] = mapped_column(
        enum_type(ChatRuleMatchType, "gntv_chat_rule_match_type"),
        default=ChatRuleMatchType.REGEX,
        nullable=False,
    )
    action: Mapped[ChatModerationAction] = mapped_column(
        enum_type(ChatModerationAction, "gntv_chat_moderation_action"),
        default=ChatModerationAction.BLOCK,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("room_id", "pattern", "match_type", name="uq_chat_rules_room_pattern"),
        Index("idx_chat_rules_room_active", "room_id", "is_active"),
    )


class ChatUserState(Base):
    __tablename__ = "chat_user_states"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    room_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    is_muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    muted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_chat_user_states_room_user"),
        Index("idx_chat_user_states_room_user", "room_id", "user_id"),
    )


class ChatModerationAudit(Base):
    __tablename__ = "chat_moderation_audit"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    room_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False)
    moderator_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    target_message_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("chat_messages.id", ondelete="SET NULL"))
    action: Mapped[ChatModerationAction] = mapped_column(
        enum_type(ChatModerationAction, "gntv_chat_audit_action"),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        Index("idx_chat_moderation_audit_room_time", "room_id", "created_at"),
        Index("idx_chat_moderation_audit_target_user", "target_user_id"),
    )
