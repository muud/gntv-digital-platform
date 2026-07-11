from collections.abc import Generator, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies.auth import get_current_user
from app.main import app
from app.models.user import Role, User
from app.modules.cms.api import content as content_api
from app.modules.cms.models import ContentStatus, ContentType, ContentVisibility
from app.modules.cms.schemas import (
    CMSCategoryCreate,
    CMSCategoryResponse,
    CMSContentCreate,
    CMSContentListResponse,
    CMSContentResponse,
    CMSContentTransitionRequest,
    CMSContentUpdate,
    CMSLanguageCreate,
    CMSLanguageResponse,
    CMSRegionCreate,
    CMSTaxonomyCreate,
)


class FakeContentCoreService:
    def __init__(self) -> None:
        self.language_id = uuid4()
        self.content_id = uuid4()
        now = datetime.now(UTC)
        self.language = CMSLanguageResponse(
            id=self.language_id,
            code="so",
            name="Somali",
            native_name=None,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self.content = CMSContentResponse(
            id=self.content_id,
            title="Somali Business Brief",
            slug="somali-business-brief",
            summary="Summary",
            body="Body",
            content_type=ContentType.ARTICLE,
            language_id=self.language_id,
            status=ContentStatus.DRAFT,
            visibility=ContentVisibility.PUBLIC,
            author_id=7,
            editor_id=None,
            category_id=None,
            tag_ids=[],
            genre_ids=[],
            region_ids=[],
            featured_image_asset_id=None,
            media_asset_ids=[],
            seo={},
            created_at=now,
            updated_at=now,
            published_at=None,
            archived_at=None,
        )

    def create_language(self, payload: CMSLanguageCreate, *, actor_id: int) -> CMSLanguageResponse:
        assert actor_id == 7
        return self.language.model_copy(update={"code": payload.code, "name": payload.name})

    def list_languages(self) -> Sequence[CMSLanguageResponse]:
        return [self.language]

    def create_category(self, payload: CMSCategoryCreate, *, actor_id: int) -> CMSCategoryResponse:
        now = datetime.now(UTC)
        return CMSCategoryResponse(
            id=uuid4(),
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            parent_id=payload.parent_id,
            created_at=now,
            updated_at=now,
        )

    def list_categories(self) -> Sequence[CMSCategoryResponse]:
        return []

    def create_tag(self, payload: CMSTaxonomyCreate, *, actor_id: int) -> dict[str, Any]:
        del actor_id
        now = datetime.now(UTC)
        return {"id": uuid4(), "name": payload.name, "slug": payload.slug, "created_at": now, "updated_at": now}

    def list_tags(self) -> Sequence[dict[str, Any]]:
        return []

    def create_genre(self, payload: CMSTaxonomyCreate, *, actor_id: int) -> dict[str, Any]:
        del actor_id
        now = datetime.now(UTC)
        return {"id": uuid4(), "name": payload.name, "slug": payload.slug, "created_at": now, "updated_at": now}

    def list_genres(self) -> Sequence[dict[str, Any]]:
        return []

    def create_region(self, payload: CMSRegionCreate, *, actor_id: int) -> dict[str, Any]:
        del actor_id
        now = datetime.now(UTC)
        return {"id": uuid4(), "code": payload.code, "name": payload.name, "created_at": now, "updated_at": now}

    def list_regions(self) -> Sequence[dict[str, Any]]:
        return []

    def create_content(self, payload: CMSContentCreate, *, author_id: int) -> CMSContentResponse:
        assert author_id == 7
        return self.content.model_copy(update={"title": payload.title, "slug": payload.slug, "body": payload.body})

    def list_content(
        self,
        *,
        status: ContentStatus | None = None,
        visibility: ContentVisibility | None = None,
        content_type: ContentType | None = None,
        language_id: UUID | None = None,
        category_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CMSContentListResponse:
        del status, visibility, content_type, language_id, category_id
        return CMSContentListResponse(items=[self.content], total=1, limit=limit, offset=offset)

    def get_content(self, content_id: UUID) -> CMSContentResponse:
        return self.content.model_copy(update={"id": content_id})

    def update_content(self, content_id: UUID, payload: CMSContentUpdate, *, actor_id: int) -> CMSContentResponse:
        del actor_id
        return self.content.model_copy(update={"id": content_id, "title": payload.title or self.content.title})

    def transition_content(
        self,
        content_id: UUID,
        payload: CMSContentTransitionRequest,
        *,
        actor_id: int,
    ) -> CMSContentResponse:
        del actor_id
        return self.content.model_copy(update={"id": content_id, "status": ContentStatus.REVIEW if payload.transition == "submit" else ContentStatus.DRAFT})


@pytest.fixture()
def cms_client() -> Generator[TestClient, None, None]:
    service = FakeContentCoreService()
    user = User(email="editor@gntv.local", hashed_password="hash", is_active=True, is_verified=True)
    user.id = 7
    user.roles = [Role(name="admin")]

    def override_service() -> FakeContentCoreService:
        return service

    def override_user() -> User:
        return user

    app.dependency_overrides[content_api.get_content_core_service] = override_service
    app.dependency_overrides[get_current_user] = override_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_content_core_openapi_paths_exist(cms_client: TestClient) -> None:
    schema = cms_client.get("/openapi.json").json()

    assert "/api/v1/cms/content" in schema["paths"]
    assert "/api/v1/cms/languages" in schema["paths"]
    assert "/api/v1/cms/categories" in schema["paths"]
    assert "/api/v1/cms/tags" in schema["paths"]
    assert "/api/v1/cms/genres" in schema["paths"]
    assert "/api/v1/cms/regions" in schema["paths"]


def test_create_and_list_content(cms_client: TestClient) -> None:
    language_id = str(uuid4())
    create_response = cms_client.post(
        "/api/v1/cms/content",
        json={
            "title": "Somali Business Brief",
            "slug": "somali-business-brief",
            "body": "Body",
            "content_type": "article",
            "language_id": language_id,
            "visibility": "public",
        },
    )
    list_response = cms_client.get("/api/v1/cms/content")

    assert create_response.status_code == 201
    assert create_response.json()["slug"] == "somali-business-brief"
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1


def test_create_taxonomy_endpoints(cms_client: TestClient) -> None:
    assert cms_client.post("/api/v1/cms/languages", json={"code": "SO", "name": "Somali"}).status_code == 201
    assert cms_client.post("/api/v1/cms/categories", json={"name": "News", "slug": "news"}).status_code == 201
    assert cms_client.post("/api/v1/cms/tags", json={"name": "Politics", "slug": "politics"}).status_code == 201
    assert cms_client.post("/api/v1/cms/genres", json={"name": "Documentary", "slug": "documentary"}).status_code == 201
    assert cms_client.post("/api/v1/cms/regions", json={"code": "KE", "name": "Kenya"}).status_code == 201


def test_transition_content(cms_client: TestClient) -> None:
    response = cms_client.post(f"/api/v1/cms/content/{uuid4()}/workflow", json={"transition": "submit"})

    assert response.status_code == 200
    assert response.json()["status"] == "review"


def test_real_cms_scope_rejects_viewer_role() -> None:
    dependency = content_api.require_cms_scope("content:write")
    viewer = User(email="viewer@gntv.local", hashed_password="hash", is_active=True, is_verified=True)
    viewer.roles = [Role(name="viewer")]

    with pytest.raises(Exception) as exc_info:
        dependency(current_user=viewer)

    assert getattr(exc_info.value, "status_code", None) == 403
