# GNTV DIGITAL — Playback Platform Execution Plan (Module 6)

**Role**: Architecture and Release Director  
**Document Status**: APPROVED — READY FOR KICKOFF  
**Release Plan**: Sprints 6.1 to 6.7

---

## Sprint 6.1 — Playback Core

### Objectives
Establish the base media playback service binding inside the FastAPI control plane and mount the physical media player component in the React consumer application, replacing the canvas simulation.

### Deliverables
- **Backend**:
  - Implement service class implementing `StreamingServiceInterface` playback methods (`resolve_playback` and `issue_playback_token`).
  - Implement token-signing functions using HMAC-SHA256 path signature logic.
  - Register `/api/v1/streaming/playback/{target_id}` and `/api/v1/streaming/playback-token` routes.
- **Frontend**:
  - Add `hls.js` or `shaka-player` to `frontend-consumer/package.json`.
  - Refactor `LivePlayer.js` to mount a native HTML5 `<video>` player linked to the signed streaming URL.

### Technical Spec
- **API Contracts**:
  - GET `/api/v1/streaming/playback/{target_id}?device_id={device_id}&protocol={protocol}`
  - Response: `PlaybackAuthorizationResponse` (signed url, expires_at, heartbeat interval).
- **Database changes**: None.
- **Redis usage**: Transient cache mapping of manifest endpoints (`manifest:endpoint:{target_id}`).
- **Test requirements**: Unit tests mock-verifying signature outputs against expected keys.
- **Security checks**: Signature tamper validation checks.

### Acceptance Criteria
- Client player initiates streaming of an unencrypted HLS manifest.
- Playback requests fail with `HTTP 403` if signed token is expired or signed with incorrect key.

### S6.1 Gates & RACI
- **Architecture Review Gate**: All route schemas conform to standard Pydantic models in `streaming/schemas/contracts.py`.
- **Release Blocker Conditions**: Playback requests trigger `HTTP 500` or loop indefinitely.
- **Codex (Backend)**: Build FastAPI service bindings and path signing.
- **Lovable (Frontend)**: Integrates player SDK and binds player controller.
- **Antigravity (Verification)**: Asserts coverage for signed path generator $\ge 90\%$.

---

## Sprint 6.2 — Playback Sessions and Authorization

### Objectives
Provision database tables for user devices and watch history, and enforce concurrent stream limits in Redis.

### Deliverables
- **Backend**:
  - Write and run Alembic migrations for `user_devices` and `user_watch_history` tables.
  - Write Redis ZSET concurrency check logic in the Playback Authorization flow.
  - Implement heartbeat endpoint `/api/v1/streaming/playback/{session_id}/heartbeat`.
- **Frontend**:
  - Integrate a background timer sending play-position heartbeats to the API.
  - Implement eviction alerts for concurrency blocks.

### Technical Spec
- **API Contracts**:
  - POST `/api/v1/streaming/playback/{session_id}/heartbeat`
  - Payload: `{ "position_ms": int, "state": str }`
- **Database changes**: Add `user_devices` and `user_watch_history` tables.
- **Redis usage**: 
  - Concurrency ZSET: `user:sessions:{user_id}` (scores = heartbeat timestamp).
  - Session metadata cache: `session:meta:{session_id}` (TTL = 1 hour).
- **Test requirements**: Run automated concurrent scripts requesting tokens for a single user to verify lease eviction.
- **Security checks**: Validate device fingerprint forgery vectors.

### Acceptance Criteria
- Launching a fourth stream for a user account evicts the first stream session within 15 seconds.
- Inactive streams are evicted automatically after 90 seconds.

### S6.2 Gates & RACI
- **Architecture Review Gate**: Alembic migration head matches single-head requirement.
- **Release Blocker Conditions**: Concurrency check exhibits race conditions allowing double the permitted streams.
- **Codex**: Implement PostgreSQL models, migrations, and Redis concurrency logic.
- **Lovable**: Implement client heartbeat loops and eviction overlays.
- **Antigravity**: Verify Redis ZSET limits under mock concurrent workloads.

---

## Sprint 6.3 — Live TV, DVR and Catch-up

### Objectives
Enable Live DVR sliding window rewinds, time-shift parameter handling, and automatic VOD catch-up publishing.

### Deliverables
- **Backend**:
  - Add dynamic time-shift URL generation to `resolve_playback`.
  - Process ApsaraVideo live recording webhook callbacks to index segment ranges.
- **Frontend**:
  - Implement visual timeline scrubbing for live streams supporting DVR windows.

### Technical Spec
- **API Contracts**:
  - Webhook POST `/api/v1/streaming/callbacks/apsara` (updated to support recording events).
- **Database changes**: Add indexes to `recordings` to optimize lookups by timestamp.
- **Redis usage**: Caching manifest segment timelines to optimize segment lookup times.
- **Test requirements**: Verify generated DVR manifest outputs align with segment sequences.
- **Security checks**: Webhook signature verification checks.

### Acceptance Criteria
- Player can seek backward up to 2 hours on a live broadcast.
- Disconnecting stream creates a VOD recording index available for playback.

### S6.3 Gates & RACI
- **Architecture Review Gate**: Webhook route signature validation must use SHA256 HMAC signature.
- **Release Blocker Conditions**: Webhook accepts unauthenticated callback requests.
- **Codex**: Webhook handlers and time-shifting algorithms.
- **Lovable**: UI timeline navigation and live-status labels.
- **Antigravity**: Verify signature validation on incoming mock webhook payloads.

---

## Sprint 6.4 — DRM, Geo-control and Watermarking

### Objectives
Protect streams against unauthorized copying using Alibaba KMS, geo-fencing policies, and visible/forensic watermarking.

### Deliverables
- **Backend**:
  - Integrate with Alibaba Cloud KMS to fetch Content Encryption Keys (CEK).
  - Enforce `GeoFencingPolicy` based on client location lookup.
  - Implement A/B segment allocation for forensic watermarking tracking.
- **Frontend**:
  - Add floating visible watermark overlay containing user details.

### Technical Spec
- **API Contracts**: None (uses signed URLs containing key indexes).
- **Database changes**: None.
- **Redis usage**: Cache country code lookups for client IP addresses.
- **Test requirements**: Simulated playback from blocked country code returns `403`.
- **Security checks**: Entitlement and geo verification checks.

### Acceptance Criteria
- Streams fail to decrypt without correct DRM license from KMS.
- Floating overlay renders username and IP at variable opacity and locations.

### S6.4 Gates & RACI
- **Architecture Review Gate**: Geo-fencing check fails closed in case of backend lookup failure.
- **Release Blocker Conditions**: Bypass of geo-fencing possible via header tampering.
- **Codex**: DRM packaging, geo policy checks, and watermarking segment mapping.
- **Lovable**: Visual SVG floating overlay integration.
- **Antigravity**: Verify geo-block enforcement on mock external IPs.

---

## Sprint 6.5 — QoE Analytics and Observability

### Objectives
Monitor playback quality (VST, rebuffer rate, switches) using telemetry ingestion.

### Deliverables
- **Backend**:
  - Implement `/api/v1/qoe/beacon` endpoint.
  - Write metrics processor parsing telemetry records.
- **Frontend**:
  - Integrate analytics beacons measuring VST, buffering times, and bitrate switches.

### Technical Spec
- **API Contracts**:
  - POST `/api/v1/qoe/beacon`
  - Payload: `{ "session_id": UUID, "vst_ms": int, "rebuffering_ms": int, "bitrate_bps": int, "failures": list }`
- **Database changes**: Provision tables for QoE session metrics.
- **Redis usage**: Store raw buffer and failure metrics before writing to DB.
- **Test requirements**: Perform volume tests verifying ingest rate handling.
- **Security checks**: Limit ingestion rate to block DoS.

### Acceptance Criteria
- Buffering events logged in client trigger a beacon dispatch to backend.
- Playback failures are updated in dashboards within 10 seconds.

### S6.5 Gates & RACI
- **Architecture Review Gate**: Telemetry beacons do not block browser page unload.
- **Release Blocker Conditions**: Telemetry ingestion causes memory leaks.
- **Codex**: Analytics API, database records, and logging alerts.
- **Lovable**: Telemetry listeners on client player.
- **Antigravity**: Load test QoE beacon endpoint.

---

## Sprint 6.6 — Smart TV, Mobile and Accessibility

### Objectives
Enable custom player behaviors for Smart TV remote control, mobile picture-in-picture, and screen readers.

### Deliverables
- **Frontend**:
  - Add remote key navigation listeners and visual focus indications.
  - Implement mobile background audio fallback and PiP mode.
  - Add ARIA attributes to player buttons.

### Technical Spec
- **API Contracts**: None.
- **Database changes**: None.
- **Redis usage**: None.
- **Test requirements**: Key code simulations, screen reader scan.

### Acceptance Criteria
- Consumer TV client is fully navigable using keyboard arrow keys.
- Minimized mobile client switches to audio-only stream.

### S6.6 Gates & RACI
- **Architecture Review Gate**: Ensure all buttons have explicit `aria-label` settings.
- **Release Blocker Conditions**: Navigation focus trapped in modal overlays.
- **Codex**: None.
- **Lovable**: Remote navigation, mobile features, accessibility markup.
- **Antigravity**: Run manual and accessibility automated audits.

---

## Sprint 6.7 — Integration, Hardening and Release Candidate

### Objectives
Remove all remaining mocks, run final migrations, perform E2E integration test runs, and package `v0.7.0-rc1`.

### Deliverables
- **Backend/Frontend**:
  - Remove all sandbox storage variables in `supabase.js` and point to production endpoints.
  - Complete configuration files for deployment to Alibaba Cloud.
  - Package code release candidate.

### Technical Spec
- **API Contracts**: Complete OpenAPI schema compile check.
- **Database changes**: Final Alembic head alignment.
- **Redis usage**: Cleanup and flush stale cache states.
- **Test requirements**: Full pytest suite execution (target 100% pass on 200+ tests).
- **Security checks**: Complete OWASP vulnerability check scan.

### Acceptance Criteria
- E2E play flows (request -> token -> CDN path -> playback -> heartbeat -> stop) execute successfully.
- Codebase passes all quality gates.

### S6.7 Gates & RACI
- **Architecture Review Gate**: Final release signed by Architecture Director.
- **Release Blocker Conditions**: Any failing tests or MyPy/Ruff errors.
- **Codex**: Configuration verification, Alembic head check.
- **Lovable**: Complete asset build verification.
- **Antigravity**: Execute final E2E test verification suite.
