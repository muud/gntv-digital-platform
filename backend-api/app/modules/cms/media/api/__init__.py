"""Versioned REST API for the CMS Media Library."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.modules.cms.media.models import AssetType, ProcessingStatus, UploadStatus
from app.modules.cms.media.permissions import require_media_scope
from app.modules.cms.media.repositories import MediaRepository
from app.modules.cms.media.schemas import AssetListResponse, AssetResponse, AssetUpdate, BulkActionRequest, BulkActionResponse, ConfirmUploadRequest, ContentAttachmentRequest, UploadRequest, UploadTarget
from app.modules.cms.media.services import MediaError, MediaNotFound, MediaService
from app.modules.cms.media.services.storage import LocalStorageProvider, OSSStorageProvider, StorageProvider
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/api/v1/cms/media", tags=["CMS Media Library"])
download_router = APIRouter(tags=["CMS Media Library"])


def get_storage_provider() -> StorageProvider:
    if settings.MEDIA_STORAGE_PROVIDER.lower() == "oss":
        return OSSStorageProvider(settings.OSS_ENDPOINT, settings.OSS_BUCKET_NAME, settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
    return LocalStorageProvider(settings.MEDIA_LOCAL_ROOT, settings.MEDIA_PUBLIC_BASE_URL, settings.MEDIA_SIGNING_SECRET)


def get_media_service(db: Session = Depends(get_db), storage: StorageProvider = Depends(get_storage_provider)) -> MediaService:
    return MediaService(MediaRepository(db), storage, AuditRepository(db), settings.MEDIA_MAX_FILE_SIZE, settings.MEDIA_URL_TTL_SECONDS)


def media_error(exc: MediaError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND if isinstance(exc, MediaNotFound) else status.HTTP_400_BAD_REQUEST, detail={"code": exc.code})


@download_router.get("/media/download/{key:path}", include_in_schema=False)
def local_signed_download(key: str, expires: int, signature: str, storage: StorageProvider = Depends(get_storage_provider)) -> FileResponse:
    if not isinstance(storage, LocalStorageProvider) or not storage.validate_signature(key, "download", expires, signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "media_signature_invalid"})
    try:
        return FileResponse(storage.path_for_download(key))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "media_object_not_found"}) from exc


@router.post("/uploads", response_model=UploadTarget, status_code=status.HTTP_201_CREATED)
def request_upload(payload: UploadRequest, user: User = Depends(require_media_scope("asset:write")), service: MediaService = Depends(get_media_service)) -> UploadTarget:
    try:
        return service.request_upload(payload, user.id)
    except MediaError as exc:
        raise media_error(exc) from exc


@router.put("/{asset_id}/upload", response_model=AssetResponse)
async def local_upload(asset_id: UUID, file: UploadFile = File(...), user: User = Depends(require_media_scope("asset:write")), service: MediaService = Depends(get_media_service)) -> AssetResponse:
    try:
        return service.direct_upload(asset_id, await file.read(), user.id)
    except MediaError as exc:
        raise media_error(exc) from exc


@router.post("/{asset_id}/confirm", response_model=AssetResponse)
def confirm_upload(asset_id: UUID, payload: ConfirmUploadRequest, user: User = Depends(require_media_scope("asset:write")), service: MediaService = Depends(get_media_service)) -> AssetResponse:
    try:
        return service.confirm(asset_id, payload.checksum, user.id)
    except MediaError as exc:
        raise media_error(exc) from exc


@router.get("", response_model=AssetListResponse)
def list_assets(search: str | None = None, asset_type: AssetType | None = None, upload_status: UploadStatus | None = None, processing_status: ProcessingStatus | None = None, include_deleted: bool = False, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(require_media_scope("asset:read-draft")), service: MediaService = Depends(get_media_service)) -> AssetListResponse:
    del user
    return service.list(search=search, asset_type=asset_type, upload_status=upload_status, processing_status=processing_status, include_deleted=include_deleted, limit=limit, offset=offset)


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(asset_id: UUID, include_deleted: bool = False, user: User = Depends(require_media_scope("asset:read-draft")), service: MediaService = Depends(get_media_service)) -> AssetResponse:
    del user
    try:
        return service.get(asset_id, include_deleted)
    except MediaError as exc:
        raise media_error(exc) from exc


@router.patch("/{asset_id}", response_model=AssetResponse)
def update_asset(asset_id: UUID, payload: AssetUpdate, user: User = Depends(require_media_scope("asset:write")), service: MediaService = Depends(get_media_service)) -> AssetResponse:
    try:
        return service.update(asset_id, payload, user.id)
    except MediaError as exc:
        raise media_error(exc) from exc


@router.post("/{asset_id}/attachments", status_code=status.HTTP_204_NO_CONTENT)
def attach(asset_id: UUID, payload: ContentAttachmentRequest, user: User = Depends(require_media_scope("asset:write")), service: MediaService = Depends(get_media_service)) -> Response:
    try:
        service.attach(asset_id, payload.content_id, user.id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except MediaError as exc:
        raise media_error(exc) from exc


@router.delete("/{asset_id}/attachments/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach(asset_id: UUID, content_id: UUID, user: User = Depends(require_media_scope("asset:write")), service: MediaService = Depends(get_media_service)) -> Response:
    try:
        service.attach(asset_id, content_id, user.id, detach=True)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except MediaError as exc:
        raise media_error(exc) from exc


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(asset_id: UUID, user: User = Depends(require_media_scope("asset:write")), service: MediaService = Depends(get_media_service)) -> Response:
    try:
        service.delete(asset_id, user.id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except MediaError as exc:
        raise media_error(exc) from exc


@router.post("/{asset_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore(asset_id: UUID, user: User = Depends(require_media_scope("asset:write")), service: MediaService = Depends(get_media_service)) -> Response:
    try:
        service.delete(asset_id, user.id, restore=True)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except MediaError as exc:
        raise media_error(exc) from exc


@router.post("/bulk/actions", response_model=BulkActionResponse)
def bulk(payload: BulkActionRequest, user: User = Depends(require_media_scope("asset:write")), service: MediaService = Depends(get_media_service)) -> BulkActionResponse:
    try:
        return BulkActionResponse(affected=service.bulk(payload.asset_ids, payload.action, user.id))
    except MediaError as exc:
        raise media_error(exc) from exc


__all__ = ["download_router", "get_media_service", "get_storage_provider", "router"]
