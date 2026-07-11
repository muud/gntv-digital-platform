"""Media Library application service."""

from datetime import UTC, datetime, timedelta
import builtins
from pathlib import Path
import re
from typing import Any
from uuid import UUID, uuid4

from app.modules.cms.media.models import AssetType, CMSMediaFile, ProcessingStatus, UploadStatus, URLStrategy
from app.modules.cms.media.repositories import MediaRepository
from app.modules.cms.media.schemas import AssetListResponse, AssetResponse, AssetUpdate, UploadRequest, UploadTarget
from app.modules.cms.media.services.storage import StorageProvider
from app.repositories.audit_repository import AuditRepository


class MediaError(RuntimeError):
    code = "media_error"


class MediaNotFound(MediaError):
    code = "media_not_found"


class MediaValidationError(MediaError):
    code = "media_validation_error"


ALLOWED: dict[AssetType, set[str]] = {
    AssetType.IMAGE: {"image/jpeg", "image/png", "image/webp", "image/gif"},
    AssetType.POSTER: {"image/jpeg", "image/png", "image/webp"},
    AssetType.THUMBNAIL: {"image/jpeg", "image/png", "image/webp"},
    AssetType.HERO: {"image/jpeg", "image/png", "image/webp"},
    AssetType.CHANNEL_LOGO: {"image/png", "image/svg+xml", "image/webp"},
    AssetType.VIDEO: {"video/mp4", "video/quicktime", "video/x-matroska"},
    AssetType.TRAILER: {"video/mp4", "video/quicktime"},
    AssetType.PREVIEW: {"video/mp4", "video/quicktime"},
    AssetType.AUDIO: {"audio/mpeg", "audio/wav", "audio/mp4", "audio/ogg"},
    AssetType.SUBTITLE: {"text/vtt", "application/x-subrip", "text/plain"},
    AssetType.CAPTION: {"text/vtt", "application/x-subrip", "text/plain"},
    AssetType.TRANSCRIPT: {"text/plain", "text/vtt", "application/pdf"},
    AssetType.ATTACHMENT: {"application/pdf", "text/plain", "application/zip"},
}
MIME_EXTENSIONS = {"image/jpeg": {".jpg", ".jpeg"}, "image/png": {".png"}, "image/webp": {".webp"}, "image/gif": {".gif"}, "image/svg+xml": {".svg"}, "video/mp4": {".mp4"}, "video/quicktime": {".mov"}, "video/x-matroska": {".mkv"}, "audio/mpeg": {".mp3"}, "audio/wav": {".wav"}, "audio/mp4": {".m4a"}, "audio/ogg": {".ogg"}, "text/vtt": {".vtt"}, "application/x-subrip": {".srt"}, "text/plain": {".txt"}, "application/pdf": {".pdf"}, "application/zip": {".zip"}}


class MediaService:
    def __init__(self, repository: MediaRepository, storage: StorageProvider, audit: AuditRepository | None, max_file_size: int, url_ttl: int) -> None:
        self.repository, self.storage, self.audit = repository, storage, audit
        self.max_file_size, self.url_ttl = max_file_size, url_ttl

    def request_upload(self, payload: UploadRequest, actor_id: int) -> UploadTarget:
        self._validate(payload)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(payload.filename).name).strip("._") or "asset"
        asset_id, ext = uuid4(), Path(safe).suffix.lower()
        storage_filename = f"{asset_id.hex}{ext}"
        key = f"media/{datetime.now(UTC):%Y/%m}/{asset_id}/{storage_filename}"
        asset = CMSMediaFile(id=asset_id, asset_type=payload.asset_type, original_filename=payload.filename, storage_filename=storage_filename, mime_type=payload.mime_type.lower(), file_size=payload.file_size, language_code=payload.language_code, storage_provider=self.storage.name, storage_key=key, url_strategy=payload.url_strategy, checksum=payload.checksum.lower(), upload_status=UploadStatus.PENDING, processing_status=ProcessingStatus.PENDING, owner_id=actor_id, created_by=actor_id, updated_by=actor_id, metadata_json=payload.metadata, file_type=payload.asset_type.value, url="")
        self.repository.add(asset)
        url, headers = self.storage.create_upload_url(key, payload.mime_type, self.url_ttl)
        self._audit(actor_id, "cms.media.upload_requested", asset_id)
        return UploadTarget(asset_id=asset_id, upload_url=url, headers=headers, expires_at=datetime.now(UTC) + timedelta(seconds=self.url_ttl))

    def direct_upload(self, asset_id: UUID, data: bytes, actor_id: int) -> AssetResponse:
        asset = self._asset(asset_id)
        if len(data) != asset.file_size:
            raise MediaValidationError("File size does not match upload request")
        self.storage.put(asset.storage_key, data)
        return self.confirm(asset_id, asset.checksum, actor_id)

    def confirm(self, asset_id: UUID, checksum: str, actor_id: int) -> AssetResponse:
        asset = self._asset(asset_id)
        if not self.storage.exists(asset.storage_key):
            raise MediaValidationError("Uploaded object was not found")
        actual = self.storage.checksum(asset.storage_key)
        if actual.lower() != checksum.lower() or actual.lower() != asset.checksum:
            self.repository.update(asset, {"upload_status": UploadStatus.FAILED, "processing_status": ProcessingStatus.FAILED, "updated_by": actor_id})
            raise MediaValidationError("Checksum verification failed")
        self.repository.update(asset, {"upload_status": UploadStatus.UPLOADED, "processing_status": ProcessingStatus.READY, "updated_by": actor_id})
        self._audit(actor_id, "cms.media.upload_confirmed", asset_id)
        return self.response(asset)

    def get(self, asset_id: UUID, include_deleted: bool = False) -> AssetResponse:
        asset = self._asset(asset_id)
        if asset.deleted_at and not include_deleted:
            raise MediaNotFound(str(asset_id))
        return self.response(asset)

    def list(self, **filters: Any) -> AssetListResponse:
        items, total = self.repository.list(**filters)
        return AssetListResponse(items=[self.response(x) for x in items], total=total, limit=filters["limit"], offset=filters["offset"])

    def update(self, asset_id: UUID, payload: AssetUpdate, actor_id: int) -> AssetResponse:
        asset = self._asset(asset_id)
        values = payload.model_dump(exclude_unset=True)
        if "metadata" in values:
            values["metadata_json"] = values.pop("metadata")
        values["updated_by"] = actor_id
        self.repository.update(asset, values)
        self._audit(actor_id, "cms.media.updated", asset_id)
        return self.response(asset)

    def attach(self, asset_id: UUID, content_id: UUID, actor_id: int, detach: bool = False) -> None:
        asset, content = self._asset(asset_id), self.repository.content(content_id)
        if content is None:
            raise MediaValidationError("Content does not exist")
        (self.repository.detach if detach else self.repository.attach)(asset, content)
        self._audit(actor_id, "cms.media.detached" if detach else "cms.media.attached", asset_id, {"content_id": str(content_id)})

    def delete(self, asset_id: UUID, actor_id: int, restore: bool = False) -> None:
        asset = self._asset(asset_id)
        self.repository.mark_deleted(asset, None if restore else datetime.now(UTC))
        self._audit(actor_id, "cms.media.restored" if restore else "cms.media.deleted", asset_id)

    def bulk(self, ids: builtins.list[UUID], action: str, actor_id: int) -> int:
        affected = 0
        for asset_id in dict.fromkeys(ids):
            self.delete(asset_id, actor_id, restore=action == "restore")
            affected += 1
        return affected

    def response(self, asset: CMSMediaFile) -> AssetResponse:
        url = None
        if asset.upload_status == UploadStatus.UPLOADED:
            url = self.storage.download_url(asset.storage_key, public=asset.url_strategy == URLStrategy.PUBLIC, expires_in=self.url_ttl)
        return AssetResponse(id=asset.id, asset_type=asset.asset_type, original_filename=asset.original_filename, storage_filename=asset.storage_filename, mime_type=asset.mime_type, file_size=asset.file_size, width=asset.width, height=asset.height, duration_seconds=float(asset.duration_seconds) if asset.duration_seconds is not None else None, language_code=asset.language_code, storage_provider=asset.storage_provider, storage_key=asset.storage_key, url_strategy=asset.url_strategy, download_url=url, checksum=asset.checksum, upload_status=asset.upload_status, processing_status=asset.processing_status, owner_id=asset.owner_id, copyright_holder=asset.copyright_holder, copyright_notice=asset.copyright_notice, license_starts_at=asset.license_starts_at, license_ends_at=asset.license_ends_at, created_by=asset.created_by, updated_by=asset.updated_by, created_at=asset.created_at, updated_at=asset.updated_at, deleted_at=asset.deleted_at, metadata=asset.metadata_json)

    def _asset(self, asset_id: UUID) -> CMSMediaFile:
        asset = self.repository.get(asset_id)
        if asset is None:
            raise MediaNotFound(str(asset_id))
        return asset

    def _validate(self, payload: UploadRequest) -> None:
        mime = payload.mime_type.lower()
        if payload.file_size > self.max_file_size or mime not in ALLOWED[payload.asset_type]:
            raise MediaValidationError("File type or size is not allowed")
        if Path(payload.filename).suffix.lower() not in MIME_EXTENSIONS.get(mime, set()):
            raise MediaValidationError("Filename extension does not match MIME type")

    def _audit(self, actor_id: int, event: str, asset_id: UUID, extra: dict[str, Any] | None = None) -> None:
        if self.audit:
            self.audit.create(actor_id, event, {"asset_id": str(asset_id), **(extra or {})})


__all__ = ["MediaError", "MediaNotFound", "MediaService", "MediaValidationError"]
