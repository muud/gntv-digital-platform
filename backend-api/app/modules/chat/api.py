"""REST API for Module 7 Sprint 7.1 audience live chat."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.chat.dependencies import get_chat_service, require_chat_moderator
from app.modules.chat.schemas import (
    ChatMessagePageResponse,
    ChatMessageResponse,
    ChatModerationActionRequest,
    ChatModerationAuditResponse,
    ChatModerationRuleCreateRequest,
    ChatModerationRuleResponse,
    ChatRoomCreateRequest,
    ChatRoomResponse,
)
from app.modules.chat.service import ChatService
from app.modules.streaming.api.router import ERROR_RESPONSES

router = APIRouter(prefix="/api/v1/chat", tags=["Audience Live Chat"])

ChatServiceDependency = Annotated[ChatService, Depends(get_chat_service)]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
ModeratorUser = Annotated[User, Depends(require_chat_moderator)]


@router.post(
    "/rooms",
    response_model=ChatRoomResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def create_room(
    payload: ChatRoomCreateRequest,
    user: ModeratorUser,
    service: ChatServiceDependency,
) -> ChatRoomResponse:
    del user
    return ChatRoomResponse.model_validate(service.create_room(payload))


@router.get(
    "/rooms/{room_id}/messages",
    response_model=ChatMessagePageResponse,
    responses=ERROR_RESPONSES,
)
def list_messages(
    room_id: UUID,
    user: AuthenticatedUser,
    service: ChatServiceDependency,
    limit: int = Query(default=50, ge=1, le=100),
    before_id: UUID | None = None,
) -> ChatMessagePageResponse:
    del user
    messages = service.list_messages(room_id, limit=limit, before_id=before_id)
    return ChatMessagePageResponse(
        items=[ChatMessageResponse.model_validate(message) for message in messages],
        next_before_id=messages[-1].id if len(messages) == limit else None,
    )


@router.post(
    "/rooms/{room_id}/moderation/action",
    response_model=ChatModerationAuditResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def moderation_action(
    room_id: UUID,
    payload: ChatModerationActionRequest,
    user: ModeratorUser,
    service: ChatServiceDependency,
) -> ChatModerationAuditResponse:
    return ChatModerationAuditResponse.model_validate(service.apply_moderation_action(room_id, payload, user))


@router.get(
    "/rooms/{room_id}/moderation/rules",
    response_model=list[ChatModerationRuleResponse],
    responses=ERROR_RESPONSES,
)
def list_rules(
    room_id: UUID,
    user: ModeratorUser,
    service: ChatServiceDependency,
) -> list[ChatModerationRuleResponse]:
    del user
    return [ChatModerationRuleResponse.model_validate(rule) for rule in service.list_rules(room_id)]


@router.post(
    "/rooms/{room_id}/moderation/rules",
    response_model=ChatModerationRuleResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
def create_rule(
    room_id: UUID,
    payload: ChatModerationRuleCreateRequest,
    user: ModeratorUser,
    service: ChatServiceDependency,
) -> ChatModerationRuleResponse:
    return ChatModerationRuleResponse.model_validate(service.add_rule(room_id, payload, user))
