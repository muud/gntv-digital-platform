# GNTV DIGITAL — CMS Module 4 Release Summary

**Release:** v0.5.0

**Release date:** 2026-07-19

**Status:** FINALIZED

**Scope:** CMS Module 4 Editorial Workflow & Publishing backend and release-blocker hotfix verification

## Delivered capability

CMS Module 4 provides a ten-state editorial lifecycle covering draft, review, fact check, legal review, editorial approval, approval, scheduling, publication, expiry, and archive. Service-layer authorization governs state changes and publication actions. The module also includes assignments, planning, comments and review notes, mentions, activity history, revision creation/comparison/restore, notification outbox records, dashboards, audit events, and optimistic locking.

The v0.5.0 hotfix adds an explicit privileged restore operation for archived workflows. Administrators and chief editors can return archived content to `approved` for a new scheduling or publishing decision; obsolete scheduling, embargo, unpublish, publication, and failure fields are cleared and the lock version is incremented.

## Release blockers resolved

1. Editorial activity and audit payloads are normalized with FastAPI's JSON-safe encoder before JSON-column persistence, preventing PostgreSQL due-date serialization failures.
2. `POST /api/v1/editorial/workflows/{workflow_id}/restore` restores archived workflows safely and emits activity, audit, and notification events.
3. Editorial OpenAPI verification covers all 25 Editorial paths, validates success responses, and exposes notification dismissal.
4. Regression coverage verifies the complete transition registry, archived restoration authorization and locking, and datetime serialization.

## Verification evidence

| Gate | Result |
|---|---:|
| PyTest | PASS — 79 tests |
| Configured coverage | PASS — 98.58% |
| MyPy | PASS — 87 source files |
| Ruff | PASS |
| OpenAPI validation | PASS |
| Editorial OpenAPI inventory | PASS — 25 paths, 28 operations |
| Alembic | PASS — `202607131200 (head)` |
| PostgreSQL Editorial lifecycle | PASS |
| Diff integrity | PASS — no whitespace errors |

Expected negative-path responses for authentication, authorization, optimistic-lock conflicts, and invalid transitions were exercised without server errors. The suite reports existing dependency deprecation warnings; they do not fail the configured release gates.

## Included release changes

- Editorial API, request schemas, and service hotfixes.
- Editorial lifecycle and OpenAPI regression tests.
- Editorial API documentation.
- v0.5.0 changelog, release notes, project status, architecture status, and this release summary.

No database migration was required by the hotfix; the Module 4 migration remains Alembic revision `202607131200`.

## Release boundary

CMS Module 4 is finalized by this release. CMS Module 5 has not been started and is explicitly excluded. This release creates no Module 5 routes, models, migrations, workers, tests, or documentation and does not authorize Module 5 implementation.
