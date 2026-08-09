# GNTV DIGITAL — Playback Platform Readiness Assessment (Module 6)

**Role**: Architecture and Release Director  
**Date**: July 31, 2026  
**Verdict**: **READY WITH CONDITIONS**

---

## 1. Repository Structure Inspection & Findings

A comprehensive review of the active workspace branch `feature/module6-playback-platform` and current dependencies has been completed.

### 1.1 Reusable Components
Several foundational entities developed in prior modules (up to Module 5 `v0.6.0-rc1`) are highly reusable for the playback platform:
- **`PlaybackSession` Model**: The SQLAlchemy model is already defined in [streaming/models/domain.py](file:///Users/ayrotv/digital%20broadcasting%20platform%20for%20Global%20Network%20TV%20%28GNTV%29/backend-api/app/modules/streaming/models/domain.py#L356-L403), containing fields for `device_id`, `token_jti_hash`, `country_code`, and media target associations.
- **Pydantic Playback Contracts**: Contract models like `PlaybackResolveQuery`, `PlaybackTokenRequest`, `PlaybackAuthorizationResponse`, `PlaybackTokenResponse`, and `PlaybackSessionResponse` are already present in [streaming/schemas/contracts.py](file:///Users/ayrotv/digital%20broadcasting%20platform%20for%20Global%20Network%20TV%20%28GNTV%29/backend-api/app/modules/streaming/schemas/contracts.py).
- **`ContinueWatching` Progress**: The database schema and services for tracking VOD progress are fully defined in the `catalog` module ([catalog/models.py](file:///Users/ayrotv/digital%20broadcasting%20platform%20for%20Global%20Network%20TV%20%28GNTV%29/backend-api/app/modules/catalog/models.py#L284-L301) and [catalog/service.py](file:///Users/ayrotv/digital%20broadcasting%20platform%20for%20Global%20Network%20TV%20%28GNTV%29/backend-api/app/modules/catalog/service.py#L197-L220)).
- **`GeoFencingPolicy`**: The geo-fencing checks and database tables are ready in the `distribution` module ([distribution/models.py](file:///Users/ayrotv/digital%20broadcasting%20platform%20for%20Global%20Network%20TV%20%28GNTV%29/backend-api/app/modules/distribution/models.py#L93-L140)).
- **Auth Dependency**: Token checks and authentication helpers in [app/dependencies/auth.py](file:///Users/ayrotv/digital%20broadcasting%20platform%20for%20Global%20Network%20TV%20%28GNTV%29/backend-api/app/dependencies/auth.py) are stable.

### 1.2 Architectural Conflicts
- **Cross-Module Dependency**: `PlaybackSession` (streaming domain) directly references `catalog_items` (catalog domain) and `cms_content` (CMS core domain). While relational constraints are correct, this creates a bidirectional dependency between streaming and catalog namespaces.
- **Authentication Duplication**: The project still contains historical files like `backend-api/app/utils/auth_dependencies.py` which conflict with `app/dependencies/auth.py`. 

### 1.3 Duplicate Modules & Legacy Code Risks
- **Mock Data Air-gap**: The React consumer app [frontend-consumer/src/main.js](file:///Users/ayrotv/digital%20broadcasting%20platform%20for%20Global%20Network%20TV%20%28GNTV%29/frontend-consumer/src/main.js) uses local storage sandboxes and mock JSON sets ([shared/src/utils/supabase.js](file:///Users/ayrotv/digital%20broadcasting%20platform%20for%20Global%20Network%20TV%20%28GNTV%29/shared/src/utils/supabase.js)) instead of executing backend API requests.
- **Mock Video Feed**: The consumer player [frontend-consumer/src/components/LivePlayer.js](file:///Users/ayrotv/digital%20broadcasting%20platform%20for%20Global%20Network%20TV%20%28GNTV%29/frontend-consumer/src/components/LivePlayer.js) draws on a `<canvas>` element to simulate video. This must be replaced with a real HTML5 media engine integration.

### 1.4 Missing Dependencies
- **Frontend Player Library**: There are no streaming player client libraries (e.g., `hls.js`, `dashjs`, or `shaka-player`) declared in [frontend-consumer/package.json](file:///Users/ayrotv/digital%20broadcasting%20platform%20for%20Global%20Network%20TV%20%28GNTV%29/frontend-consumer/package.json) or [frontend-studio/package.json](file:///Users/ayrotv/digital%20broadcasting%20platform%20for%20Global%20Network%20TV%20%28GNTV%29/frontend-studio/package.json).

### 1.5 Migration Requirements
- **PostgreSQL Tables**: Database schemas must be updated to support the registration of user devices (`user_devices`) and historical watch metrics (`user_watch_history`).
- **Alembic Single-Head**: All DDL changes must be generated as a new single-head migration script (e.g., `202608011200_module6_playback.py`).

### 1.6 Integration Risks with Module 5
- **Stubbed Service**: The streaming endpoints inside [streaming/api/router.py](file:///Users/ayrotv/digital%20broadcasting%20platform%20for%20Global%20Network%20TV%20%28GNTV%29/backend-api/app/modules/streaming/api/router.py) depend on `StreamingService`, which currently raises `503 Service Unavailable` on request. Handshake implementations must be fully bound in Sprint 6.1.
- **ApsaraVideo Ingest Handshake**: Recording finalization depends on the webhook callbacks. If signature calculations drift from Alibaba console values, recordings will fail to update.

---

## 2. Architecture Readiness Conditions

To proceed with implementation, the following conditions must be met:

1. **VOD/Live Player Package Integration**: The frontend development must install and integrate an approved player library (recommend `shaka-player` or `hls.js`) in `package.json` to handle real adaptive-bitrate streams instead of canvas simulation.
2. **Consolidate Auth Utilities**: Legacy `backend-api/app/utils/auth_dependencies.py` must be deleted. All routes must reference standard `app/dependencies/auth.py` for token verification.
3. **Database Migration Script**: An Alembic migration script must be executed to provision the `user_devices` and `user_watch_history` tables before Sprint 6.2 begins.
4. **Redis Concurrency Configuration**: Deployment environments must provide a dedicated Redis database configuration (e.g., Redis DB index `1` for telemetry and limits, DB index `0` for Celery queue management) to avoid cache pollution.

---

## 3. Verdict

```text
READY WITH CONDITIONS
```
