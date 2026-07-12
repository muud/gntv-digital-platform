# Changelog

All notable changes to GNTV DIGITAL are documented here.

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
