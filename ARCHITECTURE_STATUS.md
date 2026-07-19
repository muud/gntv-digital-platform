# Architecture Status — v0.5.0

Status date: 2026-07-19

| Layer | Status | Implementation |
|---|---|---|
| Application foundation | Complete | FastAPI, configuration, CORS, health, Redis lifecycle, OpenAPI |
| Authentication | Complete | JWT, verification, refresh, sessions/devices, password reset, RBAC, audit |
| CMS Content Core | Complete | Content, taxonomy, localization, workflow, permissions, events, workers |
| Media Library | Complete | DAM records, local/OSS providers, signed flows, validation, attachments |
| Premium Catalog | Complete | Titles, hierarchy, channels, audio, collections, progress, recommendations |
| Editorial Workflow & Publishing | Complete for v0.5.0 | Ten-state workflow, RBAC transitions, assignments, collaboration, revisions, scheduling, notifications, audit, optimistic locking, archived restore |
| Database | Complete for v0.5.0 | SQLAlchemy 2.x and PostgreSQL Alembic head `202607131200` |
| API contracts | Complete for v0.5.0 | Versioned REST endpoints, 25 Editorial paths, and validated OpenAPI response contracts |
| Media transcoding | Not implemented | Reserved for a later approved module |
| CDN/HLS packaging | Not implemented | Outside v0.4.0 scope |

## Architectural boundaries

- The canonical editorial graph remains `cms_content`.
- The canonical DAM graph remains `cms_media_files`, referenced by editorial content and catalog records.
- The catalog domain owns consumer-facing streaming metadata and personalization without duplicating media storage.
- The Editorial domain owns workflow state, planning, review collaboration, revision attribution, publication scheduling, notification outbox records, and workflow audit events while continuing to reference canonical `cms_content` records.
- Archived workflows remain terminal in the generic transition graph; the explicit, privileged restore operation returns them to `approved` and clears obsolete publication state.
- Repository and service layers isolate persistence and business rules from FastAPI routes.
- AI and antivirus capabilities are protocol-based extension points; no external processing is triggered by default.

## Quality attributes

- Security: JWT, RBAC scopes, signed media access, file validation, checksum verification, and audit events.
- Portability: local storage in development and Alibaba OSS in production through one provider contract.
- Evolvability: catalog metadata, AI hooks, processing workers, and storage are independently extensible.
- Verification: 79 tests, 98.58% configured coverage, MyPy zero across 87 files, Ruff pass, OpenAPI pass, PostgreSQL migration and Editorial lifecycle pass.

## Release boundary

CMS Module 5 distribution and geo-fencing architecture is not implemented by v0.5.0. No Module 5 routes, models, migrations, workers, tests, or release claims are included.
