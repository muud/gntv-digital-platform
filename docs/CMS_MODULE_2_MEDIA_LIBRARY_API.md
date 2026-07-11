# CMS Module 2 — Media Library API

Base path: `/api/v1/cms/media`. All operations require an authenticated CMS role. Reads require `asset:read-draft`; mutations require `asset:write`.

## Upload lifecycle

1. `POST /uploads` validates the declared MIME type, extension, size and SHA-256 checksum and creates a pending asset.
2. Upload to the returned signed `PUT` target. Local development may use `PUT /{asset_id}/upload` with multipart field `file`; OSS uses its presigned target.
3. `POST /{asset_id}/confirm` with the SHA-256 checksum. The service verifies object existence and its computed checksum, then marks the asset `uploaded/ready` or `failed/failed`.
4. `POST /{asset_id}/attachments` links a ready reusable asset to canonical CMS content.

Metadata extraction, antivirus scanning, and later video processing are represented by protocols in `media/workers`; Module 2 does not invoke FFmpeg.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/uploads` | Create an upload request and signed target |
| PUT | `/{asset_id}/upload` | Local-development direct upload |
| POST | `/{asset_id}/confirm` | Verify checksum and finalize upload |
| GET | `/` | Search, filter, and paginate assets |
| GET | `/{asset_id}` | Asset detail and signed/public download URL |
| PATCH | `/{asset_id}` | Copyright, licensing, language, URL and custom metadata |
| POST | `/{asset_id}/attachments` | Attach to CMS content |
| DELETE | `/{asset_id}/attachments/{content_id}` | Detach from content |
| DELETE | `/{asset_id}` | Soft delete |
| POST | `/{asset_id}/restore` | Restore |
| POST | `/bulk/actions` | Bulk delete or restore, up to 100 assets |

List filters: `search`, `asset_type`, `upload_status`, `processing_status`, `include_deleted`, `limit`, and `offset`.

## Storage configuration

Use `MEDIA_STORAGE_PROVIDER=local` in development or `MEDIA_STORAGE_PROVIDER=oss` in production. Local root, signing secret, size limit and URL TTL are environment-driven. OSS endpoint, bucket and credentials use `OSS_*` environment variables and are never embedded in source.

The canonical table remains `cms_media_files`, preserving Module 1 content relationships. Migration `202607111400` extends it in place.
