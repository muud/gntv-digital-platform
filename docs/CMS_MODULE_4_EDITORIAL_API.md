# GNTV DIGITAL CMS Module 4 — Editorial API

## Overview

Module 4 adds an editorial workflow around Module 1 `cms_content` records without changing the existing content, media, or catalog APIs. All endpoints are versioned under `/api/v1/editorial`, require bearer authentication, and appear in the generated OpenAPI document under **CMS Editorial Workflow**.

The workflow resource uses `lock_version` for optimistic concurrency. Every mutation that can race requires `expected_version`; a stale value returns HTTP `409` with code `editorial_optimistic_lock_conflict`.

## Workflow

The standard forward path is:

`draft → in_review → fact_check → legal_review → editorial_approval → approved → scheduled → published → expired → archived`

Approved content may publish immediately. Published content may be emergency-unpublished to `expired`, and expired content may be republished. Review stages may reject content back to `draft`; a rejection note is mandatory. Terminal archived content cannot transition.

Transition authorization is enforced in the service layer:

| Target/action | Authorized roles |
|---|---|
| In review | admin, chief_editor, editor, reporter, producer |
| Fact check | admin, chief_editor, editor |
| Legal review | admin, chief_editor, fact_checker |
| Editorial approval | admin, chief_editor, editor, legal_reviewer |
| Approved | admin, chief_editor |
| Schedule/publish | admin, chief_editor, producer |
| Emergency unpublish/republish | admin, chief_editor |
| Archive | admin, chief_editor |

## Endpoints

### Workflow and assignments

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/workflows` | Start a draft workflow for a `cms_content` ID |
| `GET` | `/workflows/{workflow_id}` | Read workflow state and publication plan |
| `PATCH` | `/workflows/{workflow_id}/planning` | Set priority and due date |
| `POST` | `/workflows/{workflow_id}/transitions` | Apply an authorized state transition |
| `PUT` | `/workflows/{workflow_id}/assignments` | Assign or reassign reporter, editor, or producer |
| `GET` | `/workflows/{workflow_id}/assignments` | List current assignments |

Create example:

```json
{
  "content_id": "5a5214b7-4386-4d07-b2f0-cee53c80289e",
  "priority": "high",
  "due_at": "2026-07-14T17:00:00+03:00"
}
```

Transition example:

```json
{
  "target_state": "fact_check",
  "expected_version": 4,
  "note": "Desk review completed"
}
```

### Collaboration

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/workflows/{workflow_id}/comments` | Add internal comment, review note, rejection reason, or approval note |
| `GET` | `/workflows/{workflow_id}/comments` | List collaboration history |
| `GET` | `/workflows/{workflow_id}/activity` | Read immutable activity timeline |

Comments accept a `mentions` array of user IDs. Each mention creates in-app, email-ready, and webhook-ready notification events.

### Revisions

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/workflows/{workflow_id}/revisions` | Store a JSON content snapshot with summary and editor attribution |
| `GET` | `/workflows/{workflow_id}/revisions` | List revisions, newest first |
| `GET` | `/workflows/{workflow_id}/revisions/compare?from_version=1&to_version=2` | Return field-level changes |
| `POST` | `/workflows/{workflow_id}/revisions/{version}/restore?expected_version=4` | Create a new revision from an old snapshot |

Restore never destroys revision history; it creates a new attributed version.

### Publishing

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/workflows/{workflow_id}/schedule` | Schedule timezone-aware publication, embargo, and auto-unpublish |
| `POST` | `/workflows/{workflow_id}/publish` | Publish approved or scheduled content immediately |
| `POST` | `/workflows/{workflow_id}/republish` | Republish expired content |
| `POST` | `/workflows/{workflow_id}/emergency-unpublish` | Immediately expire published content; reason required |
| `POST` | `/publishing/process-due` | Process auto-publish and auto-unpublish queue |

Scheduling uses IANA timezone names. All date values must include a UTC offset and are normalized to UTC for persistence.

```json
{
  "publish_at": "2026-07-15T06:00:00+03:00",
  "timezone": "Africa/Nairobi",
  "embargo_at": "2026-07-15T05:00:00+03:00",
  "unpublish_at": "2026-07-16T06:00:00+03:00",
  "expected_version": 8
}
```

### Notifications and dashboards

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/notifications` | List in-app, email-ready, and webhook-ready events |
| `POST` | `/notifications/review-reminders` | Emit reminders for overdue active reviews |
| `GET` | `/dashboard/pending-reviews` | Review, fact-check, legal, and approval work |
| `GET` | `/dashboard/assigned-to-me` | Work assigned to the current user |
| `GET` | `/dashboard/scheduled-content` | Scheduled items |
| `GET` | `/dashboard/publishing-queue` | Approved and scheduled items |
| `GET` | `/dashboard/failed-publications` | Items with a recorded publishing error |
| `GET` | `/dashboard/recent-activity` | Latest editorial events |

Notification rows are an outbox-style delivery interface. Channel values are `in_app`, `email`, and `webhook`; external delivery workers can set `delivered_at` after dispatch. Events cover assignments, mentions, state changes, review reminders, scheduled publication, successful publication, and publishing failures.

## Error contract

Errors use FastAPI's `detail` envelope:

```json
{
  "detail": {
    "code": "editorial_invalid_transition",
    "message": "Only approved content can be scheduled"
  }
}
```

Relevant status codes are `403` for RBAC/scope denial, `404` for missing content/workflows/revisions/users, `409` for duplicate workflows or stale lock versions, and `422` for transition or schedule validation failures.

## Persistence and audit

The Alembic revision is `202607131200`, following Module 3 revision `202607121200`. It creates `editorial_workflows`, `editorial_assignments`, `editorial_comments`, `editorial_revisions`, `editorial_activity`, and `editorial_notifications`. Security-sensitive actions also write `audit_logs` events prefixed with `editorial.`.
