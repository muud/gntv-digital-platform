"""Application service for live chat rooms, messages, and moderation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status

from app.models.user import User
from app.modules.chat.models import (
    ChatMessage,
    ChatMessageStatus,
    ChatModerationAction,
    ChatModerationAudit,
    ChatModerationRule,
    ChatRoom,
    ChatRoomStatus,
)
from app.modules.chat.moderation import ChatModerationEngine, ModerationDecision
from app.modules.chat.redis_coordination import ChatCoordinator
from app.modules.chat.repository import ChatRepository
from app.modules.chat.schemas import (
    ChatMessageEnvelope,
    ChatModerationActionRequest,
    ChatModerationRuleCreateRequest,
    ChatRoomCreateRequest,
    SendMessageEnvelope,
)


def username_for(user: User) -> str:
    return user.name or user.email.split("@", maxsplit=1)[0]


def user_is_moderator(user: User) -> bool:
    roles = set(user.role_names)
    permissions = user.permission_names
    return bool({"admin", "chief_editor", "producer", "moderator"} & roles) or "chat:moderate" in permissions or "*" in permissions


def timestamp_ms(value: datetime) -> int:
    value = normalize_utc(value)
    return int(value.timestamp() * 1000)


def normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class ChatService:
    def __init__(
        self,
        repository: ChatRepository,
        coordinator: ChatCoordinator,
        moderation_engine: ChatModerationEngine | None = None,
    ) -> None:
        self.repository = repository
        self.coordinator = coordinator
        self.moderation_engine = moderation_engine or ChatModerationEngine()

    def create_room(self, payload: ChatRoomCreateRequest) -> ChatRoom:
        return self.repository.create_room(
            ChatRoom(
                live_channel_id=payload.live_channel_id,
                name=payload.name,
                status=payload.status,
                slow_mode_seconds=payload.slow_mode_seconds,
            )
        )

    def room_or_404(self, room_id: UUID) -> ChatRoom:
        room = self.repository.room(room_id)
        if room is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "chat_room_not_found"})
        return room

    def list_messages(self, room_id: UUID, *, limit: int, before_id: UUID | None) -> list[ChatMessage]:
        self.room_or_404(room_id)
        return self.repository.messages(room_id, limit=limit, before_id=before_id)

    def list_rules(self, room_id: UUID) -> list[ChatModerationRule]:
        self.room_or_404(room_id)
        return self.repository.rules_for_room(room_id)

    def add_rule(self, room_id: UUID, payload: ChatModerationRuleCreateRequest, user: User) -> ChatModerationRule:
        self.room_or_404(room_id)
        return self.repository.add_rule(
            ChatModerationRule(
                room_id=room_id,
                pattern=payload.pattern,
                match_type=payload.match_type,
                action=payload.action,
                created_by=user.id,
            )
        )

    def apply_moderation_action(
        self,
        room_id: UUID,
        payload: ChatModerationActionRequest,
        user: User,
    ) -> ChatModerationAudit:
        self.room_or_404(room_id)
        if payload.action == ChatModerationAction.MUTE and payload.target_user_id is not None:
            self.repository.apply_mute(room_id, payload.target_user_id, payload.duration_seconds)
        elif payload.action == ChatModerationAction.BAN and payload.target_user_id is not None:
            self.repository.apply_ban(room_id, payload.target_user_id)
        elif payload.action == ChatModerationAction.DELETE and payload.target_message_id is not None:
            self.repository.mark_deleted(payload.target_message_id, user.id)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "invalid_moderation_target"})
        return self.repository.add_audit(
            room_id=room_id,
            moderator_id=user.id,
            target_user_id=payload.target_user_id,
            target_message_id=payload.target_message_id,
            action=payload.action,
            reason=payload.reason,
        )

    async def join_room(self, room_id: UUID, user: User) -> int:
        self.room_or_404(room_id)
        return await self.coordinator.heartbeat_presence(room_id, user.id)

    async def leave_room(self, room_id: UUID, user: User) -> int:
        return await self.coordinator.leave_presence(room_id, user.id)

    async def receive_message(self, room_id: UUID, user: User, payload: SendMessageEnvelope) -> ChatMessageEnvelope | None:
        room = self.room_or_404(room_id)
        if room.status != ChatRoomStatus.ACTIVE:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "chat_room_not_writable"})
        state = self.repository.user_state(room_id, user.id)
        now = datetime.now(UTC)
        if state.is_banned:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "chat_user_banned"})
        if state.is_muted and (state.muted_until is None or normalize_utc(state.muted_until) > now):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "chat_user_muted"})
        if room.slow_mode_seconds and state.last_message_at is not None:
            elapsed = now - normalize_utc(state.last_message_at)
            if elapsed < timedelta(seconds=room.slow_mode_seconds):
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "chat_slow_mode"})

        is_new = await self.coordinator.check_dedup(room_id, payload.client_msg_id)
        if not is_new:
            return None
        if not await self.coordinator.check_rate_limit(user.id, room_id):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "chat_rate_limited"})

        decision = self._moderation_decision(room_id, payload.text)
        message_status = ChatMessageStatus.PUBLISHED
        if decision.action == ChatModerationAction.FLAG:
            message_status = ChatMessageStatus.FLAGGED
        elif decision.action in {ChatModerationAction.BLOCK, ChatModerationAction.MUTE, ChatModerationAction.BAN}:
            message_status = ChatMessageStatus.BLOCKED

        message = self.repository.add_message(
            ChatMessage(
                room_id=room_id,
                user_id=user.id,
                username=username_for(user),
                message_text=payload.text,
                client_msg_id=payload.client_msg_id,
                status=message_status,
            )
        )
        self.repository.update_last_message_at(room_id, user.id)
        if decision.action is not None:
            self.repository.add_audit(
                room_id=room_id,
                moderator_id=user.id,
                target_user_id=user.id,
                target_message_id=message.id,
                action=decision.action,
                reason=decision.reason,
            )
        if decision.action == ChatModerationAction.MUTE:
            self.repository.apply_mute(room_id, user.id, 300)
        if decision.action == ChatModerationAction.BAN:
            self.repository.apply_ban(room_id, user.id)

        envelope = ChatMessageEnvelope(
            id=message.id,
            room_id=message.room_id,
            user_id=message.user_id,
            username=message.username,
            text=message.message_text,
            client_msg_id=message.client_msg_id,
            timestamp_ms=timestamp_ms(message.created_at),
            status=message.status,
        )
        if message_status == ChatMessageStatus.PUBLISHED:
            try:
                await self.coordinator.publish(room_id, envelope.model_dump(mode="json"))
            except Exception:
                message.status = ChatMessageStatus.FLAGGED
                self.repository.add_audit(
                    room_id=room_id,
                    moderator_id=user.id,
                    target_user_id=user.id,
                    target_message_id=message.id,
                    action=ChatModerationAction.FLAG,
                    reason="Redis publish failed; held for review",
                )
                return None
            return envelope
        if message_status == ChatMessageStatus.FLAGGED:
            return envelope
        return None

    def _moderation_decision(self, room_id: UUID, text: str) -> ModerationDecision:
        rules = self.repository.rules_for_room(room_id)
        return self.moderation_engine.evaluate(text, rules)
