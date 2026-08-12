# GNTV DIGITAL — Audience Engagement & Live Chat Control Plane (Sprint 7.1 Design)

**Role**: Architecture and Release Director
**Document Status**: APPROVED — READY FOR IMPLEMENTATION
**Target Release**: `v0.8.0` (Sprint 7.1)
**Baseline**: `v0.7.0`

---

## 1. Sprint 7.1 Architecture Blueprint

The Live Chat Control Plane provides real-time, low-latency audience engagement for live broadcasts and events on Global Network TV. It is built as an asynchronous WebSocket control plane operating alongside the existing FastAPI streaming control plane.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Consumer & Studio Clients                       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ WebSocket / REST
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      Nginx Reverse Proxy & SSL                         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ /ws/chat/{room_id}
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               FastAPI ASGI WebSocket Connection Gateway                │
│ ┌──────────────────────┐ ┌───────────────────┐ ┌────────────────────┐ │
│ │ JWT & Auth Guard     │ │ Rate Limiter      │ │ Auto-Moderation    │ │
│ └──────────────────────┘ └───────────────────┘ └────────────────────┘ │
└───────────┬───────────────────────┬──────────────────────┬─────────────┘
            │                       │                      │
            ▼                       ▼                      ▼
┌───────────────────────┐ ┌───────────────────┐ ┌──────────────────────┐
│  Redis Pub/Sub Fanout │ │ Redis ZSET        │ │ PostgreSQL DB Async  │
│  (Cross-Pod Broadcast)│ │ (Presence & Rate) │ │ (Persistence & Audit)│
└───────────────────────┘ └───────────────────┘ └──────────────────────┘
```

### Connection & Lifecycle Pipeline
1. **Handshake & Auth**: Client connects to `WS /ws/chat/{room_id}?token={jwt}`. Gateway validates signature & expiration.
2. **Room Join & Presence**: Connection registered in room socket set; presence counter incremented in Redis ZSET.
3. **Message Loop**: Client sends message payload $\rightarrow$ Rate limiter check $\rightarrow$ Regex moderation $\rightarrow$ Persisted to PostgreSQL $\rightarrow$ Published to Redis Pub/Sub `chat:pubsub:{room_id}`.
4. **Cross-Pod Fanout**: All backend nodes subscribed to `chat:pubsub:{room_id}` receive message and broadcast to local client sockets.
5. **Disconnect & Reconnect**: On socket drop, presence decremented; client attempts reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s).

---

## 2. Database Design

Alembic Migration (`202608121200_module7_sprint71_live_chat.py`):

```sql
CREATE TABLE chat_rooms (
    id CHAR(32) PRIMARY KEY,
    live_channel_id CHAR(32) REFERENCES live_channels(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active', -- active, read_only, closed
    slow_mode_seconds INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE chat_messages (
    id CHAR(32) PRIMARY KEY,
    room_id CHAR(32) NOT NULL REFERENCES chat_rooms(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id) ON DELETE SET NULL,
    username VARCHAR(100) NOT NULL,
    message_text TEXT NOT NULL,
    client_msg_id CHAR(36) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'published', -- published, flagged, deleted
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE chat_moderation_rules (
    id CHAR(32) PRIMARY KEY,
    pattern VARCHAR(255) NOT NULL,
    match_type VARCHAR(20) NOT NULL DEFAULT 'regex', -- regex, exact, fuzzy
    action VARCHAR(20) NOT NULL DEFAULT 'block', -- block, flag, mute
    created_by INT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE chat_user_states (
    id CHAR(32) PRIMARY KEY,
    room_id CHAR(32) NOT NULL REFERENCES chat_rooms(id) ON DELETE CASCADE,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_muted BOOLEAN NOT NULL DEFAULT FALSE,
    muted_until TIMESTAMP WITH TIME ZONE,
    is_banned BOOLEAN NOT NULL DEFAULT FALSE,
    banned_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(room_id, user_id)
);

CREATE TABLE chat_moderation_audit (
    id CHAR(32) PRIMARY KEY,
    room_id CHAR(32) NOT NULL REFERENCES chat_rooms(id) ON DELETE CASCADE,
    moderator_id INT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    target_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(50) NOT NULL,
    reason VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chat_messages_room_time ON chat_messages(room_id, created_at DESC);
CREATE INDEX idx_chat_user_states_room_user ON chat_user_states(room_id, user_id);
```

---

## 3. Redis Design

- **Pub/Sub Channel**: `chat:pubsub:{room_id}` for real-time cross-pod message fanout.
- **Presence ZSET**: `chat:presence:{room_id}` (member = `user_id`, score = `epoch_timestamp`).
- **Rate Limit Counter**: `chat:ratelimit:{user_id}:{room_id}` (key expire 5s; max 5 messages per 5s).
- **Deduplication Set**: `chat:dedup:{room_id}` storing `client_msg_id` (TTL = 60s).
- **Connection Pool**: Asyncio Redis Pool (`max_connections=100`, `socket_timeout=2.0`).

---

## 4. WebSocket Contract

### Protocol: JSON Over Text WebSocket
**Endpoint**: `WS /ws/chat/{room_id}?token={jwt}`

#### Client $\rightarrow$ Server: Send Message
```json
{
  "type": "send_message",
  "client_msg_id": "c7a2b9f0-1234-4567-89ab-cdef01234567",
  "text": "Hello GNTV live broadcast!"
}
```

#### Server $\rightarrow$ Client: Broadcast Message
```json
{
  "type": "chat_message",
  "id": "msg_90123456789",
  "room_id": "room_0123456789",
  "user_id": 42,
  "username": "Athero",
  "text": "Hello GNTV live broadcast!",
  "client_msg_id": "c7a2b9f0-1234-4567-89ab-cdef01234567",
  "timestamp_ms": 1770734000000
}
```

#### Server $\rightarrow$ Client: Presence Update
```json
{
  "type": "presence_update",
  "room_id": "room_0123456789",
  "active_viewers": 1420
}
```

#### Server $\rightarrow$ Client: Moderation Notice / Action
```json
{
  "type": "moderation_notice",
  "action": "message_deleted",
  "target_msg_id": "msg_90123456789",
  "reason": "Content violated community guidelines"
}
```

---

## 5. REST Contract

- `POST /api/v1/chat/rooms` — Create or update room configuration (`slow_mode_seconds`, `status`).
- `GET /api/v1/chat/rooms/{room_id}/messages?limit=50&before_id={id}` — Fetch historical messages.
- `POST /api/v1/chat/rooms/{room_id}/moderation/action` — Execute moderator action (`mute`, `ban`, `delete`).
- `GET /api/v1/chat/rooms/{room_id}/moderation/rules` — List active moderation regex rules.
- `POST /api/v1/chat/rooms/{room_id}/moderation/rules` — Add new moderation rule.
- `GET /api/v1/chat/health` — Readiness & Gateway connection status.

---

## 6. Frontend Architecture

### Consumer (`LiveChatOverlay.js`)
- Renders collapsible overlay over `LivePlayer.js`.
- Maintains WebSocket state machine (`CONNECTING`, `CONNECTED`, `RECONNECTING`, `DISCONNECTED`).
- Implements optimistic UI rendering with `sending`, `sent`, and `failed` status pills.
- HTML entity escaping to prevent XSS.
- Full D-Pad arrow key navigation for Smart TV remotes.
- ARIA live region (`aria-live="polite"`) for screen readers.

### Studio (`ChatModerationConsole.js`)
- Real-time stream of incoming messages across channels.
- Quick action controls: Mute User (5m, 1h, 24h), Ban User, Delete Message.
- Live rule editor for instant pattern blocking.

---

## 7. Moderation Model

- **Automated Regex Pre-Filter**: Scans message text before DB persistence. Matched messages are auto-blocked or flagged.
- **Spam & Duplication Filter**: Drops duplicate `client_msg_id` or identical text sent within 10 seconds.
- **Rate Limit & Slow Mode**: Enforces `slow_mode_seconds` delay between messages per user.
- **Fail-Closed Security**: If moderation engine or Redis lookup fails, message status defaults to `flagged` pending manual producer approval.

---

## 8. Scaling & Performance Plan

- **Target Capacity**: $10,000+$ concurrent WebSocket connections per node.
- **Latency Targets**: p95 $<50\text{ms}$, p99 $<100\text{ms}$ message propagation.
- **Backpressure Strategy**: Maximum WS frame size = 4KB; client buffer capped at 50 messages.
- **Redis Bottleneck Mitigation**: Redis Pub/Sub channels sharded by `room_id`.

---

## 9. Test Plan

1. **Unit Tests**:
   - `test_chat_moderation_rules.py`: Test exact, regex, and fuzzy pattern matches.
   - `test_chat_rate_limiter.py`: Verify sliding window counter limits.
   - `test_chat_schemas.py`: Validate WS envelope serialization.
2. **Integration Tests**:
   - `test_chat_websocket_lifecycle.py`: Test connect, auth, message broadcast, presence updates, and disconnects.
3. **Concurrency & Load Tests**:
   - Load test script simulating 1,000 to 10,000 WebSocket connections broadcasting messages simultaneously.
4. **Security Tests**:
   - XSS script tag injection payloads (`<script>alert(1)</script>`).
   - Expired or forged JWT connection rejection.

---

## 10. Risks & Mitigations

- **Risk**: WebSocket connection memory leakage on ungraceful client disconnects.
  **Mitigation**: Gateway enforces 60-second ping/pong heartbeat interval; inactive sockets auto-closed.
- **Risk**: High Pub/Sub message volume overwhelming single Redis instance.
  **Mitigation**: Room channels partitioned across Redis cluster nodes.

---

## 11. Acceptance Criteria

- All unit and integration tests pass with **Coverage $\ge 90.0\%$**.
- WebSocket message broadcast latency remains $<100\text{ms}$ under load.
- Automated regex moderation blocks prohibited keywords in $<5\text{ms}$.
- Frontend moderation console in `frontend-studio` executes mute/ban actions in real time across all nodes.

---

## 12. Release Blockers

- Failing Pytest unit tests or MyPy static type errors.
- Unsanitized HTML rendering causing XSS risks.
- WebSocket memory leaks under connection cycling tests.
