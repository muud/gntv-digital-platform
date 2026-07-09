"""CMS asset ORM models."""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Interval, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.cms.models.base import AuditBase, ContentBase, LocalizationBase, MediaAssetBase, WorkflowBase
from app.modules.cms.models.enums import ContentType, WorkflowState

if TYPE_CHECKING:
    from app.models.user import User


content_type_enum = Enum(
    ContentType,
    name="gntv_content_type",
    values_callable=lambda enum: [member.value for member in enum],
)

workflow_state_enum = Enum(
    WorkflowState,
    name="gntv_workflow_state",
    values_callable=lambda enum: [member.value for member in enum],
)


class CMSAsset(Base, ContentBase):
    __tablename__ = "cms_assets"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    content_type: Mapped[ContentType] = mapped_column(content_type_enum, nullable=False)
    parent_asset_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cms_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    duration: Mapped[timedelta | None] = mapped_column(Interval, nullable=True)
    publish_state: Mapped[WorkflowState] = mapped_column(
        workflow_state_enum,
        nullable=False,
        default=WorkflowState.DRAFT,
        server_default=WorkflowState.DRAFT.value,
    )
    scheduled_publish_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    age_rating: Mapped[str | None] = mapped_column(String(10), nullable=True, default="G", server_default="G")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    parent: Mapped["CMSAsset | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["CMSAsset"]] = relationship(back_populates="parent")
    translations: Mapped[list["CMSAssetTranslation"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    media_files: Mapped[list["CMSMediaFile"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    workflow_logs: Mapped[list["CMSWorkflowLog"]] = relationship(back_populates="asset", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_cms_assets_type_state", "content_type", "publish_state"),
        Index("idx_cms_assets_parent", "parent_asset_id"),
    )


class CMSAssetTranslation(Base, LocalizationBase):
    __tablename__ = "cms_asset_translations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cms_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    language_code: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(50)), nullable=False, default=list, server_default="{}")
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtitles_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    asset: Mapped[CMSAsset] = relationship(back_populates="translations")

    __table_args__ = (
        UniqueConstraint("asset_id", "language_code", name="uq_asset_language"),
        Index("idx_cms_translations_lookup", "asset_id", "language_code"),
        Index("idx_cms_translations_tags", "tags", postgresql_using="gin"),
    )


class CMSMediaFile(Base, MediaAssetBase):
    __tablename__ = "cms_media_files"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cms_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bitrate: Mapped[int | None] = mapped_column(nullable=True)
    codec: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    asset: Mapped[CMSAsset] = relationship(back_populates="media_files")

    __table_args__ = (Index("idx_cms_media_asset", "asset_id"),)


class CMSWorkflowLog(Base, WorkflowBase, AuditBase):
    __tablename__ = "cms_workflow_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cms_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    old_state: Mapped[WorkflowState | None] = mapped_column(workflow_state_enum, nullable=True)
    new_state: Mapped[WorkflowState] = mapped_column(workflow_state_enum, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    asset: Mapped[CMSAsset] = relationship(back_populates="workflow_logs")
    actor: Mapped["User"] = relationship()

    __table_args__ = (Index("idx_workflow_asset_logs", "asset_id"),)
