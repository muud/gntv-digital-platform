# GNTV DIGITAL Processing API — Frontend Contract

This is the concise integration contract for the FastAPI routes currently registered under `/api/v1/processing`. The machine-readable source is [`processing-openapi.json`](./processing-openapi.json), exported as OpenAPI 3.1.0.

## Authentication and authorization

Every operation requires `Authorization: Bearer <access-token>` using the `HTTPBearer` security scheme.

| Operations | Required RBAC scope | Roles currently granting it |
|---|---|---|
| All `GET` operations and `POST /manifests/validate` | `channel:read-operations` | `admin`, `chief_editor`, `producer`, `operator`, `editor` |
| `POST /jobs`, `DELETE /jobs/{job_id}` | `stream:control` | `admin`, `chief_editor`, `producer`, `operator` |

Missing or invalid credentials return `401`. An authenticated user without the operation's scope receives `403` with `detail.code = "streaming_forbidden"` and `detail.required_scope`.

## Registered operations

All paths below are relative to `/api/v1/processing`.

| Method | Path | Query parameters | Request | Success response | Scope |
|---|---|---|---|---|---|
| `GET` | `/jobs` | `limit`: integer, default 50, 1–100; `offset`: integer, default 0, ≥0 | — | `200 ProcessingJobPage` | `channel:read-operations` |
| `POST` | `/jobs` | — | `ProcessingJobCreateRequest` | `202 ProcessingJobResponse` | `stream:control` |
| `GET` | `/jobs/{job_id}` | —; `job_id` is a required UUID path parameter | — | `200 ProcessingJobResponse` | `channel:read-operations` |
| `DELETE` | `/jobs/{job_id}` | —; `job_id` is a required UUID path parameter | — | `200 ProcessingJobCancelResponse` | `stream:control` |
| `GET` | `/workers` | — | — | `200 WorkerStatusResponse[]` | `channel:read-operations` |
| `GET` | `/queues` | — | — | `200 QueueTelemetryResponse` | `channel:read-operations` |
| `GET` | `/metrics` | `job_id`: optional UUID | — | `200 MetricsPage` | `channel:read-operations` |
| `GET` | `/manifests` | `limit`: integer, default 50, 1–100; `offset`: integer, default 0, ≥0 | — | `200 ManifestPage` | `channel:read-operations` |
| `GET` | `/manifests/{manifest_id}` | —; `manifest_id` is a required UUID path parameter | — | `200 ManifestStatusResponse` | `channel:read-operations` |
| `POST` | `/manifests/validate` | — | `ManifestValidationRequest` | `200 ManifestValidationResponse` | `channel:read-operations` |
| `GET` | `/thumbnails` | `limit`: integer, default 50, 1–100; `offset`: integer, default 0, ≥0 | — | `200 ThumbnailPage` | `channel:read-operations` |
| `GET` | `/thumbnails/{thumbnail_id}` | —; `thumbnail_id` is a required UUID path parameter | — | `200 ThumbnailStatusResponse` | `channel:read-operations` |

`/manifests/validate` and `/thumbnails/{thumbnail_id}` are registered API extensions and therefore appear in the exact route export.

## Job creation request

`ProcessingJobCreateRequest` rejects unknown fields.

| Field | Type | Required/default | Rules |
|---|---|---|---|
| `idempotency_key` | string | required | 8–128 characters |
| `job_type` | enum | required | `vod_transcode`, `live_transcode`, `manifest`, `thumbnail` |
| `input_url` | string | required | 1–2048 characters; validated as an approved local/RTMP/SRT input |
| `output_prefix` | string | required | 1–512 characters; safe relative path |
| `renditions` | unique enum array | `["1080p","720p","480p"]` | non-empty; values: `1080p`, `720p`, `480p` |
| `queue` | enum or null | null | `transcode-cpu`, `transcode-accelerated`, `manifest`, `thumbnail`; must match `job_type` |
| `stream_id` | UUID or null | null | — |
| `recording_id` | UUID or null | null | — |
| `max_attempts` | integer | 3 | 1–10 |
| `timeout_seconds` | number | 900 | 1–86400 |
| `workspace` | string or null | null | 1–1024 characters; required for `manifest` and `thumbnail` jobs |
| `thumbnail_kinds` | unique enum array | `["poster","preview","timeline"]` | values: `poster`, `preview`, `timeline` |
| `thumbnail_interval_seconds` | integer | 10 | 1–3600 |

Queue routing is constrained as follows:

- `vod_transcode` and `live_transcode`: `transcode-cpu` or `transcode-accelerated`; default `transcode-cpu`.
- `manifest`: queue must be `manifest`.
- `thumbnail`: queue must be `thumbnail`.

### Idempotency

There is **no registered `Idempotency-Key` HTTP header**. The required JSON property `idempotency_key` is the canonical key and is also used as the Celery task ID. Repeating `POST /jobs` with an existing successful key returns the original job as `202` and does not enqueue a second task. Clients must persist and reuse the same body key when retrying an uncertain request.

## Other request schemas

`ManifestValidationRequest` rejects unknown fields and contains one required `manifest_url` string of 1–1024 characters. Validation supports local `.m3u8` and `.mpd` manifests within the configured processing output root.

## Response and pagination models

- `ProcessingJobResponse`: `job_id`, `job_type`, `status`, `queue`, `attempt`, `max_attempts`, `progress` (0–100), `metrics`, nullable `worker_id`, nullable `error_code`, nullable `error_detail`, `created_at`, nullable `started_at`, nullable `completed_at`.
- `ProcessingJobPage`: `{ "items": ProcessingJobResponse[], "total": integer }`.
- `ProcessingJobCancelResponse`: `{ "job_id": UUID, "status": "CANCELLED", "terminated_at": date-time }`.
- `WorkerStatusResponse`: worker identity, queue, status, health, heartbeat, and hardware telemetry.
- `QueueTelemetryResponse`: broker status and a map of queues to queued, leased, running, retrying, and active-worker counts.
- `ProcessingMetricsResponse`: job and queue identifiers plus optional duration, wait time, FPS, speed factor, CPU, dropped-frame, freshness, and observation values.
- `MetricsPage`: `{ "items": ProcessingMetricsResponse[], "total": integer }`.
- `ManifestStatusResponse`: IDs, format, kind, status, internal `manifest_path`, generation, renditions, and publication time.
- `ManifestPage`: `{ "items": ManifestStatusResponse[], "total": integer }`.
- `ManifestValidationResponse`: `valid`, nullable `format`, `conformance`, and validation details.
- `ThumbnailStatusResponse`: IDs, kind, timestamp, dimensions, status, and internal `asset_path`.
- `ThumbnailPage`: `{ "items": ThumbnailStatusResponse[], "total": integer }`.

Pagination uses offset/limit only. Page responses contain `items` and the unpaginated `total`; they do not include cursors, page numbers, or next-page URLs.

## Enum values

| Enum | Values |
|---|---|
| Job type | `vod_transcode`, `live_transcode`, `manifest`, `thumbnail` |
| Queue | `transcode-cpu`, `transcode-accelerated`, `manifest`, `thumbnail` |
| Rendition | `1080p`, `720p`, `480p` |
| Thumbnail request kind | `poster`, `preview`, `timeline` |
| Manifest format | `hls`, `dash` |
| Manifest kind | `live`, `event`, `vod` |
| Manifest status | `building`, `ready`, `stale`, `revoked`, `failed` |
| Stored thumbnail kind | `poster`, `keyframe`, `sprite`, `preview` |
| Thumbnail status | `queued`, `ready`, `failed`, `deleted` |
| Cancellation status | `CANCELLED` |

Job and worker `status` fields are strings rather than closed OpenAPI enums. Current job values include `QUEUED`, `CLAIMED`, `PROCESSING` phase names, `RETRYING`, `COMPLETED`, `FAILED`, and `CANCELLED`; frontends must tolerate new phase strings.

## Errors

Error bodies use FastAPI's envelope: `{ "detail": ... }`.

| Status | When |
|---|---|
| `401` | Bearer token is absent, invalid, expired, or does not identify a valid user/session |
| `403` | Account/session policy rejects access or the required RBAC scope is missing |
| `404` | A requested job, manifest, or thumbnail does not exist |
| `409` | Job creation cannot validate/persist/enqueue, or cancellation targets a terminal job |
| `422` | Path, query, or JSON data fails FastAPI/Pydantic validation |

Processing `404` and `409` details have `{ "code": "processing_not_found" | "processing_conflict", "message": string }`. Pydantic validation errors use FastAPI's standard `HTTPValidationError`.

## Cancellation semantics

`DELETE /jobs/{job_id}` accepts only a non-terminal job. It marks the durable job `CANCELLED`, clears its lease, asks Celery to revoke the task using the request's `idempotency_key` as task ID with termination enabled (`SIGTERM`), records `completed_at`, and returns `200`.

- Unknown job: `404 processing_not_found`.
- Already `succeeded`, `failed`, or `cancelled`: `409 processing_conflict`.
- A repeated cancellation is therefore not a second `200`; it returns `409`.

The response confirms orchestration acceptance and durable cancellation state. It does not guarantee that an external process has already exited at the instant the response reaches the browser.

## Scope boundary

This contract does not expose playback, DVR, catch-up, CDN publishing, DRM, or Alibaba SDK operations.
