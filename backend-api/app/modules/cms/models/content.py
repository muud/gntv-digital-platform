"""CMS content core ORM models."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, JSON, String, Table, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.cms.models.base import AuditBase, ContentBase, LocalizationBase, MediaAssetBase, WorkflowBase
from app.modules.cms.media.models import CMSMediaFile
from app.modules.cms.models.enums import ContentStatus, ContentType, ContentVisibility

if TYPE_CHECKING:
    from app.models.user import User


content_status_enum = Enum(
    ContentStatus,
    name="gntv_content_status",
    values_callable=lambda enum: [member.value for member in enum],
)

content_visibility_enum = Enum(
    ContentVisibility,
    name="gntv_content_visibility",
    values_callable=lambda enum: [member.value for member in enum],
)

content_type_enum = Enum(
    ContentType,
    name="gntv_content_type",
    values_callable=lambda enum: [member.value for member in enum],
)


cms_content_tags = Table(
    "cms_content_tags",
    Base.metadata,
    Column("content_id", Uuid(as_uuid=True), ForeignKey("cms_content.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Uuid(as_uuid=True), ForeignKey("cms_tags.id", ondelete="CASCADE"), primary_key=True),
)

cms_content_genres = Table(
    "cms_content_genres",
    Base.metadata,
    Column("content_id", Uuid(as_uuid=True), ForeignKey("cms_content.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", Uuid(as_uuid=True), ForeignKey("cms_genres.id", ondelete="CASCADE"), primary_key=True),
)

cms_content_regions = Table(
    "cms_content_regions",
    Base.metadata,
    Column("content_id", Uuid(as_uuid=True), ForeignKey("cms_content.id", ondelete="CASCADE"), primary_key=True),
    Column("region_id", Uuid(as_uuid=True), ForeignKey("cms_regions.id", ondelete="CASCADE"), primary_key=True),
)

cms_content_media_assets = Table(
    "cms_content_media_assets",
    Base.metadata,
    Column("content_id", Uuid(as_uuid=True), ForeignKey("cms_content.id", ondelete="CASCADE"), primary_key=True),
    Column("media_asset_id", Uuid(as_uuid=True), ForeignKey("cms_media_files.id", ondelete="CASCADE"), primary_key=True),
)


class CMSLanguage(Base, LocalizationBase):
    __tablename__ = "cms_languages"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    native_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    contents: Mapped[list["CMSContent"]] = relationship(back_populates="language")

    __table_args__ = (Index("idx_cms_languages_code", "code"),)


class CMSCategory(Base, ContentBase):
    __tablename__ = "cms_categories"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cms_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    parent: Mapped["CMSCategory | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["CMSCategory"]] = relationship(back_populates="parent")
    contents: Mapped[list["CMSContent"]] = relationship(back_populates="category")

    __table_args__ = (Index("idx_cms_categories_slug", "slug"),)


class CMSTag(Base, ContentBase):
    __tablename__ = "cms_tags"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    contents: Mapped[list["CMSContent"]] = relationship(secondary=cms_content_tags, back_populates="tags")

    __table_args__ = (Index("idx_cms_tags_slug", "slug"),)


class CMSGenre(Base, ContentBase):
    __tablename__ = "cms_genres"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    contents: Mapped[list["CMSContent"]] = relationship(secondary=cms_content_genres, back_populates="genres")

    __table_args__ = (Index("idx_cms_genres_slug", "slug"),)


class CMSRegion(Base, LocalizationBase):
    __tablename__ = "cms_regions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    contents: Mapped[list["CMSContent"]] = relationship(secondary=cms_content_regions, back_populates="regions")

    __table_args__ = (Index("idx_cms_regions_code", "code"),)


class CMSContent(Base, ContentBase, WorkflowBase, MediaAssetBase, AuditBase):
    __tablename__ = "cms_content"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[ContentType] = mapped_column(content_type_enum, nullable=False)
    language_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("cms_languages.id"), nullable=False)
    status: Mapped[ContentStatus] = mapped_column(
        content_status_enum,
        nullable=False,
        default=ContentStatus.DRAFT,
        server_default=ContentStatus.DRAFT.value,
    )
    visibility: Mapped[ContentVisibility] = mapped_column(
        content_visibility_enum,
        nullable=False,
        default=ContentVisibility.PRIVATE,
        server_default=ContentVisibility.PRIVATE.value,
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    editor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    category_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cms_categories.id"), nullable=True)
    featured_image_asset_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cms_media_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    seo: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    language: Mapped[CMSLanguage] = relationship(back_populates="contents")
    author: Mapped["User"] = relationship(foreign_keys=[author_id])
    editor: Mapped["User | None"] = relationship(foreign_keys=[editor_id])
    category: Mapped[CMSCategory | None] = relationship(back_populates="contents")
    tags: Mapped[list[CMSTag]] = relationship(secondary=cms_content_tags, back_populates="contents")
    genres: Mapped[list[CMSGenre]] = relationship(secondary=cms_content_genres, back_populates="contents")
    regions: Mapped[list[CMSRegion]] = relationship(secondary=cms_content_regions, back_populates="contents")
    featured_image: Mapped[CMSMediaFile | None] = relationship(foreign_keys=[featured_image_asset_id])
    media_assets: Mapped[list[CMSMediaFile]] = relationship(secondary=cms_content_media_assets)

    __table_args__ = (
        UniqueConstraint("slug", name="uq_cms_content_slug"),
        Index("idx_cms_content_status_visibility", "status", "visibility"),
        Index("idx_cms_content_language_status", "language_id", "status"),
        Index("idx_cms_content_category", "category_id"),
    )
