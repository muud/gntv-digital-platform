"""Frontend-facing local E2E contract validation for CMS Module 2."""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.audit import AuditLog
from app.models.user import Role
from app.modules.cms.media.api import get_storage_provider
from app.modules.cms.media.services.storage import LocalStorageProvider
from app.modules.cms.models import CMSContent, CMSLanguage, ContentType, ContentVisibility
from app.repositories.user_repository import UserRepository
from app.utils.jwt import create_access_token
from app.utils.security import hash_password


@pytest.fixture()
def e2e_context(tmp_path: Path) -> Generator[tuple[TestClient, Session], None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = UserRepository(db).create_user(
        email="cms-e2e@gntv.example",
        hashed_password=hash_password("StrongPass123"),
        is_active=True,
        is_verified=True,
    )
    user.roles = [Role(name="admin")]
    UserRepository(db).create_user(
        email="cms-viewer@gntv.example",
        hashed_password=hash_password("StrongPass123"),
        is_active=True,
        is_verified=True,
    )
    language = CMSLanguage(code="en", name="English")
    db.add_all([user, language])
    db.flush()
    content = CMSContent(
        title="E2E Story",
        slug="cms-module2-e2e-story",
        body="Local validation content",
        content_type=ContentType.ARTICLE,
        language_id=language.id,
        visibility=ContentVisibility.PRIVATE,
        author_id=user.id,
        seo={},
    )
    db.add(content)
    db.commit()
    storage = LocalStorageProvider(str(tmp_path / "media"), "/media", "e2e-signing-secret")

    def override_db() -> Generator[Session, None, None]:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_storage_provider] = lambda: storage
    try:
        yield TestClient(app), db
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_frontend_local_media_lifecycle(e2e_context: tuple[TestClient, Session]) -> None:
    client, db = e2e_context
    assert client.get("/api/v1/cms/media").status_code == 401
    user = UserRepository(db).get_by_email("cms-e2e@gntv.example")
    assert user is not None
    expired = create_access_token(str(user.id), {"exp": datetime.now(UTC) - timedelta(minutes=1)})
    assert client.get("/api/v1/cms/media", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    cors = client.options(
        "/api/v1/cms/media",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert cors.status_code == 200
    assert cors.headers["access-control-allow-origin"] == "http://localhost:5173"
    login = client.post(
        "/api/v1/auth/login",
        json={
            "req": {
                "email": "cms-e2e@gntv.example",
                "password": "StrongPass123",
                "device_name": "CMS E2E Browser",
                "platform": "web",
                "browser": "Chromium",
            },
            "location": {"country": "KE", "city": "Nairobi"},
        },
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    data = b"GNTV module 2 local E2E image"
    checksum = sha256(data).hexdigest()
    request = client.post(
        "/api/v1/cms/media/uploads",
        headers=headers,
        json={
            "asset_type": "hero",
            "filename": "Homepage Hero.JPG",
            "mime_type": "image/jpeg",
            "file_size": len(data),
            "checksum": checksum,
            "url_strategy": "signed",
            "metadata": {"source": "cms-module2-e2e"},
        },
    )
    assert request.status_code == 201
    assert set(request.json()) == {"asset_id", "method", "upload_url", "headers", "expires_at"}
    asset_id = request.json()["asset_id"]
    assert request.json()["method"] == "PUT"

    direct = client.put(
        f"/api/v1/cms/media/{asset_id}/upload",
        headers=headers,
        files={"file": ("Homepage Hero.JPG", data, "image/jpeg")},
    )
    assert direct.status_code == 200
    assert direct.json()["processing_status"] == "ready"

    confirmation = client.post(
        f"/api/v1/cms/media/{asset_id}/confirm",
        headers=headers,
        json={"checksum": checksum},
    )
    assert confirmation.status_code == 200
    assert {"id", "asset_type", "original_filename", "mime_type", "upload_status", "processing_status", "download_url", "metadata"} <= set(confirmation.json())
    signed_url = confirmation.json()["download_url"]
    assert signed_url is not None
    download = client.get(signed_url)
    assert download.status_code == 200
    assert download.content == data

    listing = client.get("/api/v1/cms/media", headers=headers)
    search = client.get("/api/v1/cms/media", headers=headers, params={"search": "Homepage", "asset_type": "hero", "upload_status": "uploaded", "processing_status": "ready", "limit": 10, "offset": 0})
    assert listing.status_code == 200 and listing.json()["total"] == 1
    assert search.status_code == 200 and search.json()["items"][0]["id"] == asset_id
    page_two = client.get("/api/v1/cms/media", headers=headers, params={"limit": 1, "offset": 1})
    assert page_two.status_code == 200 and page_two.json()["items"] == []

    update = client.patch(
        f"/api/v1/cms/media/{asset_id}",
        headers=headers,
        json={"copyright_holder": "GNTV", "language_code": "en", "metadata": {"alt": "GNTV homepage hero"}},
    )
    assert update.status_code == 200
    assert update.json()["metadata"]["alt"] == "GNTV homepage hero"

    content = db.query(CMSContent).filter_by(slug="cms-module2-e2e-story").one()
    assert client.post(f"/api/v1/cms/media/{asset_id}/attachments", headers=headers, json={"content_id": str(content.id)}).status_code == 204
    db.refresh(content)
    assert str(content.media_assets[0].id) == asset_id
    assert client.delete(f"/api/v1/cms/media/{asset_id}/attachments/{content.id}", headers=headers).status_code == 204
    db.refresh(content)
    assert content.media_assets == []

    assert client.delete(f"/api/v1/cms/media/{asset_id}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/cms/media/{asset_id}", headers=headers).status_code == 404
    assert client.post(f"/api/v1/cms/media/{asset_id}/restore", headers=headers).status_code == 204
    assert client.get(f"/api/v1/cms/media/{asset_id}", headers=headers).status_code == 200

    bulk_delete = client.post("/api/v1/cms/media/bulk/actions", headers=headers, json={"asset_ids": [asset_id], "action": "delete"})
    bulk_restore = client.post("/api/v1/cms/media/bulk/actions", headers=headers, json={"asset_ids": [asset_id], "action": "restore"})
    assert bulk_delete.status_code == 200 and bulk_delete.json()["affected"] == 1
    assert bulk_restore.status_code == 200 and bulk_restore.json()["affected"] == 1

    tampered = client.get(f"{signed_url}x")
    assert tampered.status_code == 403

    viewer_login = client.post(
        "/api/v1/auth/login",
        json={
            "req": {
                "email": "cms-viewer@gntv.example",
                "password": "StrongPass123",
                "device_name": "Read-only Browser",
            },
            "location": None,
        },
    )
    viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}
    assert client.get("/api/v1/cms/media", headers=viewer_headers).status_code == 403
    assert client.post("/api/v1/cms/media/uploads", headers=viewer_headers, json={}).status_code == 403

    events = {event for (event,) in db.query(AuditLog.event_type).filter(AuditLog.event_type.like("cms.media.%")).all()}
    assert {
        "cms.media.upload_requested",
        "cms.media.upload_confirmed",
        "cms.media.updated",
        "cms.media.attached",
        "cms.media.detached",
        "cms.media.deleted",
        "cms.media.restored",
    } <= events
