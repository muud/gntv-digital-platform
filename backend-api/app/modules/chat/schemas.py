"""Typed REST and WebSocket contracts for Module 7 Sprint 7.1 live chat."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.chat.models import ChatMessageStatus, ChatModerationAction, ChatRoomStatus, ChatRuleMatchType

MAX_CHAT_TEXT_LENGTH = 2048


class ChatContract(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class ChatRoomCreateRequest(ChatContract):
    live_channel_id: UUID | None = None
    name: str = Field(min_length=1, max_length=100)
    status: ChatRoomStatus = ChatRoomStatus.ACTIVE
    slow_mode_seconds: int = Field(default=0, ge=0, le=300)


class ChatRoomResponse(ChatContract):
    id: UUID
    live_channel_id: UUID | None
    name: str
    status: ChatRoomStatus
    slow_mode_seconds: int
    created_at: datetime
    updated_at: datetime


class ChatMessageResponse(ChatContract):
    id: UUID
    room_id: UUID
    user_id: int | None
    username: str
    message_text: str
    client_msg_id: str
    status: ChatMessageStatus
    created_at: datetime


class ChatMessagePageResponse(ChatContract):
    items: list[ChatMessageResponse]
    next_before_id: UUID | None = None


class ChatModerationRuleCreateRequest(ChatContract):
    pattern: str = Field(min_length=1, max_length=255)
    match_type: ChatRuleMatchType = ChatRuleMatchType.REGEX
    action: ChatModerationAction = ChatModerationAction.BLOCK


class ChatModerationRuleResponse(ChatContract):
    id: UUID
    room_id: UUID | None
    pattern: str
    match_type: ChatRuleMatchType
    action: ChatModerationAction
    is_active: bool
    created_by: int
    created_at: datetime


class ChatModerationActionRequest(ChatContract):
    action: ChatModerationAction
    target_user_id: int | None = None
    target_message_id: UUID | None = None
    duration_seconds: int | None = Field(default=None, ge=1, le=86_400)
    reason: str | None = Field(default=None, max_length=255)


class ChatModerationAuditResponse(ChatContract):
    id: UUID
    room_id: UUID
    moderator_id: int
    target_user_id: int | None
    target_message_id: UUID | None
    action: ChatModerationAction
    reason: str | None
    created_at: datetime


class SendMessageEnvelope(ChatContract):
    type: Literal["send_message"]
    client_msg_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=MAX_CHAT_TEXT_LENGTH)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.replace("\x00", "").strip()
        if not normalized:
            raise ValueError("Message text is empty")
        return normalized


class ChatMessageEnvelope(ChatContract):
    type: Literal["chat_message"] = "chat_message"
    id: UUID
    room_id: UUID
    user_id: int | None
    username: str
    text: str
    client_msg_id: str
    timestamp_ms: int
    status: ChatMessageStatus = ChatMessageStatus.PUBLISHED


class PresenceUpdateEnvelope(ChatContract):
    type: Literal["presence_update"] = "presence_update"
    room_id: UUID
    active_viewers: int


class ModerationNoticeEnvelope(ChatContract):
    type: Literal["moderation_notice"] = "moderation_notice"
    action: str
    target_msg_id: UUID | None = None
    reason: str | None = None


class ErrorEnvelope(ChatContract):
    type: Literal["error"] = "error"
    code: str
    message: str


class HeartbeatEnvelope(ChatContract):
    type: Literal["heartbeat"]


class PongEnvelope(ChatContract):
    type: Literal["pong"] = "pong"
