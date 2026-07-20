# Project Status — GNTV DIGITAL v0.5.0

Overall status: **RELEASED**
Date: 2026-07-20

## Completed milestones

- [x] Platform foundation
- [x] Authentication and authorization
- [x] CMS Module 1 — Content Core
- [x] CMS Module 2 — Media Library
- [x] CMS Module 3 — Premium Streaming Catalog Engine
- [x] CMS Module 4 — Editorial Workflow & Publishing backend
- [x] Module 4 release-blocker hotfix verification
- [x] Modules 2, 3, and 4 local E2E validation
- [x] PostgreSQL migrations through `202607131200`
- [x] OpenAPI, typing, lint, test, and coverage gates

## Release evidence

| Gate | Result |
|---|---|
| PyTest | 79 passed |
| Coverage | 98.58% |
| MyPy | Zero errors, 87 files |
| Ruff | Passed |
| OpenAPI | Passed — 3.1.0, 69 paths, 25 Editorial paths / 28 operations |
| PostgreSQL | Migration and ORM round-trips passed |
| Production configuration | Production-shaped external settings load passed |
| Module 2 E2E | Completed |
| Module 3 E2E | PASS |
| Module 4 Editorial E2E | PASS |

## Current constraints

- Transcoding, adaptive streaming, and a production publisher adapter are intentionally absent.
- OSS credentials, production buckets, JWT secrets, database credentials, and CDN settings must be supplied through deployment environments.
- Existing deprecation warnings should be addressed before future major dependency upgrades but do not block v0.5.0.

## Release boundary and next module

CMS Module 4 is approved and finalized for v0.5.0. The project is ready for Module 5 under its separately approved scope. Module 5 has not been started and no Module 5 routes, models, migrations, workers, tests, or documentation are included in this release.
