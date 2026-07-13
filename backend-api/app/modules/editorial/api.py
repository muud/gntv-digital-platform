"""Version 1 REST API for CMS Module 4."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.cms.permissions import CMSScope, has_scope
from app.modules.editorial.models import WorkflowState
from app.modules.editorial.repository import EditorialRepository
from app.modules.editorial.schemas import (
    ActivityResponse,
    AssignmentResponse,
    AssignmentUpsert,
    CommentCreate,
    CommentResponse,
    DashboardResponse,
    NotificationResponse,
    PlanningUpdate,
    ProcessingResult,
    PublishRequest,
    RevisionCreate,
    RevisionResponse,
    ScheduleRequest,
    TransitionRequest,
    VersionComparison,
    WorkflowCreate,
    WorkflowResponse,
)
from app.modules.editorial.service import Conflict, EditorialError, EditorialService, Forbidden, NotFound
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/api/v1/editorial", tags=["CMS Editorial Workflow"])


def service(db: Session = Depends(get_db)) -> EditorialService:
    return EditorialService(EditorialRepository(db), AuditRepository(db))


def access(write: bool = False) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        scope: CMSScope = "content:write" if write else "content:read-draft"
        specialist_roles = {"fact_checker", "legal_reviewer", "producer"}
        if not has_scope(roles=user.role_names, required_scope=scope) and not set(user.role_names) & specialist_roles:
            raise HTTPException(403, detail={"code": "editorial_forbidden"})
        return user

    return dependency


ReadUser = Annotated[User, Depends(access())]
WriteUser = Annotated[User, Depends(access(True))]
Service = Annotated[EditorialService, Depends(service)]


def failure(exc: EditorialError) -> HTTPException:
    status = 404 if isinstance(exc, NotFound) else 403 if isinstance(exc, Forbidden) else 409 if isinstance(exc, Conflict) else 422
    return HTTPException(status, detail={"code": exc.code, "message": str(exc)})


@router.post("/workflows", response_model=WorkflowResponse, status_code=201)
def create(payload: WorkflowCreate, user: WriteUser, svc: Service) -> WorkflowResponse:
    try:
        return WorkflowResponse.model_validate(svc.create(payload.content_id, user.id, set(user.role_names), payload.priority, payload.due_at))
    except EditorialError as exc:
        raise failure(exc) from exc


@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
def detail(workflow_id: UUID, user: ReadUser, svc: Service) -> WorkflowResponse:
    del user
    try:
        return WorkflowResponse.model_validate(svc.require(workflow_id))
    except EditorialError as exc:
        raise failure(exc) from exc


@router.patch("/workflows/{workflow_id}/planning", response_model=WorkflowResponse)
def planning(workflow_id: UUID, payload: PlanningUpdate, user: WriteUser, svc: Service) -> WorkflowResponse:
    try:
        return WorkflowResponse.model_validate(svc.plan(workflow_id, payload, user.id, set(user.role_names)))
    except EditorialError as exc:
        raise failure(exc) from exc


@router.post("/workflows/{workflow_id}/transitions", response_model=WorkflowResponse)
def transition(workflow_id: UUID, payload: TransitionRequest, user: WriteUser, svc: Service) -> WorkflowResponse:
    try:
        return WorkflowResponse.model_validate(svc.transition(workflow_id, payload, user.id, set(user.role_names)))
    except EditorialError as exc:
        raise failure(exc) from exc


@router.put("/workflows/{workflow_id}/assignments", response_model=AssignmentResponse)
def assign(workflow_id: UUID, payload: AssignmentUpsert, user: WriteUser, svc: Service) -> AssignmentResponse:
    try:
        return AssignmentResponse.model_validate(svc.assign(workflow_id, payload.role, payload.user_id, user.id, set(user.role_names)))
    except EditorialError as exc:
        raise failure(exc) from exc


@router.get("/workflows/{workflow_id}/assignments", response_model=list[AssignmentResponse])
def assignments(workflow_id: UUID, user: ReadUser, svc: Service) -> list[AssignmentResponse]:
    del user
    try:
        svc.require(workflow_id)
        return [AssignmentResponse.model_validate(x) for x in svc.repository.assignments(workflow_id)]
    except EditorialError as exc:
        raise failure(exc) from exc


@router.post("/workflows/{workflow_id}/comments", response_model=CommentResponse, status_code=201)
def comment(workflow_id: UUID, payload: CommentCreate, user: WriteUser, svc: Service) -> CommentResponse:
    try:
        return CommentResponse.model_validate(svc.comment(workflow_id, payload, user.id, set(user.role_names)))
    except EditorialError as exc:
        raise failure(exc) from exc


@router.get("/workflows/{workflow_id}/comments", response_model=list[CommentResponse])
def comments(workflow_id: UUID, user: ReadUser, svc: Service) -> list[CommentResponse]:
    del user
    try:
        svc.require(workflow_id)
        return [CommentResponse.model_validate(x) for x in svc.repository.comments(workflow_id)]
    except EditorialError as exc:
        raise failure(exc) from exc


@router.post("/workflows/{workflow_id}/revisions", response_model=RevisionResponse, status_code=201)
def revision(workflow_id: UUID, payload: RevisionCreate, user: WriteUser, svc: Service) -> RevisionResponse:
    try:
        return RevisionResponse.model_validate(svc.revision(workflow_id, payload, user.id, set(user.role_names)))
    except EditorialError as exc:
        raise failure(exc) from exc


@router.get("/workflows/{workflow_id}/revisions", response_model=list[RevisionResponse])
def revisions(workflow_id: UUID, user: ReadUser, svc: Service) -> list[RevisionResponse]:
    del user
    try:
        svc.require(workflow_id)
        return [RevisionResponse.model_validate(x) for x in svc.repository.revisions(workflow_id)]
    except EditorialError as exc:
        raise failure(exc) from exc


@router.get("/workflows/{workflow_id}/revisions/compare", response_model=VersionComparison)
def compare(workflow_id: UUID, user: ReadUser, svc: Service, from_version: int = Query(ge=1), to_version: int = Query(ge=1)) -> VersionComparison:
    del user
    try:
        return svc.compare(workflow_id, from_version, to_version)
    except EditorialError as exc:
        raise failure(exc) from exc


@router.post("/workflows/{workflow_id}/revisions/{version}/restore", response_model=RevisionResponse)
def restore(workflow_id: UUID, version: int, expected_version: int, user: WriteUser, svc: Service) -> RevisionResponse:
    try:
        return RevisionResponse.model_validate(svc.restore(workflow_id, version, expected_version, user.id, set(user.role_names)))
    except EditorialError as exc:
        raise failure(exc) from exc


@router.post("/workflows/{workflow_id}/schedule", response_model=WorkflowResponse)
def schedule(workflow_id: UUID, payload: ScheduleRequest, user: WriteUser, svc: Service) -> WorkflowResponse:
    try:
        return WorkflowResponse.model_validate(svc.schedule(workflow_id, payload, user.id, set(user.role_names)))
    except EditorialError as exc:
        raise failure(exc) from exc


def publication_action(workflow_id: UUID, payload: PublishRequest, user: User, svc: EditorialService, *, emergency: bool = False, republish: bool = False) -> WorkflowResponse:
    try:
        return WorkflowResponse.model_validate(svc.publish(workflow_id, payload, user.id, set(user.role_names), emergency, republish))
    except EditorialError as exc:
        raise failure(exc) from exc


@router.post("/workflows/{workflow_id}/publish", response_model=WorkflowResponse)
def publish(workflow_id: UUID, payload: PublishRequest, user: WriteUser, svc: Service) -> WorkflowResponse:
    return publication_action(workflow_id, payload, user, svc)


@router.post("/workflows/{workflow_id}/republish", response_model=WorkflowResponse)
def republish(workflow_id: UUID, payload: PublishRequest, user: WriteUser, svc: Service) -> WorkflowResponse:
    return publication_action(workflow_id, payload, user, svc, republish=True)


@router.post("/workflows/{workflow_id}/emergency-unpublish", response_model=WorkflowResponse)
def emergency_unpublish(workflow_id: UUID, payload: PublishRequest, user: WriteUser, svc: Service) -> WorkflowResponse:
    return publication_action(workflow_id, payload, user, svc, emergency=True)


@router.post("/publishing/process-due", response_model=ProcessingResult)
def process_due(user: WriteUser, svc: Service) -> ProcessingResult:
    if not set(user.role_names) & {"admin", "chief_editor"}:
        raise HTTPException(403, detail={"code": "editorial_forbidden"})
    return svc.process_due(user.id)


@router.get("/workflows/{workflow_id}/activity", response_model=list[ActivityResponse])
def activity(workflow_id: UUID, user: ReadUser, svc: Service) -> list[ActivityResponse]:
    del user
    try:
        svc.require(workflow_id)
        return [ActivityResponse.model_validate(x) for x in svc.repository.activities(workflow_id)]
    except EditorialError as exc:
        raise failure(exc) from exc


@router.get("/notifications", response_model=list[NotificationResponse])
def notifications(user: ReadUser, svc: Service) -> list[NotificationResponse]:
    return [NotificationResponse.model_validate(x) for x in svc.repository.notifications(user.id)]


@router.post("/notifications/review-reminders", response_model=list[NotificationResponse])
def review_reminders(user: WriteUser, svc: Service) -> list[NotificationResponse]:
    try:
        return [NotificationResponse.model_validate(x) for x in svc.review_reminders(user.id, set(user.role_names))]
    except EditorialError as exc:
        raise failure(exc) from exc


def dashboard_response(items: list[object]) -> DashboardResponse:
    converted = [WorkflowResponse.model_validate(x) for x in items]
    return DashboardResponse(items=converted, total=len(converted))


@router.get("/dashboard/pending-reviews", response_model=DashboardResponse)
def pending(user: ReadUser, svc: Service) -> DashboardResponse:
    del user
    states = {WorkflowState.IN_REVIEW, WorkflowState.FACT_CHECK, WorkflowState.LEGAL_REVIEW, WorkflowState.EDITORIAL_APPROVAL}
    return dashboard_response(list(svc.repository.dashboard(states=states)))


@router.get("/dashboard/assigned-to-me", response_model=DashboardResponse)
def assigned_to_me(user: ReadUser, svc: Service) -> DashboardResponse:
    return dashboard_response(list(svc.repository.dashboard(assigned_to=user.id)))


@router.get("/dashboard/scheduled-content", response_model=DashboardResponse)
def scheduled(user: ReadUser, svc: Service) -> DashboardResponse:
    del user
    return dashboard_response(list(svc.repository.dashboard(states={WorkflowState.SCHEDULED})))


@router.get("/dashboard/publishing-queue", response_model=DashboardResponse)
def queue(user: ReadUser, svc: Service) -> DashboardResponse:
    del user
    return dashboard_response(list(svc.repository.dashboard(states={WorkflowState.APPROVED, WorkflowState.SCHEDULED})))


@router.get("/dashboard/failed-publications", response_model=DashboardResponse)
def failed(user: ReadUser, svc: Service) -> DashboardResponse:
    del user
    return dashboard_response(list(svc.repository.dashboard(failed=True)))


@router.get("/dashboard/recent-activity", response_model=list[ActivityResponse])
def recent(user: ReadUser, svc: Service) -> list[ActivityResponse]:
    del user
    return [ActivityResponse.model_validate(x) for x in svc.repository.activities()]


@router.delete("/notifications/{notification_id}", status_code=204, include_in_schema=False)
def dismiss_notification(notification_id: UUID, user: ReadUser) -> Response:
    del notification_id, user
    return Response(status_code=204)
