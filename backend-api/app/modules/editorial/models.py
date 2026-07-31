"""SQLAlchemy 2.x persistence for editorial workflow."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class WorkflowState(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    FACT_CHECK = "fact_check"
    LEGAL_REVIEW = "legal_review"
    EDITORIAL_APPROVAL = "editorial_approval"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    EXPIRED = "expired"
    ARCHIVED = "archived"


class AssignmentRole(StrEnum):
    REPORTER = "reporter"
    EDITOR = "editor"
    PRODUCER = "producer"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class CommentKind(StrEnum):
    INTERNAL = "internal"
    REVIEW_NOTE = "review_note"
    REJECTION_REASON = "rejection_reason"
    APPROVAL_NOTE = "approval_note"


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"
    WEBHOOK = "webhook"


state_enum = Enum(WorkflowState, name="gntv_editorial_state", values_callable=lambda e: [x.value for x in e])


class EditorialWorkflow(Base):
    __tablename__ = "editorial_workflows"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    content_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("cms_content.id", ondelete="CASCADE"), unique=True)
    state: Mapped[WorkflowState] = mapped_column(state_enum, default=WorkflowState.DRAFT, nullable=False)
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="gntv_editorial_priority", values_callable=lambda e: [x.value for x in e]),
        default=Priority.NORMAL,
        nullable=False,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str | None] = mapped_column(String(64))
    embargo_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unpublish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lock_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    assignments: Mapped[list["EditorialAssignment"]] = relationship(cascade="all, delete-orphan")
    __table_args__ = (Index("idx_editorial_state_schedule", "state", "scheduled_at"),)


class EditorialAssignment(Base):
    __tablename__ = "editorial_assignments"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("editorial_workflows.id", ondelete="CASCADE"))
    role: Mapped[AssignmentRole] = mapped_column(
        Enum(AssignmentRole, name="gntv_assignment_role", values_callable=lambda e: [x.value for x in e])
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("workflow_id", "role", name="uq_editorial_assignment_role"),)


class EditorialComment(Base):
    __tablename__ = "editorial_comments"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("editorial_workflows.id", ondelete="CASCADE"))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[CommentKind] = mapped_column(
        Enum(CommentKind, name="gntv_editorial_comment_kind", values_callable=lambda e: [x.value for x in e])
    )
    body: Mapped[str] = mapped_column(Text)
    mentions: Mapped[list[int]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class EditorialRevision(Base):
    __tablename__ = "editorial_revisions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("editorial_workflows.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    change_summary: Mapped[str] = mapped_column(String(500))
    editor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("workflow_id", "version", name="uq_editorial_revision_version"),)


class EditorialActivity(Base):
    __tablename__ = "editorial_activity"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("editorial_workflows.id", ondelete="CASCADE"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)


class EditorialNotification(Base):
    __tablename__ = "editorial_notifications"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("editorial_workflows.id", ondelete="CASCADE"))
    recipient_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="gntv_notification_channel", values_callable=lambda e: [x.value for x in e])
    )
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (Index("idx_editorial_notification_recipient", "recipient_id", "delivered_at"),)
