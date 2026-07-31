# Changelog

All notable changes to GNTV DIGITAL are documented here.

## [0.6.0-rc1] — 2026-07-30

### Added

- Module 5 streaming and distribution domain foundation with live channels, events, stream keys, streams, recordings, playback sessions, transcoding jobs, manifests, thumbnails, distribution targets, and geo-fencing policies.
- RTMP/RTMPS and SRT ingest admission with gateway authentication, HMAC stream-key verification, CIDR checks, Redis leases, single-publisher coordination, lifecycle state enforcement, heartbeats, and health telemetry.
- Media processing orchestration with FFprobe inspection, safe FFmpeg command construction and execution boundaries, CPU rendition profiles, HLS and MPEG-DASH packaging, manifest validation, publication, thumbnail generation, retries, cancellation, telemetry, and processing APIs.
- Distribution target management, fail-closed playback authorization, geo-fencing enforcement, recording workflows, and signed playback controls.
- Editorial ElevenLabs text-to-speech voice discovery and MP3 generation with sanitized provider failures.
- Sheeko Xariiro multilingual production workflows for Afar, Amharic, Oromo, Somali, and Swahili, including scripts, review gates, voice presets, generated or uploaded audio, subtitle export, and generation audits.
- Frontend Processing Operations Center and Sheeko Xariiro Voice Studio surfaces.
- Alembic revisions `202607211200`, `202607241900`, and `202607291700`.
- Frontend TypeScript no-emit validation tooling.

### Security

- Production and staging reject the default ingest gateway token.
- Stream-key checks use one-way HMAC hashing and constant-time comparison.
- Provider credentials stay in environment-backed secret settings and are never returned to clients.
- Media paths, manifests, uploads, and command arguments are validated before worker execution.

### Verification

- 149 backend tests passed with 90.70% configured coverage.
- MyPy reported zero issues across 132 source files.
- Ruff passed for `app` and `tests`.
- The frontend production build and `npx tsc --noEmit` passed; npm reported zero vulnerabilities.
- Sprint 5.4 was not started and is outside this release candidate.

## [0.5.0] — 2026-07-20

### Added

- CMS Module 4 Editorial Workflow & Publishing with ten workflow states, role-aware transitions, assignments, collaboration notes, revision history, planning, scheduling, publication lifecycle processing, notifications, dashboards, audit events, and optimistic locking.
- Explicit `POST /api/v1/editorial/workflows/{workflow_id}/restore` recovery for archived workflows, restricted to administrators and chief editors.
- Editorial OpenAPI contract checks covering all 25 Editorial paths and their success responses.

### Fixed

- Editorial activity and audit payloads now JSON-encode datetime values before PostgreSQL persistence, preventing due-date planning updates from failing with HTTP 500.
- Archived workflows can be restored to `approved` for a new scheduling or publishing decision while obsolete publication fields are cleared.
- Notification dismissal is included in the generated OpenAPI document.

### Verification

- 79 tests passed with 98.58% configured coverage.
- MyPy reported zero errors across 87 source files.
- Ruff, OpenAPI 3.1 validation, Alembic single head `202607131200`, and PostgreSQL Editorial lifecycle validation passed.
- Production-shaped configuration loaded successfully with external PostgreSQL, Redis, OSS, JWT, and media-signing values; real deployment secrets remain environment-managed.
- CMS Module 5 was not started and is outside this release.

## [0.4.0] — 2026-07-12

### Added

- Unified FastAPI application foundation with PostgreSQL, Redis lifecycle, configuration, health checks, OpenAPI, SQLAlchemy 2.x, and Alembic.
- JWT authentication with registration, verification, login, refresh rotation, logout, password reset, device/session management, RBAC, and audit logging.
- CMS Module 1 Content Core with canonical content, languages, regions, categories, tags, genres, editorial workflow, permissions, events, and workers.
- CMS Module 2 Media Library with local and Alibaba OSS storage abstractions, signed upload/download flows, MIME/extension/size/checksum validation, metadata, content attachments, soft deletion, restore, and bulk operations.
- CMS Module 3 Premium Streaming Catalog Engine for movies, series, seasons, episodes, live TV, radio, podcasts, shorts, kids, and news.
- Catalog collections, featured rows, Continue Watching, ratings, recommendations, people credits, studios, SEO metadata, and AI enrichment hooks.
- Versioned APIs under `/api/v1`, PostgreSQL migrations through revision `202607121200`, API documentation, acceptance reports, and repeatable local E2E suites.

### Fixed

- Local signed media downloads now validate expiry and HMAC signatures and enforce storage-root confinement.
- Viewer catalog access is restricted to published titles; draft detail requests return 404.
- Soft-deleted catalog items remain unavailable until restored.
- Collection management now includes list, detail, update, and delete contracts.

### Security

- Role- and scope-based access controls protect CMS, media, and catalog operations.
- Upload validation includes MIME, extension, file size, safe filename, path traversal, and SHA-256 verification.
- Authentication includes revocable sessions, refresh-token rotation, account verification, and audit trails.

### Verification

- 73 tests passed.
- Coverage: 98.58%.
- MyPy: zero errors across 65 backend source files.
- Ruff and OpenAPI validation passed.
- PostgreSQL migration and ORM round-trip validation passed at Alembic head `202607121200`.

[0.4.0]: https://github.com/gntv-digital/platform/releases/tag/v0.4.0
[0.5.0]: https://github.com/gntv-digital/platform/releases/tag/v0.5.0
[0.6.0-rc1]: https://github.com/gntv-digital/platform/releases/tag/v0.6.0-rc1
