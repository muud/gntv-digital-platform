"""Repository implementation for CMS Content Core."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.modules.cms.models import (
    CMSCategory,
    CMSContent,
    CMSGenre,
    CMSLanguage,
    CMSMediaFile,
    CMSRegion,
    CMSTag,
    ContentStatus,
    ContentType,
    ContentVisibility,
)


class CMSContentRepository:
    """SQLAlchemy-backed repository for Content Core."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_language(self, *, code: str, name: str, native_name: str | None = None, is_active: bool = True) -> CMSLanguage:
        language = CMSLanguage(code=code, name=name, native_name=native_name, is_active=is_active)
        self.db.add(language)
        self.db.flush()
        return language

    def get_language(self, language_id: UUID) -> CMSLanguage | None:
        return self.db.get(CMSLanguage, language_id)

    def list_languages(self) -> Sequence[CMSLanguage]:
        return self.db.execute(select(CMSLanguage).order_by(CMSLanguage.code.asc())).scalars().all()

    def create_category(
        self,
        *,
        name: str,
        slug: str,
        description: str | None = None,
        parent_id: UUID | None = None,
    ) -> CMSCategory:
        category = CMSCategory(name=name, slug=slug, description=description, parent_id=parent_id)
        self.db.add(category)
        self.db.flush()
        return category

    def list_categories(self) -> Sequence[CMSCategory]:
        return self.db.execute(select(CMSCategory).order_by(CMSCategory.name.asc())).scalars().all()

    def get_category(self, category_id: UUID) -> CMSCategory | None:
        return self.db.get(CMSCategory, category_id)

    def create_tag(self, *, name: str, slug: str) -> CMSTag:
        tag = CMSTag(name=name, slug=slug)
        self.db.add(tag)
        self.db.flush()
        return tag

    def list_tags(self) -> Sequence[CMSTag]:
        return self.db.execute(select(CMSTag).order_by(CMSTag.name.asc())).scalars().all()

    def create_genre(self, *, name: str, slug: str) -> CMSGenre:
        genre = CMSGenre(name=name, slug=slug)
        self.db.add(genre)
        self.db.flush()
        return genre

    def list_genres(self) -> Sequence[CMSGenre]:
        return self.db.execute(select(CMSGenre).order_by(CMSGenre.name.asc())).scalars().all()

    def create_region(self, *, code: str, name: str) -> CMSRegion:
        region = CMSRegion(code=code, name=name)
        self.db.add(region)
        self.db.flush()
        return region

    def list_regions(self) -> Sequence[CMSRegion]:
        return self.db.execute(select(CMSRegion).order_by(CMSRegion.name.asc())).scalars().all()

    def get_content(self, content_id: UUID) -> CMSContent | None:
        return self.db.get(CMSContent, content_id)

    def get_content_by_slug(self, slug: str) -> CMSContent | None:
        return self.db.execute(select(CMSContent).where(CMSContent.slug == slug)).scalar_one_or_none()

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
        statement = self._content_filters(
            select(CMSContent),
            status=status,
            visibility=visibility,
            content_type=content_type,
            language_id=language_id,
            category_id=category_id,
        )
        count_statement = self._content_filters(
            select(func.count()).select_from(CMSContent),
            status=status,
            visibility=visibility,
            content_type=content_type,
            language_id=language_id,
            category_id=category_id,
        )
        items = (
            self.db.execute(
                statement.options(
                    selectinload(CMSContent.tags),
                    selectinload(CMSContent.genres),
                    selectinload(CMSContent.regions),
                    selectinload(CMSContent.media_assets),
                )
                .order_by(CMSContent.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )
        total = self.db.execute(count_statement).scalar_one()
        return items, int(total)

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
        self._sync_relations(
            content,
            tag_ids=tag_ids,
            genre_ids=genre_ids,
            region_ids=region_ids,
            media_asset_ids=media_asset_ids,
        )
        self.db.add(content)
        self.db.flush()
        return content

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
        for key, value in values.items():
            setattr(content, key, value)
        self._sync_relations(
            content,
            tag_ids=tag_ids,
            genre_ids=genre_ids,
            region_ids=region_ids,
            media_asset_ids=media_asset_ids,
        )
        self.db.add(content)
        self.db.flush()
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
        if editor_id is not None:
            content.editor_id = editor_id
        content.published_at = published_at
        content.archived_at = archived_at
        self.db.add(content)
        self.db.flush()
        return content

    def get_media_file(self, media_file_id: UUID) -> CMSMediaFile | None:
        return self.db.get(CMSMediaFile, media_file_id)

    def _sync_relations(
        self,
        content: CMSContent,
        *,
        tag_ids: Sequence[UUID] | None = None,
        genre_ids: Sequence[UUID] | None = None,
        region_ids: Sequence[UUID] | None = None,
        media_asset_ids: Sequence[UUID] | None = None,
    ) -> None:
        if tag_ids is not None:
            content.tags = list(self.db.execute(select(CMSTag).where(CMSTag.id.in_(tag_ids))).scalars().all())
        if genre_ids is not None:
            content.genres = list(self.db.execute(select(CMSGenre).where(CMSGenre.id.in_(genre_ids))).scalars().all())
        if region_ids is not None:
            content.regions = list(self.db.execute(select(CMSRegion).where(CMSRegion.id.in_(region_ids))).scalars().all())
        if media_asset_ids is not None:
            content.media_assets = list(
                self.db.execute(select(CMSMediaFile).where(CMSMediaFile.id.in_(media_asset_ids))).scalars().all()
            )

    def _content_filters(
        self,
        statement: Select[tuple[Any, ...]],
        *,
        status: ContentStatus | None,
        visibility: ContentVisibility | None,
        content_type: ContentType | None,
        language_id: UUID | None,
        category_id: UUID | None,
    ) -> Select[tuple[Any, ...]]:
        if status is not None:
            statement = statement.where(CMSContent.status == status)
        if visibility is not None:
            statement = statement.where(CMSContent.visibility == visibility)
        if content_type is not None:
            statement = statement.where(CMSContent.content_type == content_type)
        if language_id is not None:
            statement = statement.where(CMSContent.language_id == language_id)
        if category_id is not None:
            statement = statement.where(CMSContent.category_id == category_id)
        return statement
