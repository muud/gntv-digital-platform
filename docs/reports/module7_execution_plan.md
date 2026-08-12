# GNTV DIGITAL — Platform Expansion Execution Plan (Module 7)

**Role**: Architecture and Release Director
**Document Status**: APPROVED — READY FOR KICKOFF
**Target Release**: `v0.8.0`
**Current Baseline**: `v0.7.0`
**Release Plan**: Sprints 7.1 to 7.7

---

## 1. Module 7 Objectives

Module 7 (Platform Expansion) advances the Global Network TV (GNTV) Digital Broadcasting Platform from a core live/VOD streaming service (`v0.7.0`) into an enterprise-grade, monetized, interactive, and multi-tenant broadcast ecosystem (`v0.8.0`).

Key Strategic Objectives:
1. **Interactive Viewer Engagement**: Deliver real-time WebSocket audience chat, live reactions, interactive polls, and automated AI/regex chat moderation.
2. **Monetization & Server-Side Ad Insertion (SSAI)**: Enable AVOD and FAST channel monetization via VAST/VMAP manifest stitching, SCTE-35 marker parsing, and client/server ad impression tracking.
3. **Global Multi-CDN & Edge Acceleration**: Integrate Alibaba DCDN dynamic route acceleration, edge token verification, and multi-region failover.
4. **Personalized Curation & Recommendation Engine**: Implement watch-history collaborative filtering and personalized dynamic linear EPG feeds.
5. **Executive Analytics & Broadcaster Control Panel**: Provide real-time concurrency heatmaps, QoE metrics, and ad revenue analytics in `frontend-studio`.
6. **Multi-Tenant Syndication & B2B Distribution**: Enable white-label iframe embeds, domain-restricted partner licensing, and B2B distribution APIs.

---

## 2. Recommended Scope

The scope of Module 7 includes six operational sub-domains executed across Sprints 7.1 through 7.7:

1. **Real-time Live Chat & Audience Interaction Control Plane** (`app/modules/chat`)
2. **Server-Side Ad Insertion & FAST Packaging** (`app/modules/monetization`)
3. **Alibaba DCDN & Edge Acceleration Routing** (`app/modules/cdn`)
4. **Recommendation & Personalization Engine** (`app/modules/recommendation`)
5. **Broadcaster Analytics & Real-Time Executive Dashboard** (`app/modules/analytics`)
6. **Multi-Tenant Partner Distribution & Embed SDK** (`app/modules/syndication`)

---

## 3. Sprint Breakdown

### Sprint 7.1 — Real-Time Audience Engagement & Live Chat
- **Backend**:
  - Implement WebSocket endpoint `/ws/chat/{room_id}` with Redis Pub/Sub multi-node message fanout.
  - Create chat persistence repository (`chat_messages`, `chat_rooms`, `chat_moderation_rules`).
  - Implement automated keyword filtering and rate-limiting middleware.
- **Frontend**:
  - Build `LiveChatOverlay.js` in `frontend-consumer` with message history, emojis, and live polls.
  - Implement chat moderation controls in `frontend-studio`.

### Sprint 7.2 — Server-Side Ad Insertion (SSAI) & FAST Channels
- **Backend**:
  - Implement VAST/VMAP XML parser and SCTE-35 marker reader.
  - Build dynamic manifest stitcher injecting ad segment URLs into HLS master/variant playlists (`ssai/playlist.m3u8`).
  - Register `/api/v1/monetization/beacon` for ad impression and completion tracking.
- **Frontend**:
  - Integrate ad UI indicators (non-clickable ad countdowns, ad marker ticks on timeline) in `LivePlayer.js`.

### Sprint 7.3 — Global Multi-CDN Edge Acceleration & Failover
- **Backend**:
  - Integrate Alibaba DCDN dynamic edge token signature generator.
  - Implement secondary CDN origin failover switcher (`CdnRoutingService`).
- **Frontend**:
  - Implement automatic CDN origin fallback on stream stall/manifest fetch error.

### Sprint 7.4 — Personalized Recommendations & EPG Curation
- **Backend**:
  - Build watch history vector embedding lookup for user recommendations.
  - Implement personalized linear channel builder (`GET /api/v1/catalog/personalized-epg`).
- **Frontend**:
  - Render "Recommended For You" carousel and personalized channel rail on consumer dashboard.

### Sprint 7.5 — Executive Analytics & Broadcaster Control Dashboard
- **Backend**:
  - Implement real-time concurrency aggregator aggregating Redis session metrics.
  - Build revenue and ad impression analytics API (`GET /api/v1/analytics/executive-summary`).
- **Frontend**:
  - Build interactive charts (ECharts / Chart.js) in `frontend-studio` displaying concurrency heatmaps and revenue metrics.

### Sprint 7.6 — Multi-Tenant Partner Syndication & Embed SDK
- **Backend**:
  - Create `SyndicationPartner` model and API key domain restriction validator.
  - Register signed iframe embed token generator (`POST /api/v1/syndication/embed-token`).
- **Frontend**:
  - Build lightweight `EmbedPlayerSDK.js` for third-party websites with partner branding.

### Sprint 7.7 — Integration, Hardening & Release Candidate `v0.8.0-rc1`
- **Backend/Frontend**:
  - Full test suite execution (targeting 220+ tests with $\ge 90\%$ coverage).
  - Load test WebSocket gateway under 10,000+ concurrent connections.
  - OpenAPI spec compilation check and Alembic single head validation.

---

## 4. Architecture Boundaries

```
[ Consumer Client / Smart TV / Embed SDK ]
            │
            ▼
   [ Alibaba DCDN / Edge ] ──(Static / HLS Segment Caching)
            │
            ▼
     [ Nginx Reverse Proxy ]
            │
    ┌───────┴───────────────────────────┐
    ▼                                   ▼
[ FastAPI Control Plane (REST) ]   [ FastAPI ASGI WebSocket (Chat) ]
    │                                   │
    ├─ Monetization (SSAI / SCTE-35)    ├─ Redis Pub/Sub (Fanout)
    ├─ Analytics & Recommendations      └─ PostgreSQL (Persistence)
    └─ Syndication & Partner Auth
```

---

## 5. Database Impact

New Database Tables (Alembic Migration `202608121200_module7_platform_expansion.py`):
1. `chat_rooms`: `id` (UUID PK), `live_channel_id` (FK), `name`, `status`, `created_at`.
2. `chat_messages`: `id` (UUID PK), `room_id` (FK), `user_id` (FK), `message_text`, `is_flagged`, `created_at`.
3. `chat_moderation_rules`: `id` (UUID PK), `pattern`, `action`, `is_active`.
4. `ad_campaigns`: `id` (UUID PK), `name`, `vast_tag_url`, `start_time`, `end_time`, `status`.
5. `ad_impressions`: `id` (UUID PK), `campaign_id` (FK), `session_id` (FK), `event_type`, `timestamp`.
6. `syndication_partners`: `id` (UUID PK), `name`, `api_key_hash`, `allowed_domains` (JSON), `status`.

---

## 6. API Impact

- **WebSocket**:
  - `WS /ws/chat/{room_id}?token={jwt}`
- **REST Endpoints**:
  - `GET /api/v1/chat/rooms/{room_id}/messages`
  - `POST /api/v1/chat/messages/{message_id}/flag`
  - `GET /api/v1/monetization/manifest/{target_id}/ssai.m3u8`
  - `POST /api/v1/monetization/beacon`
  - `GET /api/v1/analytics/broadcaster/concurrency`
  - `POST /api/v1/syndication/embed-token`

---

## 7. Frontend Impact

- `frontend-consumer`:
  - New `LiveChatOverlay.js` component with real-time WebSocket messaging.
  - SSAI ad overlay UI (ad countdown, non-clickable state during ad breaks).
- `frontend-studio`:
  - `BroadcasterDashboard.js` for live event concurrency heatmaps and revenue analytics.
  - `ChatModerationConsole.js` for broadcast producers to mute/ban users and pin messages.
- `shared`:
  - `embedSDK.js` for partner iframe embedding.

---

## 8. Cloud / Alibaba Impact

- **Alibaba Cloud DCDN**: Dynamic Route Acceleration for WebSocket chat and SSAI manifest resolution.
- **Alibaba ApsaraVideo SSAI**: VAST/VMAP ad tag integration.
- **Redis Enterprise**: Redis Pub/Sub for cross-pod WebSocket message broadcasting.

---

## 9. Security Implications

- **Chat Abuse Prevention**: Rate limiting (max 5 messages/sec per user) and automatic profanity regex filtering.
- **Ad Impression Fraud Prevention**: HMAC signature verification on ad tracking beacons to prevent falsified completion events.
- **Syndication Partner Isolation**: Signed JWT embed tokens tied strictly to HTTP `Referer` domain matching `allowed_domains`.

---

## 10. Testing Strategy

- **Unit Tests**: Pytest coverage $\ge 90\%$ across all new services (`chat`, `monetization`, `analytics`, `syndication`).
- **WebSocket Load Tests**: Simulated load test with 10,000 concurrent client connections broadcasting 500 msg/sec.
- **SSAI Manifest Parsing**: Verification of HLS manifest structure with `#EXT-X-DISCONTINUITY` and `#EXT-X-DATERANGE` SCTE-35 tags.

---

## 11. Migration Strategy

- **Zero Downtime**: Alembic migration `202608121200` adds new tables without altering existing Module 1–6 schemas.
- **Backward Compatibility**: Existing HLS streams (`index.m3u8`) remain untouched; SSAI manifests are served on explicit `ssai.m3u8` request paths.

---

## 12. Risks & Mitigations

| Risk | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **WebSocket Memory Exhaustion** | High | Connections managed with Redis Pub/Sub fanout; stale socket connections dropped after 60s ping timeout. |
| **Ad Blocker Interference** | Medium | Server-Side Ad Insertion (SSAI) stitches ad segments directly into video HLS manifest, preventing domain-based ad blocking. |
| **Partner Domain Forgery** | Medium | Embed tokens signed with RSA-256 containing caller domain claims validated against HTTP headers. |

---

## 13. Acceptance Criteria

- Full backend pytest execution passes with **Coverage $\ge 90.0\%$**.
- WebSocket chat latency $<100\text{ms}$ under 5,000 active chatters.
- SSAI manifest engine seamlessly stitches ad breaks into live HLS feeds.
- Broadcaster executive dashboard updates real-time concurrency metrics within 5 seconds.
- Multi-tenant partner embeds render cleanly on approved third-party domains.

---

## 14. Release Plan

- **Target Release Branch**: `feature/module7-platform-expansion`
- **Milestone Version**: `v0.8.0`
- **Release Candidate**: `v0.8.0-rc1` following Sprint 7.7 code freeze and audit.
