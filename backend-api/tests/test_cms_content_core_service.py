from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from app.modules.cms.models import (
    CMSCategory,
    CMSContent,
    CMSLanguage,
    CMSMediaFile,
    ContentStatus,
    ContentType,
    ContentVisibility,
)
from app.repositories.audit_repository import AuditRepository
from app.modules.cms.repositories import CMSContentRepository
from app.modules.cms.schemas import CMSContentCreate, CMSContentTransitionRequest, CMSContentUpdate
from app.modules.cms.services import CMSContentCoreService, CMSInvalidTransitionError, CMSValidationError


class FakeContentRepository:
    def __init__(self) -> None:
        self.languages: dict[UUID, CMSLanguage] = {}
        self.categories: dict[UUID, CMSCategory] = {}
        self.contents: dict[UUID, CMSContent] = {}
        self.media_files: dict[UUID, CMSMediaFile] = {}

    def create_language(self, *, code: str, name: str, native_name: str | None = None, is_active: bool = True) -> CMSLanguage:
        language = CMSLanguage(code=code, name=name, native_name=native_name, is_active=is_active)
        language.id = uuid4()
        language.created_at = datetime.now(UTC)
        language.updated_at = language.created_at
        self.languages[language.id] = language
        return language

    def get_language(self, language_id: UUID) -> CMSLanguage | None:
        return self.languages.get(language_id)

    def list_languages(self) -> Sequence[CMSLanguage]:
        return list(self.languages.values())

    def create_category(
        self,
        *,
        name: str,
        slug: str,
        description: str | None = None,
        parent_id: UUID | None = None,
    ) -> CMSCategory:
        category = CMSCategory(name=name, slug=slug, description=description, parent_id=parent_id)
        category.id = uuid4()
        category.created_at = datetime.now(UTC)
        category.updated_at = category.created_at
        self.categories[category.id] = category
        return category

    def get_category(self, category_id: UUID) -> CMSCategory | None:
        return self.categories.get(category_id)

    def list_categories(self) -> Sequence[CMSCategory]:
        return list(self.categories.values())

    def get_content_by_slug(self, slug: str) -> CMSContent | None:
        return next((content for content in self.contents.values() if content.slug == slug), None)

    def get_media_file(self, media_file_id: UUID) -> CMSMediaFile | None:
        return self.media_files.get(media_file_id)

    def create_content(
        self,
        *,
        title: str,
        slug: str,
        body: str,
        content_type: ContentType,
        language_id: UUID,
        author_id: int,
        summary: str | None = None,
        visibility: ContentVisibility = ContentVisibility.PRIVATE,
        category_id: UUID | None = None,
        featured_image_asset_id: UUID | None = None,
        seo: dict[str, Any] | None = None,
        tag_ids: Sequence[UUID] = (),
        genre_ids: Sequence[UUID] = (),
        region_ids: Sequence[UUID] = (),
        media_asset_ids: Sequence[UUID] = (),
    ) -> CMSContent:
        del tag_ids, genre_ids, region_ids, media_asset_ids
        content = CMSContent(
            title=title,
            slug=slug,
            summary=summary,
            body=body,
            content_type=content_type,
            language_id=language_id,
            visibility=visibility,
            author_id=author_id,
            category_id=category_id,
            featured_image_asset_id=featured_image_asset_id,
            seo=seo or {},
        )
        content.id = uuid4()
        content.status = ContentStatus.DRAFT
        content.tags = []
        content.genres = []
        content.regions = []
        content.media_assets = []
        content.created_at = datetime.now(UTC)
        content.updated_at = content.created_at
        content.published_at = None
        content.archived_at = None
        content.editor_id = None
        self.contents[content.id] = content
        return content

    def get_content(self, content_id: UUID) -> CMSContent | None:
        return self.contents.get(content_id)

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
    ) -> tuple[Sequence[CMSContent], int]:
        del status, visibility, content_type, language_id, category_id
        items = list(self.contents.values())[offset : offset + limit]
        return items, len(self.contents)

    def update_content(
        self,
        content: CMSContent,
        *,
        values: dict[str, Any],
        tag_ids: Sequence[UUID] | None = None,
        genre_ids: Sequence[UUID] | None = None,
        region_ids: Sequence[UUID] | None = None,
        media_asset_ids: Sequence[UUID] | None = None,
    ) -> CMSContent:
        del tag_ids, genre_ids, region_ids, media_asset_ids
        for key, value in values.items():
            setattr(content, key, value)
        return content

    def update_status(
        self,
        content: CMSContent,
        *,
        status: ContentStatus,
        editor_id: int | None = None,
        published_at: datetime | None = None,
        archived_at: datetime | None = None,
    ) -> CMSContent:
        content.status = status
        content.editor_id = editor_id
        content.published_at = published_at
        content.archived_at = archived_at
        return content


class FakeAuditRepository:
    def __init__(self) -> None:
        self.events: list[tuple[int, str, dict[str, Any] | None]] = []

    def create(self, user_id: int, event_type: str, metadata: dict[str, Any] | None = None) -> object:
        self.events.append((user_id, event_type, metadata))
        return object()


def make_service() -> tuple[CMSContentCoreService, FakeContentRepository, FakeAuditRepository]:
    repository = FakeContentRepository()
    audit = FakeAuditRepository()
    return CMSContentCoreService(cast(CMSContentRepository, repository), cast(AuditRepository, audit)), repository, audit


def test_create_content_validates_language_and_audits() -> None:
    service, repository, audit = make_service()
    language = repository.create_language(code="so", name="Somali")

    response = service.create_content(
        CMSContentCreate(
            title="Somali Business Brief",
            slug="somali-business-brief",
            body="Body",
            content_type=ContentType.ARTICLE,
            language_id=language.id,
            visibility=ContentVisibility.PUBLIC,
        ),
        author_id=7,
    )

    assert response.title == "Somali Business Brief"
    assert response.status == ContentStatus.DRAFT
    assert response.author_id == 7
    assert audit.events[-1][1] == "cms.content.created"


def test_create_content_rejects_missing_language() -> None:
    service, _, _ = make_service()

    with pytest.raises(CMSValidationError):
        service.create_content(
            CMSContentCreate(title="Missing", slug="missing", body="Body", content_type=ContentType.ARTICLE, language_id=uuid4()),
            author_id=7,
        )


def test_update_content_rejects_duplicate_slug() -> None:
    service, repository, _ = make_service()
    language = repository.create_language(code="so", name="Somali")
    first = service.create_content(
        CMSContentCreate(title="First", slug="first", body="Body", content_type=ContentType.ARTICLE, language_id=language.id),
        author_id=7,
    )
    service.create_content(
        CMSContentCreate(title="Second", slug="second", body="Body", content_type=ContentType.ARTICLE, language_id=language.id),
        author_id=7,
    )

    with pytest.raises(CMSValidationError):
        service.update_content(first.id, CMSContentUpdate(slug="second"), actor_id=7)


def test_transition_content_through_publish() -> None:
    service, repository, _ = make_service()
    language = repository.create_language(code="so", name="Somali")
    content = service.create_content(
        CMSContentCreate(title="Workflow", slug="workflow", body="Body", content_type=ContentType.ARTICLE, language_id=language.id),
        author_id=7,
    )

    reviewed = service.transition_content(content.id, CMSContentTransitionRequest(transition="submit"), actor_id=8)
    fact_checked = service.transition_content(content.id, CMSContentTransitionRequest(transition="fact_check"), actor_id=8)
    approved = service.transition_content(content.id, CMSContentTransitionRequest(transition="approve"), actor_id=8)
    published = service.transition_content(content.id, CMSContentTransitionRequest(transition="publish"), actor_id=8)

    assert reviewed.status == ContentStatus.REVIEW
    assert fact_checked.status == ContentStatus.FACT_CHECK
    assert approved.status == ContentStatus.APPROVED
    assert published.status == ContentStatus.PUBLISHED
    assert published.published_at is not None


def test_transition_content_rejects_invalid_jump() -> None:
    service, repository, _ = make_service()
    language = repository.create_language(code="so", name="Somali")
    content = service.create_content(
        CMSContentCreate(title="Workflow", slug="workflow", body="Body", content_type=ContentType.ARTICLE, language_id=language.id),
        author_id=7,
    )

    with pytest.raises(CMSInvalidTransitionError):
        service.transition_content(content.id, CMSContentTransitionRequest(transition="publish"), actor_id=8)
