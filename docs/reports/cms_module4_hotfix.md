# CMS Module 4 Release-Blocker Hotfix

**Date:** 14 July 2026

**Scope:** The four Antigravity release blockers only

**Module 5:** Not started

## Hotfix result

All requested CMS Module 4 backend release blockers are resolved and verified against the real local FastAPI and PostgreSQL services.

## 1. `PATCH /planning` datetime serialization

**Status: PASS**

- Editorial activity and audit payloads are now normalized through FastAPI's JSON-safe encoder at the common event boundary.
- Workflow model updates continue to receive native `datetime` values, while JSON activity/audit columns receive ISO-8601 strings.
- The regression test updates both priority and due date and asserts that `editorial_activity.data.due_at` and `audit_logs.metadata.due_at` are strings.
- Real PostgreSQL E2E returned HTTP 200 for the due-date update.
- Real PostgreSQL evidence:
  - workflow due date: `2026-07-15T14:46:51.144098Z`
  - activity due-date type: `str`
  - audit due-date type: `str`
  - stale concurrent planning update: HTTP 409
- No HTTP 500 occurred in the completed live run.

## 2. Archived → Restore workflow

**Status: PASS**

- Added `POST /api/v1/editorial/workflows/{workflow_id}/restore`.
- Added the explicit `WorkflowRestoreRequest` contract with `expected_version` and optional `reason`.
- Restore is allowed only when the current state is `archived` and only for `admin` or `chief_editor`.
- Restore moves the workflow to `approved`, increments `lock_version`, and clears obsolete schedule, timezone, embargo, unpublish, publish, and failure fields.
- Restore emits:
  - activity event `workflow.restored`
  - audit event `editorial.workflow.restored`
  - in-app, email, and webhook outbox events `editorial.workflow.restored`
- Invalid-state restore returns HTTP 422; unauthorized restore returns HTTP 403.
- Real PostgreSQL E2E observed `archived → approved`, HTTP 200, with lock version incremented to 8.
- Revision snapshot restore remains a separate existing endpoint and is unchanged.

## 3. Editorial OpenAPI schemas

**Status: PASS**

- The served OpenAPI document passes `openapi-spec-validator`.
- Added an automated contract test that enumerates every Editorial operation and verifies:
  - the Editorial tag is present
  - at least one success response is declared
  - JSON success responses contain a schema
- The notification-dismiss endpoint is now included in OpenAPI instead of being hidden.
- Live schema evidence:
  - 25 Editorial paths
  - 28 Editorial operations
  - 85 component schemas in the complete API document
  - archived restore path present
  - notification-dismiss path present with a valid 204 response

## 4. Full Editorial E2E rerun

**Status: PASS**

The real local PostgreSQL/FastAPI scenario re-exercised all Editorial endpoint groups:

| Area | Verified result |
|---|---|
| Workflow | draft, in review, fact check, legal review, editorial approval, approved, scheduled, published, expired, archived, restored to approved |
| Planning | priority and due-date update 200; stale update 409 |
| Assignments | reporter, editor, producer, reassignment, list, assigned-to-me |
| Collaboration | internal, review, rejection, approval notes, mentions, activity |
| Versioning | create/list revisions, compare, revision restore, attribution |
| Publishing | immediate publish, scheduled publish, embargo rejection, auto-publish, auto-unpublish, republish, emergency unpublish |
| Notifications | in-app, email, webhook, reminders, restore and publishing events, dismiss 204 |
| Dashboards | pending, assigned, scheduled, queue, failures, recent activity |
| Security | valid JWT, missing token 401, viewer 403, reporter publish 403, optimistic lock 409 |
| PostgreSQL | read/write round-trip succeeded on PostgreSQL 15.18 |

Expected negative-path responses (401, 403, 409, and 422) were observed without server errors.

## Verification gates

| Gate | Result |
|---|---:|
| `mypy --config-file mypy.ini app tests alembic` | PASS — 87 source files |
| `ruff check app tests alembic` | PASS |
| `pytest -q --disable-warnings` | PASS — 79 tests |
| Configured coverage gate | PASS — 98.58% |
| `alembic upgrade head` | PASS |
| Alembic current revision | `202607131200 (head)` |
| PostgreSQL container health | PASS |
| FastAPI startup | PASS |
| Served OpenAPI validation | PASS |
| Real Editorial API E2E | PASS |

The suite reports 865 existing deprecation warnings; they do not fail the configured quality gate and are outside this restricted hotfix scope.

## Files changed

- `backend-api/app/modules/editorial/service.py`
- `backend-api/app/modules/editorial/api.py`
- `backend-api/app/modules/editorial/schemas.py`
- `backend-api/tests/test_editorial_module4.py`
- `backend-api/tests/test_openapi.py`
- `docs/CMS_MODULE_4_EDITORIAL_API.md`
- `docs/reports/cms_module4_hotfix.md`

No schema migration was required. No Module 5 code, routes, models, migrations, workers, or documentation were created.

## Verdict

PASS
