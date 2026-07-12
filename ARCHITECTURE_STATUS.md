# Architecture Status — v0.4.0

Status date: 2026-07-12

| Layer | Status | Implementation |
|---|---|---|
| Application foundation | Complete | FastAPI, configuration, CORS, health, Redis lifecycle, OpenAPI |
| Authentication | Complete | JWT, verification, refresh, sessions/devices, password reset, RBAC, audit |
| CMS Content Core | Complete | Content, taxonomy, localization, workflow, permissions, events, workers |
| Media Library | Complete | DAM records, local/OSS providers, signed flows, validation, attachments |
| Premium Catalog | Complete | Titles, hierarchy, channels, audio, collections, progress, recommendations |
| Database | Complete for v0.4.0 | SQLAlchemy 2.x and PostgreSQL Alembic head `202607121200` |
| API contracts | Complete for v0.4.0 | Versioned REST endpoints and validated OpenAPI |
| Media transcoding | Not implemented | Reserved for a later approved module |
| CDN/HLS packaging | Not implemented | Outside v0.4.0 scope |

## Architectural boundaries

- The canonical editorial graph remains `cms_content`.
- The canonical DAM graph remains `cms_media_files`, referenced by editorial content and catalog records.
- The catalog domain owns consumer-facing streaming metadata and personalization without duplicating media storage.
- Repository and service layers isolate persistence and business rules from FastAPI routes.
- AI and antivirus capabilities are protocol-based extension points; no external processing is triggered by default.

## Quality attributes

- Security: JWT, RBAC scopes, signed media access, file validation, checksum verification, and audit events.
- Portability: local storage in development and Alibaba OSS in production through one provider contract.
- Evolvability: catalog metadata, AI hooks, processing workers, and storage are independently extensible.
- Verification: 73 tests, 98.58% coverage, MyPy zero, Ruff pass, OpenAPI pass, PostgreSQL migration/round-trip pass.
