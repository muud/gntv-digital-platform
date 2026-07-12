# CMS Module 2 — Full Local E2E Validation

Date: 2026-07-12  
Scope: Lovable frontend contract, FastAPI backend, local filesystem, PostgreSQL, and Alibaba OSS abstraction  
Module 3: not started

## Final verdict

# CHANGES REQUIRED

The Module 2 backend passes all functional, security, persistence, migration, OpenAPI, and quality checks. The final local frontend-to-backend E2E verdict cannot be `PASS` because the Lovable CMS media adapter described as using `${VITE_CMS_API_URL}/media/*` is not present in this workspace, and no local environment previously declared `VITE_CMS_API_URL`. The available `frontend-studio` Media CMS still contains simulated upload/progress behavior rather than the stated API adapter. Consequently, real browser upload progress, adapter payload mapping, rendered API errors, and removal of frontend hardcoded URLs cannot be verified locally.

`VITE_CMS_API_URL=http://localhost:8000/api/v1/cms` has been added to `.env.example`, which resolves the missing documented base URL without redesigning the frontend. The actual Lovable adapter source/build must be synced into this workspace before the remaining browser E2E checks can pass.

## Backend E2E results

| Area | Evidence | Result |
|---|---|---|
| JWT login | Real login returned bearer and refresh tokens and authorized media operations | PASS |
| Expired token | Token with past `exp` returned 401 | PASS |
| Unauthorized access | Missing bearer token returned 401 | PASS |
| RBAC | Viewer JWT received 403 for draft listing and upload; admin completed lifecycle | PASS |
| Image upload | Request, local persistence and confirmation reached ready | PASS |
| Video upload | MP4 request, persistence and confirmation reached ready | PASS |
| Audio upload | MP3 request, persistence and confirmation reached ready | PASS |
| Subtitle upload | WebVTT request, persistence and confirmation reached ready | PASS |
| Poster upload | PNG request, persistence and confirmation reached ready | PASS |
| Thumbnail upload | WebP request, persistence and confirmation reached ready | PASS |
| Hero artwork | JPEG direct multipart upload and repeated confirmation reached ready | PASS |
| Channel logo | SVG request, persistence and confirmation reached ready | PASS |
| Upload request | Response keys match `UploadTarget`: asset ID, method, URL, headers and expiry | PASS |
| Direct local upload | Exact bytes persisted under the generated safe storage key | PASS |
| Upload confirmation | Object existence and SHA-256 verified before uploaded/ready state | PASS |
| Failed upload | Checksum mismatch returned structured 400 and persisted failed states | PASS |
| Processing/ready status | Pending-to-ready and failure transitions verified | PASS |
| Listing/grid/list data | Asset response contains identity, filename, MIME, dimensions, status, URL, ownership, dates and metadata | PASS |
| Search | Case-insensitive filename search returned expected asset | PASS |
| Filters | Type, upload status and processing status combination passed | PASS |
| Pagination | Limit, offset, items and total behavior passed | PASS |
| Metadata update | Copyright, language and JSON metadata persisted | PASS |
| Preview/download | Signed URL returned exact uploaded bytes | PASS |
| Signed URL security | Tampered signature returned 403 | PASS |
| Attach/detach | Canonical CMS content relationship added and removed in persistence layer | PASS |
| Soft delete/restore | Hidden after delete and readable after restore | PASS |
| Bulk actions | Bulk delete and restore returned correct affected count | PASS |
| MIME/extension/size | Invalid combinations and oversize payloads rejected | PASS |
| Filename/path safety | Safe storage filename generated; path traversal rejected | PASS |
| Audit logging | Requested, confirmed, updated, attached, detached, deleted and restored events persisted | PASS |
| Local storage persistence | Existence, byte retrieval and SHA-256 passed | PASS |
| Alibaba OSS abstraction | Network-free bucket double passed PUT/GET presigning, headers, existence, upload and streamed checksum | PASS |
| CORS | Browser preflight from `http://localhost:5173` succeeded with allow-origin response | PASS |
| PostgreSQL migration | `venv/bin/python -m alembic upgrade head` reached revision `202607111400` | PASS |
| PostgreSQL ORM persistence | Transactionally rolled-back user/media insert, flush and read round-trip passed | PASS |

## Frontend contract findings

Expected backend base for the declared Lovable pattern:

```env
VITE_CMS_API_URL=http://localhost:8000/api/v1/cms
```

This makes `${VITE_CMS_API_URL}/media/*` resolve to `/api/v1/cms/media/*`, matching OpenAPI.

| Check | Local finding | Result |
|---|---|---|
| Request payloads match schemas | Backend request/response shapes are asserted, but the Lovable adapter source is absent | BLOCKED |
| Response payloads match adapters | No local adapter/types to inspect or execute | BLOCKED |
| Errors displayed correctly | Backend returns verified 400/401/403/404 structures, but no wired UI error renderer is available | BLOCKED |
| Upload progress | Available Media CMS uses simulated timers; no API/XHR progress adapter is present | BLOCKED |
| No hardcoded URLs | Workspace search still finds hardcoded localhost API URLs in shared and broadcast-control sources | FAILED |
| Local CMS environment | `.env.example` now documents `VITE_CMS_API_URL`; the current local `.env` did not contain it | FIXED IN EXAMPLE |

## Commands and quality gates

- Full PyTest: `70 passed`
- MyPy: zero errors across 58 source files
- Ruff: passed
- OpenAPI validator: passed
- Alembic: upgraded PostgreSQL to `202607111400`
- Git whitespace validation: passed
- Authentication coverage: 98.58% (minimum 90%)

The direct `venv/bin/alembic` console wrapper loses the application import path because the workspace path contains spaces. The equivalent canonical module invocation `venv/bin/python -m alembic upgrade head` succeeds.

## Required before PASS

1. Sync the Lovable CMS Module 2 adapter/components into the local workspace.
2. Set `VITE_CMS_API_URL` in the frontend runtime environment to `http://localhost:8000/api/v1/cms` for local E2E.
3. Run the browser flow against the local backend and confirm progress, schema adapters, preview, and displayed 400/401/403/404 errors.
4. Remove or centralize the remaining hardcoded API URLs within the frontend scope.

Module 3 remains blocked pending final approval.
