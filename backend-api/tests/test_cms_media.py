from collections.abc import Generator
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.audit import AuditLog
from app.models.user import Role, User
from app.modules.cms.media.api import get_storage_provider
from app.modules.cms.media.models import AssetType, CMSMediaFile, ProcessingStatus, UploadStatus
from app.modules.cms.media.permissions import require_media_scope
from app.modules.cms.media.repositories import MediaRepository
from app.modules.cms.media.schemas import UploadRequest
from app.modules.cms.media.services import MediaService, MediaValidationError
from app.modules.cms.media.services.storage import LocalStorageProvider, StorageError


@pytest.fixture()
def media_context(tmp_path: Path) -> Generator[tuple[TestClient, Session, LocalStorageProvider], None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    user = User(email="media@gntv.local", hashed_password="hash", is_active=True, is_verified=True)
    user.roles = [Role(name="admin")]
    db.add(user)
    db.commit()
    db.refresh(user)
    storage = LocalStorageProvider(str(tmp_path / "media"), "/media", "test-secret")

    def override_db() -> Generator[Session, None, None]:
        yield db
        db.commit()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_storage_provider] = lambda: storage
    try:
        yield TestClient(app), db, storage
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_local_upload_flow_and_audit(media_context: tuple[TestClient, Session, LocalStorageProvider]) -> None:
    client, db, _ = media_context
    data = b"valid image bytes"
    checksum = sha256(data).hexdigest()
    requested = client.post("/api/v1/cms/media/uploads", json={"asset_type": "image", "filename": "News Hero.JPG", "mime_type": "image/jpeg", "file_size": len(data), "checksum": checksum})
    assert requested.status_code == 201
    asset_id = requested.json()["asset_id"]
    uploaded = client.put(f"/api/v1/cms/media/{asset_id}/upload", files={"file": ("News Hero.JPG", data, "image/jpeg")})
    assert uploaded.status_code == 200
    assert uploaded.json()["upload_status"] == "uploaded"
    assert uploaded.json()["processing_status"] == "ready"
    events = db.execute(select(AuditLog.event_type).where(AuditLog.event_type.like("cms.media.%")).order_by(AuditLog.id)).scalars().all()
    assert events == ["cms.media.upload_requested", "cms.media.upload_confirmed"]


def test_list_update_delete_restore_and_bulk(media_context: tuple[TestClient, Session, LocalStorageProvider]) -> None:
    client, _, storage = media_context
    service = MediaService(MediaRepository(next(iter(app.dependency_overrides[get_db]()))), storage, None, 1000, 60)
    payload = UploadRequest(asset_type=AssetType.ATTACHMENT, filename="notes.txt", mime_type="text/plain", file_size=3, checksum=sha256(b"abc").hexdigest())
    target = service.request_upload(payload, 1)
    storage.put(f"media/{target.asset_id}", b"unused")
    assert client.get("/api/v1/cms/media?search=notes").json()["total"] == 1
    assert client.patch(f"/api/v1/cms/media/{target.asset_id}", json={"copyright_holder": "GNTV"}).json()["copyright_holder"] == "GNTV"
    assert client.delete(f"/api/v1/cms/media/{target.asset_id}").status_code == 204
    assert client.get(f"/api/v1/cms/media/{target.asset_id}").status_code == 404
    assert client.post(f"/api/v1/cms/media/{target.asset_id}/restore").status_code == 204
    assert client.post("/api/v1/cms/media/bulk/actions", json={"asset_ids": [str(target.asset_id)], "action": "delete"}).json()["affected"] == 1


def test_validation_rejects_mime_extension_and_size(media_context: tuple[TestClient, Session, LocalStorageProvider]) -> None:
    client, _, _ = media_context
    checksum = "a" * 64
    mismatch = client.post("/api/v1/cms/media/uploads", json={"asset_type": "image", "filename": "attack.exe", "mime_type": "image/jpeg", "file_size": 1, "checksum": checksum})
    assert mismatch.status_code == 400
    service = MediaService(MediaRepository(media_context[1]), media_context[2], None, 1, 60)
    with pytest.raises(MediaValidationError):
        service.request_upload(UploadRequest(asset_type=AssetType.VIDEO, filename="x.mp4", mime_type="video/mp4", file_size=2, checksum=checksum), 1)


def test_checksum_failure_marks_asset_failed(media_context: tuple[TestClient, Session, LocalStorageProvider]) -> None:
    client, db, storage = media_context
    requested = client.post("/api/v1/cms/media/uploads", json={"asset_type": "attachment", "filename": "a.txt", "mime_type": "text/plain", "file_size": 3, "checksum": sha256(b"abc").hexdigest()}).json()
    asset = db.get(CMSMediaFile, UUID(requested["asset_id"]))
    assert asset is not None
    storage.put(asset.storage_key, b"xyz")
    assert client.post(f"/api/v1/cms/media/{asset.id}/confirm", json={"checksum": sha256(b"abc").hexdigest()}).status_code == 400
    assert asset.upload_status == UploadStatus.FAILED
    assert asset.processing_status == ProcessingStatus.FAILED


def test_storage_signing_and_path_safety(tmp_path: Path) -> None:
    storage = LocalStorageProvider(str(tmp_path), "/media", "secret")
    storage.put("safe/file.txt", b"abc")
    assert storage.exists("safe/file.txt")
    assert storage.checksum("safe/file.txt") == sha256(b"abc").hexdigest()
    assert "signature=" in storage.download_url("safe/file.txt", public=False, expires_in=60)
    with pytest.raises(StorageError):
        storage.put("../escape.txt", b"no")


def test_media_rbac_and_openapi(media_context: tuple[TestClient, Session, LocalStorageProvider]) -> None:
    viewer = User(email="viewer@gntv.local", hashed_password="hash", is_verified=True)
    viewer.roles = [Role(name="viewer")]
    with pytest.raises(Exception) as exc:
        require_media_scope("asset:write")(current_user=viewer)
    assert getattr(exc.value, "status_code", None) == 403
    schema = media_context[0].get("/openapi.json").json()
    assert "/api/v1/cms/media/uploads" in schema["paths"]
    assert "/api/v1/cms/media/{asset_id}/confirm" in schema["paths"]
