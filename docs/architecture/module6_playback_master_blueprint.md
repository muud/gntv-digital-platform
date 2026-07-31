# GNTV DIGITAL — Playback Platform Master Blueprint (Module 6)

**Role**: Architecture and Release Director  
**Status**: APPROVED — FOR DESIGN SIGN-OFF  
**Release Target**: `v0.7.0` (following `v0.6.0-rc1`)  
**Active Branch**: `feature/module6-playback-platform`

---

## 1. Executive Summary & System Context

This document defines the architecture of the **GNTV Playback Platform (Module 6)**. It establishes the technical designs, workflows, data models, and player behaviors required to deliver secure, resilient, high-quality, localized video playback for Video-On-Demand (VOD) and Live TV services.

The Playback Platform operates at the boundary between the GNTV Core CMS (Module 5), the Premium Catalog, and public-facing consumer applications (React web, mobile, Smart TV, IPTV, OTT).

```mermaid
flowchart TD
    subgraph Client Layer
        Web[Web Client]
        Mobile[Mobile iOS/Android]
        SmartTV[Smart TV / OTT]
    end

    subgraph Alibaba CDN & Origin
        CDN[Alibaba Cloud CDN]
        OSS[Alibaba Cloud OSS Origin]
        KMS[Alibaba Cloud Key Management Service]
    end

    subgraph FastAPI Control Plane
        API[FastAPI Gateway]
        AuthSvc[Entitlement & Session Service]
        QoeSvc[QoE Analytics Engine]
    end

    subgraph Cache & Persistence
        Redis[(Redis Cluster)]
        PG[(ApsaraDB PostgreSQL)]
    end

    %% Workflows
    Web -->|1. Request Token| API
    API -->|2. Entitlement / Geo Check| AuthSvc
    AuthSvc -->|3. Query Limits| Redis
    AuthSvc -->|4. Persist Session| PG
    API -->|5. Issue Signed Token / URL| Web
    Web -->|6. Fetch Stream (.m3u8)| CDN
    CDN -->|7. Verify Edge Signature| CDN
    CDN -->|8. Fetch Segments| OSS
    CDN -->|9. Fetch Keys / Licenses| KMS
    Web -->|10. Telemetry Beacons| QoeSvc
    QoeSvc -->|11. Cache Metrics| Redis
```

---

## 2. Streaming Fundamentals & Delivery Architecture

### 2.1 VOD Playback
- **Source Assets**: Transcoded multi-bitrate HLS and MPEG-DASH files stored on Alibaba Cloud OSS (`gntv-streaming-media`).
- **ABR Configuration**: Video encoding utilizes H.264 (AVC) and H.265 (HEVC) in fragmented MP4 (fMP4) wrappers.
- **Rendition Ladder**:
  - 1080p: 6.0 Mbps (HEVC) / 8.0 Mbps (AVC), 60 FPS
  - 720p: 3.5 Mbps (HEVC) / 4.5 Mbps (AVC), 60 FPS
  - 480p: 1.8 Mbps (HEVC) / 2.2 Mbps (AVC), 30 FPS
  - 360p: 800 Kbps (AVC), 30 FPS

### 2.2 Live TV Playback
- **Ingest Origin**: Ingested via SRT/RTMP (Module 5), transcoded live by GPU/CPU worker pools.
- **Packaging**: Packaged concurrently into HLS and MPEG-DASH manifests.
- **Audio & Subtitle Packaging**: Multi-language audio tracks multiplexed using ISO 639-2 codes (`amh`, `som`, `swa`, `orm`, `aff`, `eng`). Subtitles distributed in WebVTT format referenced via `#EXT-X-MEDIA` HLS attributes.

### 2.3 Live DVR, Catch-up TV, and Time-Shift
- **Live DVR**: Standard HLS live manifests use `#EXT-X-PLAYLIST-TYPE:EVENT` with a sliding time window (configurable, default: 2 hours, `sliding_window_segments=1200` for 6-second segments) allowing D-pad rewinding.
- **Time-Shift Playback**: Enables viewing live broadcasts starting from any historical timestamp using request parameters:
  - HLS: `https://stream.gntv.com/live/{channel_id}/index.m3u8?time-shift=1719878400`
  - Backend dynamically retrieves segment offsets from database recording indexes.
- **Catch-up TV**: Once a scheduled live event completes, the segment files recorded in OSS under the configured prefix (`recordings.oss_prefix`) are indexed and republished as a static VOD HLS/DASH asset, immediately visible in the Continue Watching shelf.

---

## 3. Playback Session Lifecycle & Security

### 3.1 Playback Session Lifecycle
A playback session transitions through the following states, mapped directly to `PlaybackSessionStatus`:
1. **Authorized**: Signed token issued; no playback traffic received.
2. **Playing**: Active playback detected via client heartbeat.
3. **Paused**: Client reports paused state; heartbeats continue at a lower frequency (e.g., every 120s instead of 30s).
4. **Ended**: Client explicitly sends stop signal, or lease expires.
5. **Revoked**: Explicit administrative termination (e.g., concurrency limit exceeded, user logged out).
6. **Expired**: No heartbeat received within the grace period (heartbeat interval * 2.5).

### 3.2 Signed Playback Tokens & URL Signing
To prevent hotlinking and credential sharing, CDN URLs require dynamic signatures.
- **HMAC Construction**:
  `Signature = Hex(HMAC-SHA256(CDN_Signing_Key, Normalised_Path + "?" + Query_Params))`
- **Normalised Path Format**: `/live/{channel_id}/index.m3u8` or `/vod/{item_id}/playlist.mpd`.
- **Query Parameters**:
  - `exp`: Epoch expiration timestamp (10-digit integer).
  - `session_id`: Unique `playback_sessions.id`.
  - `pv`: Geo-fencing policy version.
  - `kid`: KMS Content Key Identifier.
- **CDN Edge Validation**: Alibaba CDN executes an EdgeScript routine to validate the HMAC and reject expired or altered tokens at the nearest Point of Presence (PoP).

### 3.3 Playback Authorization & Entitlement
- **Authorization Flow**:
  1. Consumer requests playback of `target_id` (catalog_item_id or live_channel_id).
  2. Route `/api/v1/streaming/playback-token` checks if user is authenticated and holds active subscription scopes (RBAC role verification).
  3. Geo-fencing check matches client IP against the target's effective `GeoFencingPolicy` (fail-closed if policy is in `PENDING` or country code is blocked).
  4. Redis checks concurrent stream count for `user_id`.
  5. Upon success, generates a `PlaybackSession` record in PostgreSQL, initializes a concurrency key in Redis, and signs the HLS/DASH URL.

---

## 4. Concurrent Stream & Device Limits

### 4.1 Device Limits
- **Policy**: Maximum of 5 registered devices per subscriber account.
- **Registration**: Device registration occurs automatically on first login via unique hardware fingerprint (`device_id`).
- **Cooldown**: De-registration of a device is limited to once every 30 days to prevent account cycling.

### 4.2 Concurrent Stream Limits
- **Limit**: Standard limit of 3 concurrent streams per account (can vary by subscription tier: Free = 1, Premium = 3, Family = 5).
- **Enforcement Mechanism**:
  - Redis tracks active sessions using a Sorted Set (ZSET) per user: `user:sessions:{user_id}` where the member is `session_id` and the score is the epoch timestamp of the last active heartbeat.
  - On authorization request, API queries `ZCARD user:sessions:{user_id}`.
  - If current active count matches or exceeds the tier limit:
    - **Lease Eviction**: The oldest session (highest idle time) is evicted by publishing an eviction event via Redis Pub/Sub to client sockets, and its database status is updated to `REVOKED`.
    - Alternatively, request is blocked with `HTTP 409 Conflict` (policy is customizable).
  - Heartbeats from clients refresh the member score: `ZADD user:sessions:{user_id} NX {current_time} {session_id}`.
  - A periodic Celery cleanup job sweeps expired ZSET keys where score is older than `current_time - (heartbeat_interval * 2.5)`.

---

## 5. Playback Localization & Personalization

### 5.1 Resume Playback & Continue Watching
- **State Capture**: The video player sends playback progress update requests to `/api/v1/catalog/items/{id}/progress` every 10 seconds.
- **Rules**:
  - If progress is < 5% of total duration: Ignore (prevent cluttering the Continue Watching list).
  - If progress is > 95% of total duration: Set `completed = True` and remove from active Continue Watching shelf.
  - Otherwise, store progress position (`position_seconds`) in `catalog_continue_watching`.

### 5.2 Watch History
- Detailed tracking of playback events is recorded in a new historical ledger database table `user_watch_history`.
- Unlike `ContinueWatching`, which is upserted, `watch_history` appends records for audit, recommendations, and analytics.

---

## 6. DRM & Watermarking Architecture

### 6.1 Multi-DRM Architecture
We integrate with **Alibaba Cloud KMS** and ApsaraVideo DRM to deliver encrypted streams.
- **Widevine**: Used for Chrome, Firefox, Android, and Android TV (Smart TV). Packaged as MPEG-DASH.
- **PlayReady**: Used for Edge browser, Xbox, and legacy IPTV/OTT set-top boxes. Packaged as MPEG-DASH.
- **FairPlay**: Used for Safari, macOS, iOS, and Apple TV. Packaged as HLS with sample-level AES-128 encryption.
- **Key Rotation**: CEKs (Content Encryption Keys) are rotated every 24 hours for live streams. For VOD, keys are generated once per asset ingestion.

### 6.2 Visible and Forensic Watermarking
- **Visible Watermarking**: Video player renders a floating CSS overlay containing user metadata:
  - Format: `GNTV | {username} | {ip_address} | {timestamp}`
  - Implementation: SVG layer with dynamic opacity (15%), random coordinates changing every 60 seconds. Can be combined with canvas manipulation on Smart TVs.
- **Forensic Watermarking**:
  - **A/B Segment Switching**: The encoder packages two distinct variants of every video segment (Variant A and Variant B) with imperceptible, unique pixel adjustments.
  - The CDN edge server dynamically routes segment requests based on user token bits (e.g., session hash bits determine whether segment 10 is served from path `/A/` or `/B/`).
  - This embeds an indelible, tracking sequence into the downloaded file, tracing leaked streams back to the precise subscriber session.

---

## 7. Client Playback & Resilience Strategy

### 7.1 Player Error Handling & Code Maps
The consumer application wraps the underlying player library (e.g., `hls.js` or `shaka-player`) with a mapping layer:
- **Error Code Maps**:
  - `ERR_NET_TIMEOUT`: Network timeout fetching manifest/segment.
  - `ERR_DECRYPT_FAILED`: DRM license or key acquisition failure.
  - `ERR_GEO_BLOCKED`: Egress blocked by geo-fencing policies.
  - `ERR_CONCURRENCY_EXCEEDED`: Active session evicted due to stream limit.

### 7.2 Retry and Reconnection Strategy
Clients must implement exponential backoff reconnection logic:
- Max retries: 5.
- Base delay: 1000ms.
- Multiplier: 2x + random jitter (0-500ms).
- **CDN Failover**: If segment download fails continuously (e.g., HTTP 5xx or 404), the player switches seamlessly to a secondary CDN domain (e.g., from `stream.gntv.com` to `backup-stream.gntv.com`).

### 7.3 Smart TV Remote Navigation
- **Focus Engine**: HTML/CSS elements use CSS `:focus` states. Remote navigation catches key codes for D-pad navigation:
  - Up: 38, Down: 40, Left: 37, Right: 39, Select/Enter: 13, Back/Return: 8 (or 10009 on Tizen, 461 on webOS).
- **Overlay HUD**: Smart TV overlays are optimized for remote clicks, featuring large hit targets (minimum 48x48 pixels, 80px preferred for TV).

### 7.4 Mobile Playback Behaviour
- **Picture-in-Picture (PiP)**: React wrappers listen to document visibility changes and invoke `video.requestPictureInPicture()`.
- **Background Playback**: In mobile applications, playback falls back to an audio-only stream when the app is minimized, minimizing cellular data consumption.

### 7.5 Accessibility
- Enforce Web Content Accessibility Guidelines (WCAG 2.1 AA) compliance.
- High-contrast visual focus indicators (3px dashed outline).
- Full keyboard and screen-reader accessibility for controls (using standard ARIA labels like `aria-label="Play"`, `aria-pressed="false"`).

---

## 8. QoE Analytics & Metrics

Client telemetry is dispatched using the Beacon API (`navigator.sendBeacon`) or fallback WebSocket channels to `/api/v1/qoe/beacon`.

| QoE Metric | Definition | SLA Target |
|---|---|---|
| **Startup Time (VST)** | Time (ms) from play click to first video frame rendered. | < 1500ms |
| **Rebuffer Rate (RBR)** | Ratio of buffering duration to total session duration. | < 0.5% |
| **Bitrate Switch Count** | Frequency of adaptive switching events. | Normal. High count triggers alert. |
| **Failure Rate (VSF)** | Percentage of sessions terminating in playback failure. | < 0.1% |
| **Watch Duration** | Total seconds played per session. | N/A (Analytical use) |

---

## 9. Database & Cache Schema Changes

### 9.1 Database Schema Changes (PostgreSQL)

To support watch history and device registrations, we will introduce two new models:

#### `UserDevice` Model
Tracks registered subscriber devices to enforce the 5-device limit.
```sql
CREATE TABLE user_devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id VARCHAR(160) NOT NULL,
    device_name VARCHAR(120) NOT NULL,
    device_type VARCHAR(40) NOT NULL, -- 'web', 'mobile', 'smart_tv', 'iptv', 'ott'
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_device UNIQUE (user_id, device_id)
);
CREATE INDEX idx_user_devices_user ON user_devices(user_id);
```

#### `UserWatchHistory` Model
Maintains a historical record of all playback sessions.
```sql
CREATE TABLE user_watch_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    catalog_item_id UUID REFERENCES catalog_items(id) ON DELETE SET NULL,
    live_channel_id UUID REFERENCES live_channels(id) ON DELETE SET NULL,
    playback_session_id UUID REFERENCES playback_sessions(id) ON DELETE SET NULL,
    device_id VARCHAR(160) NOT NULL,
    watch_duration_seconds INTEGER NOT NULL DEFAULT 0,
    max_position_seconds INTEGER NOT NULL DEFAULT 0,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    watched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_watch_history_target CHECK (
        (catalog_item_id IS NOT NULL AND live_channel_id IS NULL) OR
        (catalog_item_id IS NULL AND live_channel_id IS NOT NULL)
    )
);
CREATE INDEX idx_watch_history_user_time ON user_watch_history(user_id, watched_at DESC);
```

### 9.2 Redis Data Structures
- **Active User Sessions ZSET**:
  - Key: `user:sessions:{user_id}`
  - Type: Sorted Set (ZSET)
  - Member: `{session_id}`
  - Score: Epoch timestamp (e.g., `1719878400`)
  - TTL: None (managed by eviction/cleanup logic)
- **Session IP/Country Code cache**:
  - Key: `session:meta:{session_id}`
  - Type: Hash (HMAC/Token cache, IP, Country)
  - TTL: 3600 seconds (matches token expiration window)

---

## 10. Backend API Contracts & Events

All API endpoints enforce JSON request/response structures.

### 10.1 Playback Heartbeat
- **Endpoint**: `/api/v1/streaming/playback/{session_id}/heartbeat` (POST)
- **Request Payload**:
  ```json
  {
    "position_ms": 125000,
    "state": "playing",
    "qoe": {
      "buffer_events": 0,
      "bitrate_bps": 4500000,
      "fps": 60
    }
  }
  ```
- **Response**:
  ```json
  {
    "status": "active",
    "next_heartbeat_interval_seconds": 30
  }
  ```

### 10.2 Session Eviction Event (Redis Pub/Sub)
- **Channel**: `user_notifications:{user_id}`
- **Payload**:
  ```json
  {
    "event": "session_evicted",
    "session_id": "c3b0ac48-dd02-4b2a-8ea6-9509bfef42c7",
    "reason": "concurrency_limit_exceeded"
  }
  ```

---

## 11. Security Threat Model

| Threat | Attack Vector | Architectural Mitigation |
|---|---|---|
| **Token Sharing** | User shares HLS playlist URL with unauthorized viewers. | URL contains short-lived signed tokens (`exp` parameter 5-15 mins). Edge validates token expiration. |
| **Geo-Bypass** | Client uses proxy/VPN to access restricted streams. | Cloud CDN geofencing matches IP against GeoIP databases. Playback Authorization route blocks VPN IPs during token issuance. |
| **Stream Ripping** | User records stream using browser extensions or tools. | Stream is encrypted with Multi-DRM (Widevine/FairPlay/PlayReady). Dynamic forensic watermarking identifies the source account. |
| **Concurrency Abuse** | User shares credentials to allow infinite simultaneous streams. | Redis ZSET limits stream count to 3, evicting oldest sessions dynamically. |

---

## 12. Quality Gates & Release Architecture

### 12.1 Release Gates
To promote Module 6 to production, the codebase must clear the following gates:
- **PyTest Coverage**: Master suite must pass with $\ge 90\%$ code coverage on all new playback routes and services.
- **MyPy & Ruff**: Zero issues reported in strict check modes.
- **Load Testing**: Redis concurrency enforcement must handle $\ge 5000$ heartbeat requests per second with $< 50\text{ms}$ p99 response times.
- **Frontend Bundle**: Vite production build compilation must pass without warning gates.

### 12.2 Rollback Strategy
If a post-release failure occurs (e.g., CDN signature validation failure):
- **FastAPI Rollback**: Revert PostgreSQL schemas/code via Alembic down migration commands (`alembic downgrade -1`).
- **CDN EdgeScript Disable**: Toggle the Alibaba CDN EdgeScript configuration flag back to bypass URL signature validation.
- **Cache Clear**: Flush Redis active session ZSETs if concurrency limit checks become corrupted.
