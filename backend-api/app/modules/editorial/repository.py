"""Repository pattern implementation for editorial persistence."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CursorResult, func, or_, select, update
from sqlalchemy.orm import Session

from app.modules.cms.models import CMSContent
from app.modules.editorial.models import (
    AssignmentRole,
    CommentKind,
    EditorialActivity,
    EditorialAssignment,
    EditorialComment,
    EditorialNotification,
    EditorialRevision,
    EditorialWorkflow,
    NotificationChannel,
    Priority,
    WorkflowState,
)


class EditorialRepository:
    def __init__(self, db: Session):
        self.db = db

    def content_exists(self, content_id: UUID) -> bool:
        return self.db.get(CMSContent, content_id) is not None

    def user_exists(self, user_id: int) -> bool:
        from app.models.user import User

        return self.db.get(User, user_id) is not None

    def create_workflow(self, content_id: UUID, actor_id: int, priority: Priority, due_at: datetime | None) -> EditorialWorkflow:
        item = EditorialWorkflow(content_id=content_id, created_by=actor_id, updated_by=actor_id, priority=priority, due_at=due_at)
        self.db.add(item)
        self.db.flush()
        return item

    def get(self, workflow_id: UUID) -> EditorialWorkflow | None:
        return self.db.get(EditorialWorkflow, workflow_id)

    def get_by_content(self, content_id: UUID) -> EditorialWorkflow | None:
        return self.db.execute(select(EditorialWorkflow).where(EditorialWorkflow.content_id == content_id)).scalar_one_or_none()

    def compare_and_update(self, item: EditorialWorkflow, expected: int, actor_id: int, values: dict[str, Any]) -> bool:
        update_values = {**values, "updated_by": actor_id, "updated_at": datetime.utcnow(), "lock_version": expected + 1}
        result = self.db.execute(
            update(EditorialWorkflow)
            .where(EditorialWorkflow.id == item.id, EditorialWorkflow.lock_version == expected)
            .values(**update_values)
        )
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            self.db.expire(item)
            return False
        self.db.flush()
        self.db.refresh(item)
        return True

    def assign(self, workflow_id: UUID, role: AssignmentRole, user_id: int, actor_id: int) -> EditorialAssignment:
        item = self.db.execute(
            select(EditorialAssignment).where(EditorialAssignment.workflow_id == workflow_id, EditorialAssignment.role == role)
        ).scalar_one_or_none()
        if item is None:
            item = EditorialAssignment(workflow_id=workflow_id, role=role, user_id=user_id, assigned_by=actor_id)
        else:
            item.user_id = user_id
            item.assigned_by = actor_id
            item.assigned_at = datetime.utcnow()
        self.db.add(item)
        self.db.flush()
        return item

    def assignments(self, workflow_id: UUID) -> Sequence[EditorialAssignment]:
        return self.db.execute(select(EditorialAssignment).where(EditorialAssignment.workflow_id == workflow_id)).scalars().all()

    def comment(self, workflow_id: UUID, author_id: int, kind: CommentKind, body: str, mentions: list[int]) -> EditorialComment:
        item = EditorialComment(workflow_id=workflow_id, author_id=author_id, kind=kind, body=body, mentions=mentions)
        self.db.add(item)
        self.db.flush()
        return item

    def comments(self, workflow_id: UUID) -> Sequence[EditorialComment]:
        return self.db.execute(select(EditorialComment).where(EditorialComment.workflow_id == workflow_id).order_by(EditorialComment.created_at)).scalars().all()

    def revision(self, workflow_id: UUID, snapshot: dict[str, Any], summary: str, editor_id: int) -> EditorialRevision:
        version = self.db.execute(select(func.coalesce(func.max(EditorialRevision.version), 0)).where(EditorialRevision.workflow_id == workflow_id)).scalar_one() + 1
        item = EditorialRevision(workflow_id=workflow_id, version=version, snapshot=snapshot, change_summary=summary, editor_id=editor_id)
        self.db.add(item)
        self.db.flush()
        return item

    def revisions(self, workflow_id: UUID) -> Sequence[EditorialRevision]:
        return self.db.execute(select(EditorialRevision).where(EditorialRevision.workflow_id == workflow_id).order_by(EditorialRevision.version.desc())).scalars().all()

    def get_revision(self, workflow_id: UUID, version: int) -> EditorialRevision | None:
        return self.db.execute(select(EditorialRevision).where(EditorialRevision.workflow_id == workflow_id, EditorialRevision.version == version)).scalar_one_or_none()

    def activity(self, workflow_id: UUID, actor_id: int, event_type: str, data: dict[str, Any]) -> EditorialActivity:
        item = EditorialActivity(workflow_id=workflow_id, actor_id=actor_id, event_type=event_type, data=data)
        self.db.add(item)
        self.db.flush()
        return item

    def activities(self, workflow_id: UUID | None = None, limit: int = 100) -> Sequence[EditorialActivity]:
        query = select(EditorialActivity)
        if workflow_id is not None:
            query = query.where(EditorialActivity.workflow_id == workflow_id)
        return self.db.execute(query.order_by(EditorialActivity.created_at.desc()).limit(limit)).scalars().all()

    def notify(self, workflow_id: UUID, recipient_id: int | None, event_type: str, payload: dict[str, Any]) -> list[EditorialNotification]:
        records = [
            EditorialNotification(workflow_id=workflow_id, recipient_id=recipient_id, channel=channel, event_type=event_type, payload=payload)
            for channel in NotificationChannel
        ]
        self.db.add_all(records)
        self.db.flush()
        return records

    def notifications(self, recipient_id: int, limit: int = 100) -> Sequence[EditorialNotification]:
        return self.db.execute(
            select(EditorialNotification)
            .where(or_(EditorialNotification.recipient_id == recipient_id, EditorialNotification.recipient_id.is_(None)))
            .order_by(EditorialNotification.created_at.desc()).limit(limit)
        ).scalars().all()

    def dashboard(self, *, states: set[WorkflowState] | None = None, assigned_to: int | None = None, failed: bool = False, limit: int = 100) -> Sequence[EditorialWorkflow]:
        query = select(EditorialWorkflow)
        if assigned_to is not None:
            query = query.join(EditorialAssignment).where(EditorialAssignment.user_id == assigned_to)
        if states:
            query = query.where(EditorialWorkflow.state.in_(states))
        if failed:
            query = query.where(EditorialWorkflow.last_error.is_not(None))
        return self.db.execute(query.order_by(EditorialWorkflow.updated_at.desc()).limit(limit)).scalars().unique().all()

    def due_publications(self, now: datetime) -> Sequence[EditorialWorkflow]:
        return self.db.execute(select(EditorialWorkflow).where(
            or_(
                (EditorialWorkflow.state == WorkflowState.SCHEDULED) & (EditorialWorkflow.scheduled_at <= now),
                (EditorialWorkflow.state == WorkflowState.PUBLISHED) & (EditorialWorkflow.unpublish_at <= now),
            )
        )).scalars().all()

    def overdue_reviews(self, now: datetime) -> Sequence[EditorialWorkflow]:
        review_states = {
            WorkflowState.IN_REVIEW,
            WorkflowState.FACT_CHECK,
            WorkflowState.LEGAL_REVIEW,
            WorkflowState.EDITORIAL_APPROVAL,
        }
        return self.db.execute(
            select(EditorialWorkflow).where(
                EditorialWorkflow.state.in_(review_states),
                EditorialWorkflow.due_at.is_not(None),
                EditorialWorkflow.due_at <= now,
            )
        ).scalars().all()
