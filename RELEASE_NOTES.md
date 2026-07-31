# GNTV DIGITAL v0.5.0 Release Notes

Release date: 2026-07-20
Release status: **Released — CMS Module 4 approved and finalized**

GNTV DIGITAL v0.5.0 completes the backend Editorial Workflow & Publishing module and its release-blocking verification hotfixes. It builds on the platform, authentication, Content Core, Media Library, and Premium Streaming Catalog delivered through v0.4.0.

## Highlights

- Ten-state editorial lifecycle from draft through review, approval, scheduling, publication, expiry, and archive.
- Role-enforced transitions, assignment queues, planning, comments, review notes, mentions, revision comparison and restore, and activity history.
- Immediate and scheduled publishing, embargo and unpublish planning, due-work processing, reminders, notification outbox records, dashboards, audit trails, and optimistic locking.
- An explicit admin/chief-editor archived-workflow restore operation that returns content to `approved` and clears obsolete publication planning.
- PostgreSQL-safe serialization of datetime values in Editorial activity and audit JSON payloads.

## API and database

- The canonical Editorial namespace is `/api/v1/editorial` with 25 documented paths.
- OpenAPI validation and operation-level Editorial response-schema checks pass.
- Database schema is managed through Alembic revision `202607131200`.
- Apply migrations with `cd backend-api && venv/bin/python -m alembic upgrade head`.

## Quality status

The release was verified with 79 passing tests, 98.58% configured coverage, zero MyPy errors across 87 source files, passing Ruff checks, valid OpenAPI 3.1, Alembic single head `202607131200`, and a successful PostgreSQL Editorial lifecycle run. Production-shaped settings also loaded successfully with externalized PostgreSQL, Redis, OSS, JWT, and media-signing values.

## Explicit exclusions

This release does not start or include CMS Module 5. Distribution and geo-fencing work remains outside the authorized release scope. FFmpeg transcoding, adaptive bitrate packaging, CDN publication, and a production downstream publisher adapter also remain future work.

CMS Module 4 approval makes the project ready to begin Module 5 as a separate implementation effort; no Module 5 code is included in v0.5.0.

## Upgrade notes

1. Back up the PostgreSQL database.
2. Configure environment variables from `.env.example`; never commit real secrets.
3. Install `backend-api/requirements.txt` in the backend virtual environment.
4. Run Alembic to head.
5. Confirm local/OSS media configuration and JWT secrets before exposing the API.
