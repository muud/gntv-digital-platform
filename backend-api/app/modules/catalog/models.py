"""SQLAlchemy 2.x models for the premium streaming catalog."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CatalogType(StrEnum):
    MOVIE = "movie"
    SERIES = "series"
    SEASON = "season"
    EPISODE = "episode"
    LIVE_TV = "live_tv"
    RADIO = "radio"
    PODCAST = "podcast"
    SHORT = "short"
    KIDS = "kids"
    NEWS = "news"


class CatalogStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class CreditRole(StrEnum):
    CAST = "cast"
    CREW = "crew"
    DIRECTOR = "director"
    PRODUCER = "producer"


item_genres = Table(
    "catalog_item_genres",
    Base.metadata,
    Column(
        "item_id",
        Uuid,
        ForeignKey("catalog_items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "genre_id",
        Uuid,
        ForeignKey("catalog_genres.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
item_languages = Table(
    "catalog_item_languages",
    Base.metadata,
    Column(
        "item_id",
        Uuid,
        ForeignKey("catalog_items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "language_id",
        Uuid,
        ForeignKey("catalog_languages.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
item_regions = Table(
    "catalog_item_regions",
    Base.metadata,
    Column(
        "item_id",
        Uuid,
        ForeignKey("catalog_items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "region_id",
        Uuid,
        ForeignKey("catalog_regions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
collection_items = Table(
    "catalog_collection_items",
    Base.metadata,
    Column(
        "collection_id",
        Uuid,
        ForeignKey("catalog_collections.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "item_id",
        Uuid,
        ForeignKey("catalog_items.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("position", Integer, nullable=False, default=0),
)


class TaxonomyBase:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False, unique=True)


class CatalogGenre(Base, TaxonomyBase):
    __tablename__ = "catalog_genres"


class CatalogLanguage(Base, TaxonomyBase):
    __tablename__ = "catalog_languages"
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)


class CatalogRegion(Base, TaxonomyBase):
    __tablename__ = "catalog_regions"
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)


class CatalogStudio(Base):
    __tablename__ = "catalog_studios"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    website: Mapped[str | None] = mapped_column(String(500))


class CatalogPerson(Base):
    __tablename__ = "catalog_people"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    biography: Mapped[str | None] = mapped_column(Text)
    image_asset_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("cms_media_files.id", ondelete="SET NULL")
    )


class CatalogItem(Base):
    __tablename__ = "catalog_items"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    catalog_type: Mapped[CatalogType] = mapped_column(
        Enum(
            CatalogType,
            name="gntv_catalog_type",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    status: Mapped[CatalogStatus] = mapped_column(
        Enum(
            CatalogStatus,
            name="gntv_catalog_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        default=CatalogStatus.DRAFT,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    synopsis: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("catalog_items.id", ondelete="CASCADE")
    )
    season_number: Mapped[int | None] = mapped_column(Integer)
    episode_number: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    release_date: Mapped[date | None] = mapped_column(Date)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_kids: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    age_rating: Mapped[str | None] = mapped_column(String(20))
    stream_url: Mapped[str | None] = mapped_column(String(2048))
    media_asset_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("cms_media_files.id", ondelete="SET NULL")
    )
    poster_asset_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("cms_media_files.id", ondelete="SET NULL")
    )
    studio_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("catalog_studios.id", ondelete="SET NULL")
    )
    seo_title: Mapped[str | None] = mapped_column(String(255))
    seo_description: Mapped[str | None] = mapped_column(String(500))
    seo_keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    ai_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    ai_enrichment_status: Mapped[str] = mapped_column(
        String(30), default="not_requested", nullable=False
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parent: Mapped["CatalogItem | None"] = relationship(
        remote_side=[id], back_populates="children"
    )
    children: Mapped[list["CatalogItem"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    genres: Mapped[list[CatalogGenre]] = relationship(secondary=item_genres)
    languages: Mapped[list[CatalogLanguage]] = relationship(secondary=item_languages)
    regions: Mapped[list[CatalogRegion]] = relationship(secondary=item_regions)
    credits: Mapped[list["CatalogCredit"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    __table_args__ = (
        Index("idx_catalog_type_status", "catalog_type", "status"),
        Index("idx_catalog_parent", "parent_id"),
        Index("idx_catalog_search", "title", "slug"),
    )


class CatalogCredit(Base):
    __tablename__ = "catalog_credits"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("catalog_people.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[CreditRole] = mapped_column(
        Enum(
            CreditRole,
            name="gntv_credit_role",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    character_name: Mapped[str | None] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer, default=0)
    item: Mapped[CatalogItem] = relationship(back_populates="credits")
    person: Mapped[CatalogPerson] = relationship()
    __table_args__ = (
        UniqueConstraint("item_id", "person_id", "role", name="uq_catalog_credit"),
    )


class CatalogCollection(Base):
    __tablename__ = "catalog_collections"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    row_style: Mapped[str] = mapped_column(String(30), default="landscape")
    position: Mapped[int] = mapped_column(Integer, default=0)
    items: Mapped[list[CatalogItem]] = relationship(secondary=collection_items)


class ContinueWatching(Base):
    __tablename__ = "catalog_continue_watching"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("catalog_items.id", ondelete="CASCADE")
    )
    position_seconds: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    item: Mapped[CatalogItem] = relationship()
    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_catalog_progress"),
    )


class CatalogRating(Base):
    __tablename__ = "catalog_ratings"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    item_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("catalog_items.id", ondelete="CASCADE")
    )
    score: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    __table_args__ = (UniqueConstraint("user_id", "item_id", name="uq_catalog_rating"),)
