"""WebSocket gateway for Module 7 Sprint 7.1 live chat."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.modules.chat.repository import ChatRepository
from app.modules.chat.schemas import ErrorEnvelope, ModerationNoticeEnvelope, PongEnvelope, PresenceUpdateEnvelope, SendMessageEnvelope
from app.modules.chat.service import ChatService
from app.modules.chat.redis_coordination import ChatCoordinator
from app.modules.chat.dependencies import get_chat_coordinator
from app.utils.jwt import decode_token

MAX_WS_PAYLOAD_BYTES = 4096

router = APIRouter(tags=["Audience Live Chat"])


class ChatConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[UUID, set[WebSocket]] = defaultdict(set)

    async def connect(self, room_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._rooms[room_id].add(websocket)

    def disconnect(self, room_id: UUID, websocket: WebSocket) -> None:
        self._rooms[room_id].discard(websocket)
        if not self._rooms[room_id]:
            self._rooms.pop(room_id, None)

    async def broadcast(self, room_id: UUID, event: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for socket in tuple(self._rooms.get(room_id, ())):
            try:
                await socket.send_json(event)
            except Exception:
                stale.append(socket)
        for socket in stale:
            self.disconnect(room_id, socket)


manager = ChatConnectionManager()


def websocket_user(token: str, db: Session) -> User | None:
    try:
        payload = decode_token(token)
        subject = payload.get("sub")
        if subject is None:
            return None
        user = db.get(User, int(subject))
    except Exception:
        return None
    if user is None or not user.is_active or not user.email_verified:
        return None
    return user


@router.websocket("/ws/chat/{room_id}")
async def chat_websocket(
    websocket: WebSocket,
    room_id: UUID,
    token: str = Query(default=""),
    db: Session = Depends(get_db),
    coordinator: ChatCoordinator = Depends(get_chat_coordinator),
) -> None:
    user = websocket_user(token, db)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    service = ChatService(ChatRepository(db), coordinator)
    try:
        active_viewers = await service.join_room(room_id, user)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(room_id, websocket)
    await manager.broadcast(room_id, PresenceUpdateEnvelope(room_id=room_id, active_viewers=active_viewers).model_dump(mode="json"))
    try:
        while True:
            raw_payload = await websocket.receive_text()
            if len(raw_payload.encode("utf-8")) > MAX_WS_PAYLOAD_BYTES:
                await websocket.send_json(
                    ErrorEnvelope(code="payload_too_large", message="Chat payload exceeds 4KB").model_dump(mode="json")
                )
                continue
            try:
                body = json.loads(raw_payload)
            except json.JSONDecodeError:
                await websocket.send_json(ErrorEnvelope(code="malformed_json", message="Invalid JSON").model_dump(mode="json"))
                continue
            if body.get("type") == "heartbeat":
                viewers = await coordinator.heartbeat_presence(room_id, user.id)
                await websocket.send_json(PongEnvelope().model_dump(mode="json"))
                await manager.broadcast(
                    room_id,
                    PresenceUpdateEnvelope(room_id=room_id, active_viewers=viewers).model_dump(mode="json"),
                )
                continue
            try:
                envelope = SendMessageEnvelope.model_validate(body)
                result = await service.receive_message(room_id, user, envelope)
                db.commit()
            except ValidationError:
                db.rollback()
                await websocket.send_json(ErrorEnvelope(code="malformed_payload", message="Unsupported chat envelope").model_dump(mode="json"))
                continue
            except HTTPException as exc:
                db.rollback()
                detail = exc.detail if isinstance(exc.detail, dict) else {"code": "chat_error"}
                await websocket.send_json(
                    ErrorEnvelope(code=str(detail.get("code", "chat_error")), message="Chat message rejected").model_dump(mode="json")
                )
                continue
            if result is None:
                await websocket.send_json(
                    ModerationNoticeEnvelope(action="message_held", reason="Message was not published").model_dump(mode="json")
                )
            elif result.status == "flagged":
                await websocket.send_json(
                    ModerationNoticeEnvelope(
                        action="message_flagged",
                        target_msg_id=result.id,
                        reason="Message is pending moderator review",
                    ).model_dump(mode="json")
                )
            else:
                await manager.broadcast(room_id, result.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(room_id, websocket)
        viewers = await service.leave_room(room_id, user)
        await manager.broadcast(room_id, PresenceUpdateEnvelope(room_id=room_id, active_viewers=viewers).model_dump(mode="json"))
