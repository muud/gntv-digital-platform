"""Module 7 Sprint 7.1 live chat control-plane tests."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
import importlib.util
from pathlib import Path
from typing import Any
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Table, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.core.database import Base, get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.auth_extra import EmailVerification, FailedLoginAttempt, PasswordReset, RefreshToken
from app.models.user import Device, Permission, Profile, Role, User, UserSession, role_permissions, user_roles
from app.modules.chat.dependencies import get_chat_coordinator
from app.modules.chat.models import (
    ChatMessage,
    ChatMessageStatus,
    ChatModerationAction,
    ChatModerationAudit,
    ChatModerationRule,
    ChatRoom,
    ChatRoomStatus,
    ChatUserState,
)
from app.modules.chat.redis_coordination import (
    InMemoryChatCoordinator,
    chat_dedup_key,
    chat_presence_key,
    chat_pubsub_key,
    chat_ratelimit_key,
)
from app.modules.chat.repository import ChatRepository
from app.modules.chat.schemas import SendMessageEnvelope
from app.modules.chat.service import ChatService
from app.utils.jwt import create_access_token
from app.utils.security import hash_password


CHAT_TABLES: list[Table] = [
    User.__table__,
    Profile.__table__,
    Role.__table__,
    Permission.__table__,
    user_roles,
    role_permissions,
    Device.__table__,
    UserSession.__table__,
    EmailVerification.__table__,
    PasswordReset.__table__,
    RefreshToken.__table__,
    FailedLoginAttempt.__table__,
    AuditLog.__table__,
    ChatRoom.__table__,
    ChatMessage.__table__,
    ChatModerationRule.__table__,
    ChatUserState.__table__,
    ChatModerationAudit.__table__,
]


@pytest.fixture()
def chat_coordinator() -> InMemoryChatCoordinator:
    return InMemoryChatCoordinator()


@pytest.fixture()
def chat_db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=CHAT_TABLES)
    local_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = local_session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine, tables=reversed(CHAT_TABLES))
        engine.dispose()


@pytest.fixture()
def chat_client(chat_db: Session, chat_coordinator: InMemoryChatCoordinator) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield chat_db
            chat_db.commit()
        except Exception:
            chat_db.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_chat_coordinator] = lambda: chat_coordinator
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def create_user(db: Session, email: str, role_name: str = "viewer") -> User:
    role = db.query(Role).filter_by(name=role_name).one_or_none()
    if role is None:
        role = Role(name=role_name, description=f"{role_name} role")
        db.add(role)
        db.flush()
    user = User(email=email, hashed_password=hash_password("StrongPass123"), is_active=True, is_verified=True)
    user.roles.append(role)
    user.name = email.split("@", maxsplit=1)[0].title()
    db.add(user)
    db.commit()
    return user


def token_for(user: User) -> str:
    return create_access_token(subject=str(user.id), additional_claims={"email": user.email})


def create_room(db: Session, *, slow_mode_seconds: int = 0) -> ChatRoom:
    room = ChatRoom(name="GNTV Live Chat", status=ChatRoomStatus.ACTIVE, slow_mode_seconds=slow_mode_seconds)
    db.add(room)
    db.commit()
    return room


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(user)}"}


def receive_type(socket: Any, expected: str, attempts: int = 5) -> dict[str, Any]:
    for _ in range(attempts):
        event = socket.receive_json()
        if event["type"] == expected:
            return event
    raise AssertionError(f"Did not receive {expected}")


def test_room_creation(chat_client: TestClient, chat_db: Session) -> None:
    admin = create_user(chat_db, "admin@example.com", "admin")

    response = chat_client.post(
        "/api/v1/chat/rooms",
        headers=auth_headers(admin),
        json={"name": "Election Night", "slow_mode_seconds": 3},
    )

    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Election Night"
    assert chat_db.query(ChatRoom).count() == 1


def test_message_persistence(chat_db: Session, chat_coordinator: InMemoryChatCoordinator) -> None:
    user = create_user(chat_db, "viewer@example.com")
    room = create_room(chat_db)
    service = ChatService(ChatRepository(chat_db), chat_coordinator)

    result = asyncio.run(
        service.receive_message(
            room.id,
            user,
            SendMessageEnvelope(type="send_message", client_msg_id="one", text="Hello Africa"),
        )
    )

    assert result.text == "Hello Africa"
    assert chat_db.query(ChatMessage).filter_by(room_id=room.id).one().message_text == "Hello Africa"


def test_websocket_auth_failure(chat_client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with chat_client.websocket_connect(f"/ws/chat/{uuid4()}?token=bad-token"):
            pass


def test_successful_message_broadcast(chat_client: TestClient, chat_db: Session) -> None:
    user = create_user(chat_db, "viewer@example.com")
    room = create_room(chat_db)

    with chat_client.websocket_connect(f"/ws/chat/{room.id}?token={token_for(user)}") as socket:
        receive_type(socket, "presence_update")
        socket.send_json({"type": "send_message", "client_msg_id": "broadcast-1", "text": "We are live"})
        message = receive_type(socket, "chat_message")

    assert message["text"] == "We are live"
    assert message["client_msg_id"] == "broadcast-1"


def test_duplicate_client_msg_id(chat_client: TestClient, chat_db: Session) -> None:
    user = create_user(chat_db, "viewer@example.com")
    room = create_room(chat_db)

    with chat_client.websocket_connect(f"/ws/chat/{room.id}?token={token_for(user)}") as socket:
        receive_type(socket, "presence_update")
        socket.send_json({"type": "send_message", "client_msg_id": "dup-1", "text": "First"})
        receive_type(socket, "chat_message")
        socket.send_json({"type": "send_message", "client_msg_id": "dup-1", "text": "Duplicate"})
        notice = receive_type(socket, "moderation_notice")

    assert notice["action"] == "message_held"
    assert chat_db.query(ChatMessage).filter_by(room_id=room.id).count() == 1


def test_rate_limiting(chat_client: TestClient, chat_db: Session) -> None:
    user = create_user(chat_db, "viewer@example.com")
    room = create_room(chat_db)

    with chat_client.websocket_connect(f"/ws/chat/{room.id}?token={token_for(user)}") as socket:
        receive_type(socket, "presence_update")
        for index in range(5):
            socket.send_json({"type": "send_message", "client_msg_id": f"rate-{index}", "text": f"msg {index}"})
            receive_type(socket, "chat_message")
        socket.send_json({"type": "send_message", "client_msg_id": "rate-6", "text": "too fast"})
        error = receive_type(socket, "error")

    assert error["code"] == "chat_rate_limited"


def test_slow_mode(chat_client: TestClient, chat_db: Session) -> None:
    user = create_user(chat_db, "viewer@example.com")
    room = create_room(chat_db, slow_mode_seconds=30)

    with chat_client.websocket_connect(f"/ws/chat/{room.id}?token={token_for(user)}") as socket:
        receive_type(socket, "presence_update")
        socket.send_json({"type": "send_message", "client_msg_id": "slow-1", "text": "First"})
        receive_type(socket, "chat_message")
        socket.send_json({"type": "send_message", "client_msg_id": "slow-2", "text": "Second"})
        error = receive_type(socket, "error")

    assert error["code"] == "chat_slow_mode"


def test_regex_block(chat_client: TestClient, chat_db: Session) -> None:
    admin = create_user(chat_db, "admin@example.com", "admin")
    viewer = create_user(chat_db, "viewer@example.com")
    room = create_room(chat_db)
    chat_client.post(
        f"/api/v1/chat/rooms/{room.id}/moderation/rules",
        headers=auth_headers(admin),
        json={"pattern": "forbidden\\s+word", "match_type": "regex", "action": "block"},
    )

    with chat_client.websocket_connect(f"/ws/chat/{room.id}?token={token_for(viewer)}") as socket:
        receive_type(socket, "presence_update")
        socket.send_json({"type": "send_message", "client_msg_id": "block-1", "text": "forbidden word"})
        notice = receive_type(socket, "moderation_notice")

    assert notice["action"] == "message_held"
    assert chat_db.query(ChatMessage).filter_by(status=ChatMessageStatus.BLOCKED).count() == 1


def test_flag_behavior(chat_client: TestClient, chat_db: Session) -> None:
    admin = create_user(chat_db, "admin@example.com", "admin")
    viewer = create_user(chat_db, "viewer@example.com")
    room = create_room(chat_db)
    chat_client.post(
        f"/api/v1/chat/rooms/{room.id}/moderation/rules",
        headers=auth_headers(admin),
        json={"pattern": "review me", "match_type": "exact", "action": "flag"},
    )

    with chat_client.websocket_connect(f"/ws/chat/{room.id}?token={token_for(viewer)}") as socket:
        receive_type(socket, "presence_update")
        socket.send_json({"type": "send_message", "client_msg_id": "flag-1", "text": "please review me"})
        notice = receive_type(socket, "moderation_notice")

    assert notice["action"] == "message_flagged"
    assert chat_db.query(ChatMessage).filter_by(status=ChatMessageStatus.FLAGGED).count() == 1


def test_mute_and_ban(chat_client: TestClient, chat_db: Session) -> None:
    admin = create_user(chat_db, "admin@example.com", "admin")
    viewer = create_user(chat_db, "viewer@example.com")
    room = create_room(chat_db)

    mute = chat_client.post(
        f"/api/v1/chat/rooms/{room.id}/moderation/action",
        headers=auth_headers(admin),
        json={"action": "mute", "target_user_id": viewer.id, "duration_seconds": 60, "reason": "spam"},
    )
    ban = chat_client.post(
        f"/api/v1/chat/rooms/{room.id}/moderation/action",
        headers=auth_headers(admin),
        json={"action": "ban", "target_user_id": viewer.id, "reason": "abuse"},
    )

    state = chat_db.query(ChatUserState).filter_by(room_id=room.id, user_id=viewer.id).one()
    assert mute.status_code == 201
    assert ban.status_code == 201
    assert state.is_muted is True
    assert state.is_banned is True
    assert chat_db.query(ChatModerationAudit).count() == 2


def test_delete_and_moderation_audit(chat_client: TestClient, chat_db: Session, chat_coordinator: InMemoryChatCoordinator) -> None:
    admin = create_user(chat_db, "admin@example.com", "admin")
    viewer = create_user(chat_db, "viewer@example.com")
    room = create_room(chat_db)
    service = ChatService(ChatRepository(chat_db), chat_coordinator)
    message = asyncio.run(
        service.receive_message(
            room.id,
            viewer,
            SendMessageEnvelope(type="send_message", client_msg_id="delete-1", text="delete me"),
        )
    )
    chat_db.commit()

    response = chat_client.post(
        f"/api/v1/chat/rooms/{room.id}/moderation/action",
        headers=auth_headers(admin),
        json={"action": "delete", "target_message_id": str(message.id), "reason": "cleanup"},
    )

    assert response.status_code == 201
    assert chat_db.get(ChatMessage, message.id).status == ChatMessageStatus.DELETED
    assert response.json()["action"] == "delete"


def test_malformed_payload_and_payload_too_large(chat_client: TestClient, chat_db: Session) -> None:
    user = create_user(chat_db, "viewer@example.com")
    room = create_room(chat_db)

    with chat_client.websocket_connect(f"/ws/chat/{room.id}?token={token_for(user)}") as socket:
        receive_type(socket, "presence_update")
        socket.send_text("{not-json")
        malformed = receive_type(socket, "error")
        socket.send_json({"type": "send_message", "client_msg_id": "large-1", "text": "x" * 5000})
        too_large = receive_type(socket, "error")

    assert malformed["code"] == "malformed_json"
    assert too_large["code"] == "payload_too_large"


@pytest.mark.anyio
async def test_redis_failure_behavior(chat_db: Session, chat_coordinator: InMemoryChatCoordinator) -> None:
    user = create_user(chat_db, "viewer@example.com")
    room = create_room(chat_db)
    chat_coordinator.fail_publish = True

    result = await ChatService(ChatRepository(chat_db), chat_coordinator).receive_message(
        room.id,
        user,
        SendMessageEnvelope(type="send_message", client_msg_id="redis-fail", text="hold me"),
    )

    message = chat_db.query(ChatMessage).filter_by(client_msg_id="redis-fail").one()
    assert result is None
    assert message.status == ChatMessageStatus.FLAGGED
    assert chat_db.query(ChatModerationAudit).filter_by(action=ChatModerationAction.FLAG).count() == 1


def test_reconnect_presence_lifecycle(chat_client: TestClient, chat_db: Session, chat_coordinator: InMemoryChatCoordinator) -> None:
    user = create_user(chat_db, "viewer@example.com")
    room = create_room(chat_db)

    with chat_client.websocket_connect(f"/ws/chat/{room.id}?token={token_for(user)}") as socket:
        presence = receive_type(socket, "presence_update")
        assert presence["active_viewers"] == 1
    assert chat_coordinator.presence[room.id] == {}
    with chat_client.websocket_connect(f"/ws/chat/{room.id}?token={token_for(user)}") as socket:
        presence = receive_type(socket, "presence_update")
        socket.send_json({"type": "heartbeat"})
        pong = receive_type(socket, "pong")

    assert presence["active_viewers"] == 1
    assert pong["type"] == "pong"


def test_xss_payload_treated_as_text(chat_client: TestClient, chat_db: Session) -> None:
    user = create_user(chat_db, "viewer@example.com")
    room = create_room(chat_db)
    payload = "<script>alert(1)</script>"

    with chat_client.websocket_connect(f"/ws/chat/{room.id}?token={token_for(user)}") as socket:
        receive_type(socket, "presence_update")
        socket.send_json({"type": "send_message", "client_msg_id": "xss-1", "text": payload})
        message = receive_type(socket, "chat_message")

    assert message["text"] == payload
    assert chat_db.query(ChatMessage).filter_by(message_text=payload).count() == 1


def test_redis_key_names() -> None:
    room_id = uuid4()
    assert chat_pubsub_key(room_id) == f"chat:pubsub:{room_id}"
    assert chat_presence_key(room_id) == f"chat:presence:{room_id}"
    assert chat_ratelimit_key(7, room_id) == f"chat:ratelimit:7:{room_id}"
    assert chat_dedup_key(room_id) == f"chat:dedup:{room_id}"


def test_sprint71_openapi_paths_exist() -> None:
    schema = app.openapi()
    assert "/api/v1/chat/rooms" in schema["paths"]
    assert "/api/v1/chat/rooms/{room_id}/messages" in schema["paths"]
    assert "/api/v1/chat/rooms/{room_id}/moderation/action" in schema["paths"]
    assert "/api/v1/chat/rooms/{room_id}/moderation/rules" in schema["paths"]


def test_sprint71_migration_upgrade_and_downgrade_on_isolated_database() -> None:
    migration_path = Path(__file__).parents[1] / "alembic/versions/202608121200_module7_sprint71_live_chat.py"
    spec = importlib.util.spec_from_file_location("sprint71_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    connection = engine.connect()
    connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
    connection.execute(text("CREATE TABLE live_channels (id CHAR(32) PRIMARY KEY)"))
    context = MigrationContext.configure(connection)
    original_op = module.op
    module.op = Operations(context)
    try:
        module.upgrade()
        inspector = inspect(connection)
        assert {"chat_rooms", "chat_messages", "chat_moderation_rules", "chat_user_states", "chat_moderation_audit"} <= set(
            inspector.get_table_names()
        )
        module.downgrade()
        assert "chat_rooms" not in inspect(connection).get_table_names()
    finally:
        module.op = original_op
        connection.close()
        engine.dispose()
