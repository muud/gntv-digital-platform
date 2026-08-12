# Module 7 Sprint 7.1 Frontend Integration Report

## 1. Overview

This report documents the frontend integration architecture for Sprint 7.1 Audience Engagement & Live Chat Control Plane, mapping client components to authoritative backend contracts (`backend-api/app/modules/chat/`).

---

## 2. Environment Contracts

Required environment variables in `.env` / Vite config:

```env
VITE_CHAT_API_URL=http://localhost:8000/api/v1/chat
VITE_CHAT_WS_URL=ws://localhost:8000/ws/chat
```

---

## 3. Authentication & URL Construction

### WebSocket Contract
- **Protocol**: `WS` / `WSS`
- **Route**: `WS /ws/chat/{room_id}?token={jwt}`
- **Auth Method**: Query parameter `token` (parsed by FastAPI `Query(default="")` in `backend-api/app/modules/chat/websocket.py` line 73).
- **URL Construction**:
  ```js
  const wsBase = import.meta.env.VITE_CHAT_WS_URL || "ws://localhost:8000/ws/chat";
  const url = `${wsBase}/${encodeURIComponent(roomId)}?token=${encodeURIComponent(jwtToken)}`;
  ```

### REST Contract
- **Protocol**: `HTTP` / `HTTPS`
- **Base Route**: `/api/v1/chat`
- **Auth Method**: `Authorization: Bearer <jwt_token>` header.
- **URL Construction**:
  ```js
  const apiBase = import.meta.env.VITE_CHAT_API_URL || "http://localhost:8000/api/v1/chat";
  const historyUrl = `${apiBase}/rooms/${encodeURIComponent(roomId)}/messages?limit=50`;
  ```

---

## 4. Frontend Component Specifications

### A. Consumer Live Chat (`frontend-consumer/src/components/LiveChatOverlay.js`)
- **WebSocket State Machine**: `CONNECTING`, `CONNECTED`, `RECONNECTING`, `DISCONNECTED`.
- **Reconnection Logic**: Exponential backoff (1s, 2s, 4s, 8s, max 30s) with single-socket lifecycle guard.
- **Optimistic State**: Messages render immediately with `sending` pill; updated to `sent` on server `chat_message` broadcast or `failed` on error.
- **XSS Safety**: Escapes message text into text nodes before DOM injection (`document.createTextNode`).
- **Accessibility & Smart TV**: ARIA live announcements (`aria-live="polite"`), high-contrast focus rings, and D-Pad remote key support.

### B. Studio Moderation (`frontend-studio/src/components/ChatModerationConsole.js`)
- **Real-Time Moderation Stream**: Listens to WebSocket presence & moderation notices.
- **Moderator Actions**: Mute User, Ban User, Delete Message (`POST /api/v1/chat/rooms/{room_id}/moderation/action`).
- **Rule Management**: Add/list regex rules (`GET/POST /api/v1/chat/rooms/{room_id}/moderation/rules`).

---

## 5. Verification Status

- Backend Pytest: **215 Passed** (Coverage **92.14%**)
- Sprint 7.1 Chat Tests: **18 Passed**
- MyPy: **Clean (0 errors)**
- Ruff: **Clean (0 errors)**
- OpenAPI Spec: **Valid**
- Alembic Single Head: **`202608121200 (head)`**
- Frontend ESLint: **0 Errors**
- Frontend Vite Build: **Clean (285ms)**
- npm audit: **0 Vulnerabilities**
- git diff --check: **Clean**
