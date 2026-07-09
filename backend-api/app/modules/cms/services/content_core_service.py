"""Application service for CMS Content Core."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.repositories.audit_repository import AuditRepository
from app.modules.cms.models import (
    CMSCategory,
    CMSContent,
    CMSGenre,
    CMSLanguage,
    CMSRegion,
    CMSTag,
    ContentStatus,
    ContentType,
    ContentVisibility,
)
from app.modules.cms.repositories import CMSContentRepository
from app.modules.cms.schemas import (
    CMSCategoryCreate,
    CMSContentCreate,
    CMSContentListResponse,
    CMSContentResponse,
    CMSContentTransitionRequest,
    CMSContentUpdate,
    CMSLanguageCreate,
    CMSRegionCreate,
    CMSTaxonomyCreate,
)
from app.modules.cms.services.exceptions import CMSContentNotFoundError, CMSInvalidTransitionError, CMSValidationError

ContentTransition = tuple[ContentStatus, ContentStatus]

CONTENT_TRANSITIONS: dict[str, ContentTransition] = {
    "submit": (ContentStatus.DRAFT, ContentStatus.REVIEW),
    "fact_check": (ContentStatus.REVIEW, ContentStatus.FACT_CHECK),
    "approve": (ContentStatus.FACT_CHECK, ContentStatus.APPROVED),
    "schedule": (ContentStatus.APPROVED, ContentStatus.SCHEDULED),
    "publish": (ContentStatus.APPROVED, ContentStatus.PUBLISHED),
    "release": (ContentStatus.SCHEDULED, ContentStatus.PUBLISHED),
    "archive": (ContentStatus.PUBLISHED, ContentStatus.ARCHIVED),
}


class CMSContentCoreService:
    """Coordinates Content Core persistence, validation, workflow, and audit."""

    def __init__(self, repository: CMSContentRepository, audit_repository: AuditRepository | None = None) -> None:
        self.repository = repository
        self.audit_repository = audit_repository

    def create_language(self, payload: CMSLanguageCreate, *, actor_id: int) -> CMSLanguage:
        language = self.repository.create_language(
            code=payload.code,
            name=payload.name,
            native_name=payload.native_name,
            is_active=payload.is_active,
        )
        self._audit(actor_id, "cms.language.created", {"language_id": str(language.id), "code": language.code})
        return language

    def list_languages(self) -> Sequence[CMSLanguage]:
        return self.repository.list_languages()

    def create_category(self, payload: CMSCategoryCreate, *, actor_id: int) -> CMSCategory:
        if payload.parent_id is not None and self.repository.get_category(payload.parent_id) is None:
            raise CMSValidationError("Parent category does not exist")
        category = self.repository.create_category(
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            parent_id=payload.parent_id,
        )
        self._audit(actor_id, "cms.category.created", {"category_id": str(category.id), "slug": category.slug})
        return category

    def list_categories(self) -> Sequence[CMSCategory]:
        return self.repository.list_categories()

    def create_tag(self, payload: CMSTaxonomyCreate, *, actor_id: int) -> CMSTag:
        tag = self.repository.create_tag(name=payload.name, slug=payload.slug)
        self._audit(actor_id, "cms.tag.created", {"tag_id": str(tag.id), "slug": tag.slug})
        return tag

    def list_tags(self) -> Sequence[CMSTag]:
        return self.repository.list_tags()

    def create_genre(self, payload: CMSTaxonomyCreate, *, actor_id: int) -> CMSGenre:
        genre = self.repository.create_genre(name=payload.name, slug=payload.slug)
        self._audit(actor_id, "cms.genre.created", {"genre_id": str(genre.id), "slug": genre.slug})
        return genre

    def list_genres(self) -> Sequence[CMSGenre]:
        return self.repository.list_genres()

    def create_region(self, payload: CMSRegionCreate, *, actor_id: int) -> CMSRegion:
        region = self.repository.create_region(code=payload.code, name=payload.name)
        self._audit(actor_id, "cms.region.created", {"region_id": str(region.id), "code": region.code})
        return region

    def list_regions(self) -> Sequence[CMSRegion]:
        return self.repository.list_regions()

    def create_content(self, payload: CMSContentCreate, *, author_id: int) -> CMSContentResponse:
        self._validate_content_references(
            language_id=payload.language_id,
            category_id=payload.category_id,
            featured_image_asset_id=payload.featured_image_asset_id,
        )
        if self.repository.get_content_by_slug(payload.slug) is not None:
            raise CMSValidationError("Content slug already exists")

        content = self.repository.create_content(
            title=payload.title,
            slug=payload.slug,
            summary=payload.summary,
            body=payload.body,
            content_type=payload.content_type,
            language_id=payload.language_id,
            visibility=payload.visibility,
            author_id=author_id,
            category_id=payload.category_id,
            featured_image_asset_id=payload.featured_image_asset_id,
            seo=payload.seo.model_dump(),
            tag_ids=payload.tag_ids,
            genre_ids=payload.genre_ids,
            region_ids=payload.region_ids,
            media_asset_ids=payload.media_asset_ids,
        )
        self._audit(author_id, "cms.content.created", {"content_id": str(content.id), "slug": content.slug})
        return self.to_content_response(content)

    def get_content(self, content_id: UUID) -> CMSContentResponse:
        return self.to_content_response(self._require_content(content_id))

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
        items, total = self.repository.list_content(
            status=status,
            visibility=visibility,
            content_type=content_type,
            language_id=language_id,
            category_id=category_id,
            limit=limit,
            offset=offset,
        )
        return CMSContentListResponse(
            items=[self.to_content_response(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    def update_content(self, content_id: UUID, payload: CMSContentUpdate, *, actor_id: int) -> CMSContentResponse:
        content = self._require_content(content_id)
        values = payload.model_dump(exclude_unset=True, exclude={"tag_ids", "genre_ids", "region_ids", "media_asset_ids", "seo"})
        if payload.seo is not None:
            values["seo"] = payload.seo.model_dump()
        if "language_id" in values or "category_id" in values or "featured_image_asset_id" in values:
            self._validate_content_references(
                language_id=values.get("language_id", content.language_id),
                category_id=values.get("category_id", content.category_id),
                featured_image_asset_id=values.get("featured_image_asset_id", content.featured_image_asset_id),
            )
        if "slug" in values:
            existing = self.repository.get_content_by_slug(values["slug"])
            if existing is not None and existing.id != content_id:
                raise CMSValidationError("Content slug already exists")

        updated = self.repository.update_content(
            content,
            values=values,
            tag_ids=payload.tag_ids,
            genre_ids=payload.genre_ids,
            region_ids=payload.region_ids,
            media_asset_ids=payload.media_asset_ids,
        )
        self._audit(actor_id, "cms.content.updated", {"content_id": str(updated.id)})
        return self.to_content_response(updated)

    def transition_content(
        self,
        content_id: UUID,
        payload: CMSContentTransitionRequest,
        *,
        actor_id: int,
    ) -> CMSContentResponse:
        content = self._require_content(content_id)
        old_status = content.status
        new_status = self._resolve_transition(old_status, payload)
        now = datetime.now(UTC)
        published_at = content.published_at
        archived_at = content.archived_at
        if new_status == ContentStatus.PUBLISHED:
            published_at = payload.scheduled_publish_at or now
        if new_status == ContentStatus.ARCHIVED:
            archived_at = now
        updated = self.repository.update_status(
            content,
            status=new_status,
            editor_id=payload.editor_id or actor_id,
            published_at=published_at,
            archived_at=archived_at,
        )
        self._audit(
            actor_id,
            "cms.content.transitioned",
            {"content_id": str(updated.id), "old_status": old_status.value, "new_status": new_status.value},
        )
        return self.to_content_response(updated)

    def to_content_response(self, content: CMSContent) -> CMSContentResponse:
        return CMSContentResponse(
            id=content.id,
            title=content.title,
            slug=content.slug,
            summary=content.summary,
            body=content.body,
            content_type=content.content_type,
            language_id=content.language_id,
            status=content.status,
            visibility=content.visibility,
            author_id=content.author_id,
            editor_id=content.editor_id,
            category_id=content.category_id,
            tag_ids=[tag.id for tag in content.tags],
            genre_ids=[genre.id for genre in content.genres],
            region_ids=[region.id for region in content.regions],
            featured_image_asset_id=content.featured_image_asset_id,
            media_asset_ids=[media.id for media in content.media_assets],
            seo=content.seo,
            created_at=content.created_at,
            updated_at=content.updated_at,
            published_at=content.published_at,
            archived_at=content.archived_at,
        )

    def _require_content(self, content_id: UUID) -> CMSContent:
        content = self.repository.get_content(content_id)
        if content is None:
            raise CMSContentNotFoundError(content_id)
        return content

    def _validate_content_references(
        self,
        *,
        language_id: UUID,
        category_id: UUID | None,
        featured_image_asset_id: UUID | None,
    ) -> None:
        if self.repository.get_language(language_id) is None:
            raise CMSValidationError("Language does not exist")
        if category_id is not None and self.repository.get_category(category_id) is None:
            raise CMSValidationError("Category does not exist")
        if featured_image_asset_id is not None and self.repository.get_media_file(featured_image_asset_id) is None:
            raise CMSValidationError("Featured image asset does not exist")

    def _resolve_transition(self, old_status: ContentStatus, payload: CMSContentTransitionRequest) -> ContentStatus:
        transition = payload.transition
        if transition == "schedule" and payload.scheduled_publish_at is None:
            raise CMSValidationError("scheduled_publish_at is required for schedule transition")
        target = CONTENT_TRANSITIONS.get(transition)
        if target is None:
            raise CMSInvalidTransitionError(transition)
        source_status, target_status = target
        if old_status != source_status:
            raise CMSInvalidTransitionError(transition)
        return target_status

    def _audit(self, actor_id: int, event_type: str, metadata: dict[str, Any]) -> None:
        if self.audit_repository is not None:
            self.audit_repository.create(actor_id, event_type, metadata)
