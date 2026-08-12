"""FastAPI dependencies for live chat."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis import redis_manager
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.chat.redis_coordination import ChatCoordinator, RedisChatCoordinator
from app.modules.chat.repository import ChatRepository
from app.modules.chat.service import ChatService, user_is_moderator


def get_chat_coordinator() -> ChatCoordinator:
    try:
        return RedisChatCoordinator(redis_manager.get_client())
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "chat_redis_unavailable"},
        ) from exc


def get_chat_service(
    db: Annotated[Session, Depends(get_db)],
    coordinator: Annotated[ChatCoordinator, Depends(get_chat_coordinator)],
) -> ChatService:
    return ChatService(ChatRepository(db), coordinator)


def require_chat_moderator(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user_is_moderator(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "chat_moderator_required"})
    return user
