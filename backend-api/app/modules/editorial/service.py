"""Editorial workflow, collaboration, versioning, and publishing services."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder

from app.modules.editorial.models import CommentKind, Priority, WorkflowState
from app.modules.editorial.repository import EditorialRepository
from app.modules.editorial.schemas import (
    CommentCreate,
    PlanningUpdate,
    ProcessingResult,
    PublishRequest,
    RevisionCreate,
    ScheduleRequest,
    TransitionRequest,
    VersionComparison,
    WorkflowRestoreRequest,
)
from app.repositories.audit_repository import AuditRepository


class EditorialError(Exception):
    code = "editorial_error"


class NotFound(EditorialError):
    code = "editorial_not_found"


class Forbidden(EditorialError):
    code = "editorial_forbidden"


class Conflict(EditorialError):
    code = "editorial_optimistic_lock_conflict"


class InvalidTransition(EditorialError):
    code = "editorial_invalid_transition"


TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.DRAFT: {WorkflowState.IN_REVIEW},
    WorkflowState.IN_REVIEW: {WorkflowState.DRAFT, WorkflowState.FACT_CHECK},
    WorkflowState.FACT_CHECK: {WorkflowState.DRAFT, WorkflowState.LEGAL_REVIEW},
    WorkflowState.LEGAL_REVIEW: {WorkflowState.DRAFT, WorkflowState.EDITORIAL_APPROVAL},
    WorkflowState.EDITORIAL_APPROVAL: {WorkflowState.DRAFT, WorkflowState.APPROVED},
    WorkflowState.APPROVED: {WorkflowState.SCHEDULED, WorkflowState.PUBLISHED, WorkflowState.ARCHIVED},
    WorkflowState.SCHEDULED: {WorkflowState.PUBLISHED, WorkflowState.ARCHIVED},
    WorkflowState.PUBLISHED: {WorkflowState.EXPIRED, WorkflowState.ARCHIVED},
    WorkflowState.EXPIRED: {WorkflowState.PUBLISHED, WorkflowState.ARCHIVED},
    WorkflowState.ARCHIVED: set(),
}

TARGET_ROLES: dict[WorkflowState, set[str]] = {
    WorkflowState.IN_REVIEW: {"admin", "chief_editor", "editor", "reporter", "producer"},
    WorkflowState.FACT_CHECK: {"admin", "chief_editor", "editor"},
    WorkflowState.LEGAL_REVIEW: {"admin", "chief_editor", "fact_checker"},
    WorkflowState.EDITORIAL_APPROVAL: {"admin", "chief_editor", "editor", "legal_reviewer"},
    WorkflowState.APPROVED: {"admin", "chief_editor"},
    WorkflowState.SCHEDULED: {"admin", "chief_editor", "producer"},
    WorkflowState.PUBLISHED: {"admin", "chief_editor", "producer", "system"},
    WorkflowState.EXPIRED: {"admin", "chief_editor", "system"},
    WorkflowState.ARCHIVED: {"admin", "chief_editor"},
    WorkflowState.DRAFT: {"admin", "chief_editor", "editor", "fact_checker", "legal_reviewer"},
}


class EditorialService:
    def __init__(self, repository: EditorialRepository, audit: AuditRepository | None = None):
        self.repository = repository
        self.audit = audit

    def create(self, content_id: UUID, actor_id: int, roles: set[str], priority: Priority, due_at: datetime | None) -> Any:
        self._roles(roles, {"admin", "chief_editor", "editor", "reporter", "producer"})
        if not self.repository.content_exists(content_id):
            raise NotFound("Content does not exist")
        if self.repository.get_by_content(content_id):
            raise Conflict("Workflow already exists")
        item = self.repository.create_workflow(content_id, actor_id, priority, due_at)
        self._event(item.id, actor_id, "workflow.created", {"state": item.state.value})
        return item

    def require(self, workflow_id: UUID) -> Any:
        item = self.repository.get(workflow_id)
        if item is None:
            raise NotFound("Workflow does not exist")
        return item

    def transition(self, workflow_id: UUID, request: TransitionRequest, actor_id: int, roles: set[str]) -> Any:
        item = self.require(workflow_id)
        self._roles(roles, TARGET_ROLES[request.target_state])
        if request.target_state not in TRANSITIONS[item.state]:
            raise InvalidTransition(f"Cannot move from {item.state.value} to {request.target_state.value}")
        if request.target_state == WorkflowState.DRAFT and not request.note:
            raise InvalidTransition("A rejection reason is required")
        old = item.state
        values: dict[str, Any] = {"state": request.target_state, "last_error": None}
        if request.target_state == WorkflowState.PUBLISHED:
            values["published_at"] = datetime.now(UTC)
        self._update(item, request.expected_version, actor_id, values)
        event = "workflow.rejected" if request.target_state == WorkflowState.DRAFT else "workflow.transitioned"
        self._event(item.id, actor_id, event, {"from": old.value, "to": request.target_state.value, "note": request.note})
        if request.note:
            kind = CommentKind.REJECTION_REASON if request.target_state == WorkflowState.DRAFT else CommentKind.APPROVAL_NOTE
            self.repository.comment(item.id, actor_id, kind, request.note, [])
        self._notify(item.id, None, event, {"content_id": str(item.content_id), "state": item.state.value})
        return item

    def plan(self, workflow_id: UUID, request: PlanningUpdate, actor_id: int, roles: set[str]) -> Any:
        self._roles(roles, {"admin", "chief_editor", "editor", "producer"})
        item = self.require(workflow_id)
        values = request.model_dump(exclude={"expected_version"}, exclude_unset=True)
        self._update(item, request.expected_version, actor_id, values)
        self._event(item.id, actor_id, "workflow.planning_updated", values)
        return item

    def assign(self, workflow_id: UUID, role: Any, user_id: int, actor_id: int, roles: set[str]) -> Any:
        self._roles(roles, {"admin", "chief_editor", "editor", "producer"})
        self.require(workflow_id)
        if not self.repository.user_exists(user_id):
            raise NotFound("Assignee does not exist")
        assignment = self.repository.assign(workflow_id, role, user_id, actor_id)
        self._event(workflow_id, actor_id, "assignment.changed", {"role": role.value, "user_id": user_id})
        self._notify(workflow_id, user_id, "editorial.assignment", {"role": role.value})
        return assignment

    def comment(self, workflow_id: UUID, request: CommentCreate, actor_id: int, roles: set[str]) -> Any:
        self._roles(roles, {"admin", "chief_editor", "editor", "reporter", "producer", "fact_checker", "legal_reviewer"})
        self.require(workflow_id)
        for user_id in request.mentions:
            if not self.repository.user_exists(user_id):
                raise NotFound("Mentioned user does not exist")
        item = self.repository.comment(workflow_id, actor_id, request.kind, request.body, request.mentions)
        self._event(workflow_id, actor_id, "comment.created", {"kind": request.kind.value, "comment_id": str(item.id)})
        for user_id in set(request.mentions):
            self._notify(workflow_id, user_id, "editorial.mentioned", {"comment_id": str(item.id)})
        return item

    def revision(self, workflow_id: UUID, request: RevisionCreate, actor_id: int, roles: set[str]) -> Any:
        self._roles(roles, {"admin", "chief_editor", "editor", "reporter", "producer"})
        item = self.require(workflow_id)
        self._update(item, request.expected_version, actor_id, {})
        revision = self.repository.revision(workflow_id, request.snapshot, request.change_summary, actor_id)
        self._event(workflow_id, actor_id, "revision.created", {"version": revision.version, "summary": request.change_summary})
        return revision

    def compare(self, workflow_id: UUID, start: int, end: int) -> VersionComparison:
        self.require(workflow_id)
        left = self.repository.get_revision(workflow_id, start)
        right = self.repository.get_revision(workflow_id, end)
        if left is None or right is None:
            raise NotFound("Revision does not exist")
        keys = left.snapshot.keys() | right.snapshot.keys()
        changes = {key: {"from": left.snapshot.get(key), "to": right.snapshot.get(key)} for key in keys if left.snapshot.get(key) != right.snapshot.get(key)}
        return VersionComparison(from_version=start, to_version=end, changes=changes)

    def restore(self, workflow_id: UUID, version: int, expected: int, actor_id: int, roles: set[str]) -> Any:
        self._roles(roles, {"admin", "chief_editor", "editor"})
        item = self.require(workflow_id)
        old = self.repository.get_revision(workflow_id, version)
        if old is None:
            raise NotFound("Revision does not exist")
        self._update(item, expected, actor_id, {})
        restored = self.repository.revision(workflow_id, old.snapshot, f"Restored version {version}", actor_id)
        self._event(workflow_id, actor_id, "revision.restored", {"source_version": version, "version": restored.version})
        return restored

    def restore_archived(
        self,
        workflow_id: UUID,
        request: WorkflowRestoreRequest,
        actor_id: int,
        roles: set[str],
    ) -> Any:
        self._roles(roles, {"admin", "chief_editor"})
        item = self.require(workflow_id)
        if item.state != WorkflowState.ARCHIVED:
            raise InvalidTransition("Only archived content can be restored")
        self._update(
            item,
            request.expected_version,
            actor_id,
            {
                "state": WorkflowState.APPROVED,
                "scheduled_at": None,
                "timezone": None,
                "embargo_at": None,
                "unpublish_at": None,
                "published_at": None,
                "last_error": None,
            },
        )
        payload = {"from": WorkflowState.ARCHIVED.value, "to": WorkflowState.APPROVED.value, "reason": request.reason}
        self._event(item.id, actor_id, "workflow.restored", payload)
        self._notify(item.id, None, "editorial.workflow.restored", {"content_id": str(item.content_id), **payload})
        return item

    def schedule(self, workflow_id: UUID, request: ScheduleRequest, actor_id: int, roles: set[str]) -> Any:
        self._roles(roles, {"admin", "chief_editor", "producer"})
        item = self.require(workflow_id)
        if item.state != WorkflowState.APPROVED:
            raise InvalidTransition("Only approved content can be scheduled")
        values = {"state": WorkflowState.SCHEDULED, "scheduled_at": request.publish_at.astimezone(UTC), "timezone": request.timezone, "embargo_at": request.embargo_at.astimezone(UTC) if request.embargo_at else None, "unpublish_at": request.unpublish_at.astimezone(UTC) if request.unpublish_at else None, "last_error": None}
        self._update(item, request.expected_version, actor_id, values)
        self._event(item.id, actor_id, "publication.scheduled", {"publish_at": request.publish_at.isoformat(), "timezone": request.timezone})
        self._notify(item.id, None, "editorial.publishing_scheduled", {"publish_at": request.publish_at.isoformat()})
        return item

    def publish(self, workflow_id: UUID, request: PublishRequest, actor_id: int, roles: set[str], emergency: bool = False, republish: bool = False) -> Any:
        allowed = {WorkflowState.APPROVED, WorkflowState.SCHEDULED}
        target = WorkflowState.PUBLISHED
        if emergency:
            self._roles(roles, {"admin", "chief_editor"})
            allowed, target = {WorkflowState.PUBLISHED}, WorkflowState.EXPIRED
            if not request.reason:
                raise InvalidTransition("Emergency unpublish requires a reason")
        elif republish:
            self._roles(roles, {"admin", "chief_editor"})
            allowed = {WorkflowState.EXPIRED}
        else:
            self._roles(roles, {"admin", "chief_editor", "producer"})
        item = self.require(workflow_id)
        if item.state not in allowed:
            raise InvalidTransition("Content is not in a publishable state")
        now = datetime.now(UTC)
        if target == WorkflowState.PUBLISHED and item.embargo_at and self._aware(item.embargo_at) > now:
            raise InvalidTransition("Content is under embargo")
        values: dict[str, Any] = {"state": target, "last_error": None}
        if target == WorkflowState.PUBLISHED:
            values["published_at"] = now
        self._update(item, request.expected_version, actor_id, values)
        event = "publication.emergency_unpublished" if emergency else ("publication.republished" if republish else "publication.published")
        self._event(item.id, actor_id, event, {"reason": request.reason})
        self._notify(item.id, None, f"editorial.{event}", {"content_id": str(item.content_id)})
        return item

    def process_due(self, actor_id: int = 1) -> ProcessingResult:
        result = ProcessingResult()
        now = datetime.now(UTC)
        for item in self.repository.due_publications(now):
            try:
                if item.state == WorkflowState.SCHEDULED and (not item.embargo_at or self._aware(item.embargo_at) <= now):
                    self._update(item, item.lock_version, actor_id, {"state": WorkflowState.PUBLISHED, "published_at": now, "last_error": None})
                    result.published += 1
                    self._event(item.id, actor_id, "publication.auto_published", {})
                elif item.state == WorkflowState.PUBLISHED:
                    self._update(item, item.lock_version, actor_id, {"state": WorkflowState.EXPIRED})
                    result.unpublished += 1
                    self._event(item.id, actor_id, "publication.auto_unpublished", {})
            except Exception as exc:
                result.failed += 1
                self.repository.compare_and_update(item, item.lock_version, actor_id, {"last_error": str(exc)})
                self._notify(item.id, None, "editorial.publishing_failed", {"error": str(exc)})
        return result

    def review_reminders(self, actor_id: int, roles: set[str]) -> list[Any]:
        self._roles(roles, {"admin", "chief_editor", "editor", "producer"})
        records: list[Any] = []
        for item in self.repository.overdue_reviews(datetime.now(UTC)):
            assignments = self.repository.assignments(item.id)
            recipients: set[int | None] = {assignment.user_id for assignment in assignments}
            if not recipients:
                recipients.add(None)
            for recipient_id in recipients:
                records.extend(
                    self.repository.notify(
                        item.id,
                        recipient_id,
                        "editorial.review_reminder",
                        {"content_id": str(item.content_id), "due_at": item.due_at.isoformat() if item.due_at else None},
                    )
                )
            self._event(item.id, actor_id, "review.reminder_sent", {"recipients": list(recipients)})
        return records

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    def _update(self, item: Any, expected: int, actor_id: int, values: dict[str, Any]) -> None:
        if item.lock_version != expected or not self.repository.compare_and_update(item, expected, actor_id, values):
            raise Conflict("Content changed since it was loaded")

    @staticmethod
    def _roles(actual: set[str], allowed: set[str]) -> None:
        if not actual & allowed:
            raise Forbidden("Role cannot perform this editorial action")

    def _event(self, workflow_id: UUID, actor_id: int, event: str, data: dict[str, Any]) -> None:
        serialized: dict[str, Any] = jsonable_encoder(data)
        self.repository.activity(workflow_id, actor_id, event, serialized)
        if self.audit:
            self.audit.create(actor_id, f"editorial.{event}", {"workflow_id": str(workflow_id), **serialized})

    def _notify(self, workflow_id: UUID, recipient_id: int | None, event: str, payload: dict[str, Any]) -> None:
        self.repository.notify(workflow_id, recipient_id, event, payload)
