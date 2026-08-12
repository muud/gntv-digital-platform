"""Persistence repository for the Module 7 live chat control plane."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.chat.models import (
    ChatMessage,
    ChatMessageStatus,
    ChatModerationAction,
    ChatModerationAudit,
    ChatModerationRule,
    ChatRoom,
    ChatUserState,
)


class ChatRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def room(self, room_id: UUID) -> ChatRoom | None:
        return self.db.get(ChatRoom, room_id)

    def create_room(self, room: ChatRoom) -> ChatRoom:
        self.db.add(room)
        self.db.flush()
        return room

    def messages(self, room_id: UUID, *, limit: int, before_id: UUID | None = None) -> list[ChatMessage]:
        query = select(ChatMessage).where(ChatMessage.room_id == room_id)
        if before_id is not None:
            before = self.db.get(ChatMessage, before_id)
            if before is not None:
                query = query.where(ChatMessage.created_at < before.created_at)
        return list(self.db.execute(query.order_by(ChatMessage.created_at.desc()).limit(limit)).scalars().all())

    def message(self, message_id: UUID) -> ChatMessage | None:
        return self.db.get(ChatMessage, message_id)

    def add_message(self, message: ChatMessage) -> ChatMessage:
        self.db.add(message)
        self.db.flush()
        return message

    def rules_for_room(self, room_id: UUID) -> list[ChatModerationRule]:
        return list(
            self.db.execute(
                select(ChatModerationRule).where(
                    ChatModerationRule.is_active.is_(True),
                    (ChatModerationRule.room_id == room_id) | (ChatModerationRule.room_id.is_(None)),
                )
            )
            .scalars()
            .all()
        )

    def add_rule(self, rule: ChatModerationRule) -> ChatModerationRule:
        self.db.add(rule)
        self.db.flush()
        return rule

    def user_state(self, room_id: UUID, user_id: int) -> ChatUserState:
        state = self.db.execute(
            select(ChatUserState).where(ChatUserState.room_id == room_id, ChatUserState.user_id == user_id)
        ).scalar_one_or_none()
        if state is None:
            state = ChatUserState(room_id=room_id, user_id=user_id)
            self.db.add(state)
            self.db.flush()
        return state

    def apply_mute(self, room_id: UUID, user_id: int, duration_seconds: int | None) -> ChatUserState:
        state = self.user_state(room_id, user_id)
        state.is_muted = True
        state.muted_until = datetime.now(UTC) + timedelta(seconds=duration_seconds or 300)
        self.db.flush()
        return state

    def apply_ban(self, room_id: UUID, user_id: int) -> ChatUserState:
        state = self.user_state(room_id, user_id)
        state.is_banned = True
        state.banned_at = datetime.now(UTC)
        self.db.flush()
        return state

    def update_last_message_at(self, room_id: UUID, user_id: int) -> None:
        state = self.user_state(room_id, user_id)
        state.last_message_at = datetime.now(UTC)
        self.db.flush()

    def mark_deleted(self, message_id: UUID, moderator_id: int) -> ChatMessage | None:
        message = self.message(message_id)
        if message is None:
            return None
        message.status = ChatMessageStatus.DELETED
        message.deleted_at = datetime.now(UTC)
        message.deleted_by = moderator_id
        self.db.flush()
        return message

    def add_audit(
        self,
        *,
        room_id: UUID,
        moderator_id: int,
        action: ChatModerationAction,
        target_user_id: int | None = None,
        target_message_id: UUID | None = None,
        reason: str | None = None,
    ) -> ChatModerationAudit:
        audit = ChatModerationAudit(
            room_id=room_id,
            moderator_id=moderator_id,
            target_user_id=target_user_id,
            target_message_id=target_message_id,
            action=action,
            reason=reason,
        )
        self.db.add(audit)
        self.db.flush()
        return audit
