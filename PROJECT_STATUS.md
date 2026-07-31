# Project Status — GNTV DIGITAL v0.6.0-rc1

Overall status: **RELEASE CANDIDATE**
Date: 2026-07-30

## Completed release scope

- [x] Module 5 domain, contract, persistence, and permission foundation
- [x] RTMP/RTMPS and SRT ingest admission, stream-key security, leases, heartbeats, and health telemetry
- [x] Media probing, processing job orchestration, HLS/DASH packaging, manifest validation, publication, thumbnails, retries, and worker telemetry
- [x] Distribution targets, playback authorization, geo-fencing policy enforcement, recordings, and playback session controls
- [x] Editorial ElevenLabs text-to-speech integration with safe provider error handling
- [x] Sheeko Xariiro multilingual voice workflow for Afar, Amharic, Oromo, Somali, and Swahili
- [x] Processing Operations Center and Sheeko Xariiro Voice Studio frontend surfaces
- [x] Alembic migrations through `202607291700`
- [x] OpenAPI, typing, lint, test, coverage, build, and TypeScript gates

## Release evidence

| Gate | Result |
|---|---|
| PyTest | 149 passed |
| Coverage | 90.70% |
| MyPy | Zero issues across 132 source files |
| Ruff | Passed |
| Frontend production build | Passed with Vite 8.2.0 |
| TypeScript | `npx tsc --noEmit` passed |
| npm audit | Zero vulnerabilities |
| Release exclusions | Local environments, logs, IDE files, dependencies, build outputs, and caches excluded |

## Current constraints

- Media binaries and GPU execution remain isolated to approved worker environments; API processes dispatch work and do not perform heavy media processing.
- Sprint 5.3 defaults to CPU workers. GPU workers require an approved image and explicit `MEDIA_GPU_WORKERS_ENABLED=true`.
- Production ingest tokens, ElevenLabs credentials, databases, Redis, object storage, CDN signing secrets, and KMS configuration must be supplied through deployment environments.
- The test suite reports dependency deprecation warnings which do not block this release candidate.

## Release boundary

Module 5 is packaged as `v0.6.0-rc1` for release-candidate evaluation. Sprint 5.4 has not been started and is outside this release.
