# GNTV DIGITAL v0.4.0 Release Notes

Release date: 2026-07-12  
Release status: **Stable CMS foundation milestone**

GNTV DIGITAL v0.4.0 completes the first three CMS modules on top of the platform and authentication foundations. The release provides an editorial content core, production-oriented digital asset management, and a premium streaming catalog engine.

## Highlights

- Editorial content workflow with multilingual taxonomy and CMS RBAC.
- Secure media ingest for images, video/audio sources, artwork, subtitles, captions, transcripts, previews, and attachments.
- Local filesystem support for development and Alibaba OSS abstraction for production.
- Premium catalog modeling for on-demand, episodic, live, audio, kids, short-form, and news experiences.
- Home-screen collections and featured rows, Continue Watching, ratings, and recommendation foundations.
- Cast, crew, director, producer, studio, SEO, and AI-enrichment metadata.

## API and database

- Canonical API namespaces: `/api/v1/auth`, `/api/v1/cms`, `/api/v1/cms/media`, and `/api/v1/catalog`.
- OpenAPI validation is enabled and passing.
- Database schema is managed through Alembic revision `202607121200`.
- Apply migrations with `cd backend-api && venv/bin/python -m alembic upgrade head`.

## Quality status

The release was verified with 73 passing tests, 98.58% coverage, zero MyPy errors, passing Ruff checks, valid OpenAPI, and PostgreSQL persistence checks.

## Explicit exclusions

This release does not include FFmpeg transcoding, adaptive bitrate packaging, CDN publication, or Module 4. Media processing interfaces are extension points only.

## Upgrade notes

1. Back up the PostgreSQL database.
2. Configure environment variables from `.env.example`; never commit real secrets.
3. Install `backend-api/requirements.txt` in the backend virtual environment.
4. Run Alembic to head.
5. Confirm local/OSS media configuration and JWT secrets before exposing the API.
