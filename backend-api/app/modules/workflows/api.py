"""FastAPI API router for Workflow Orchestration & Job Execution Platform."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.workflows.models import (
    WorkflowRunStatus,
    WorkflowStatus,
    WorkflowTriggerType,
)
from app.modules.workflows.repository import WorkflowRepository
from app.modules.workflows.schemas import (
    WorkflowAuditLogResponse,
    WorkflowCreate,
    WorkflowManualApprovalAction,
    WorkflowMetricsSummaryResponse,
    WorkflowResponse,
    WorkflowRunCreate,
    WorkflowRunDetailResponse,
    WorkflowRunResponse,
    WorkflowScheduleCreate,
    WorkflowScheduleResponse,
    WorkflowTriggerCreate,
    WorkflowTriggerResponse,
    WorkflowUpdate,
)
from app.modules.workflows.service import WorkflowService

workflows_router = APIRouter(prefix="/api/v1/workflows", tags=["Workflows"])
workflow_runs_router = APIRouter(prefix="/api/v1/workflow-runs", tags=["Workflow Runs"])
runs_router = workflow_runs_router

OPERATOR_ROLES = {"admin", "operator", "super_admin"}
READ_ROLES = {"admin", "operator", "super_admin", "viewer"}


def get_service(db: Session = Depends(get_db)) -> WorkflowService:
    return WorkflowService(WorkflowRepository(db))


def require_operator_role(user: User = Depends(get_current_user)) -> User:
    """Enforce operator/admin clearance for workflow mutations."""
    roles = set(user.role_names) if hasattr(user, "role_names") else {r.name for r in user.roles}
    if not (roles & OPERATOR_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator or Admin clearance required for workflow mutations",
        )
    return user


def require_read_role(user: User = Depends(get_current_user)) -> User:
    """Enforce read clearance for inspecting workflows and runs."""
    roles = set(user.role_names) if hasattr(user, "role_names") else {r.name for r in user.roles}
    if not (roles & READ_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Clearance required to view workflows",
        )
    return user


# =====================================================================
# Workflow Definitions Endpoints (/api/v1/workflows)
# =====================================================================

@workflows_router.get(
    "/metrics/summary",
    response_model=WorkflowMetricsSummaryResponse,
    summary="Get workflow orchestration metrics summary",
)
def get_workflow_metrics(
    service: WorkflowService = Depends(get_service),
    _user: User = Depends(require_read_role),
) -> WorkflowMetricsSummaryResponse:
    metrics = service.get_metrics_summary()
    return WorkflowMetricsSummaryResponse(**metrics)


@workflows_router.get(
    "",
    response_model=list[WorkflowResponse],
    summary="List workflow definitions",
)
def list_workflows(
    status: WorkflowStatus | None = None,
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    service: WorkflowService = Depends(get_service),
    _user: User = Depends(require_read_role),
) -> list[WorkflowResponse]:
    workflows = service.list_workflows(status=status, limit=limit, offset=offset)
    return [WorkflowResponse.model_validate(w) for w in workflows]


@workflows_router.post(
    "",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workflow definition with steps",
)
def create_workflow(
    payload: WorkflowCreate,
    service: WorkflowService = Depends(get_service),
    user: User = Depends(require_operator_role),
) -> WorkflowResponse:
    workflow = service.create_workflow(payload, user_id=user.id)
    return WorkflowResponse.model_validate(workflow)


@workflows_router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Get workflow definition details",
)
def get_workflow(
    workflow_id: UUID,
    service: WorkflowService = Depends(get_service),
    _user: User = Depends(require_read_role),
) -> WorkflowResponse:
    try:
        workflow = service.get_workflow(workflow_id)
        return WorkflowResponse.model_validate(workflow)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@workflows_router.patch(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Update workflow definition",
)
def update_workflow(
    workflow_id: UUID,
    payload: WorkflowUpdate,
    service: WorkflowService = Depends(get_service),
    user: User = Depends(require_operator_role),
) -> WorkflowResponse:
    try:
        workflow = service.update_workflow(workflow_id, payload, user_id=user.id)
        return WorkflowResponse.model_validate(workflow)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@workflows_router.post(
    "/{workflow_id}/activate",
    response_model=WorkflowResponse,
    summary="Activate workflow definition",
)
def activate_workflow(
    workflow_id: UUID,
    service: WorkflowService = Depends(get_service),
    user: User = Depends(require_operator_role),
) -> WorkflowResponse:
    try:
        workflow = service.activate_workflow(workflow_id, user_id=user.id)
        return WorkflowResponse.model_validate(workflow)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@workflows_router.post(
    "/{workflow_id}/pause",
    response_model=WorkflowResponse,
    summary="Pause active workflow",
)
def pause_workflow(
    workflow_id: UUID,
    service: WorkflowService = Depends(get_service),
    user: User = Depends(require_operator_role),
) -> WorkflowResponse:
    try:
        workflow = service.pause_workflow(workflow_id, user_id=user.id)
        return WorkflowResponse.model_validate(workflow)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@workflows_router.post(
    "/{workflow_id}/run",
    response_model=WorkflowRunDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger a workflow run",
)
def trigger_workflow_run(
    workflow_id: UUID,
    payload: WorkflowRunCreate,
    service: WorkflowService = Depends(get_service),
    user: User = Depends(require_operator_role),
) -> WorkflowRunDetailResponse:
    try:
        run = service.trigger_workflow_run(
            workflow_id=workflow_id,
            input_metadata=payload.input_metadata,
            idempotency_key=payload.idempotency_key,
            trigger_type=WorkflowTriggerType.MANUAL,
            trigger_source=payload.trigger_source or "operator_api",
            actor_user_id=user.id,
            execute_now=True,
        )
        return WorkflowRunDetailResponse.model_validate(run)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@workflows_router.get(
    "/{workflow_id}/triggers",
    response_model=list[WorkflowTriggerResponse],
    summary="List triggers for a workflow",
)
def list_triggers(
    workflow_id: UUID,
    service: WorkflowService = Depends(get_service),
    _user: User = Depends(require_read_role),
) -> list[WorkflowTriggerResponse]:
    try:
        triggers = service.list_triggers(workflow_id)
        return [WorkflowTriggerResponse.model_validate(t) for t in triggers]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@workflows_router.post(
    "/{workflow_id}/triggers",
    response_model=WorkflowTriggerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a trigger definition for a workflow",
)
def create_trigger(
    workflow_id: UUID,
    payload: WorkflowTriggerCreate,
    service: WorkflowService = Depends(get_service),
    _user: User = Depends(require_operator_role),
) -> WorkflowTriggerResponse:
    try:
        trigger = service.create_trigger(workflow_id, payload)
        return WorkflowTriggerResponse.model_validate(trigger)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@workflows_router.get(
    "/{workflow_id}/schedules",
    response_model=list[WorkflowScheduleResponse],
    summary="List schedules for a workflow",
)
def list_schedules(
    workflow_id: UUID,
    service: WorkflowService = Depends(get_service),
    _user: User = Depends(require_read_role),
) -> list[WorkflowScheduleResponse]:
    schedules = service.list_schedules(workflow_id)
    return [WorkflowScheduleResponse.model_validate(s) for s in schedules]


@workflows_router.post(
    "/{workflow_id}/schedules",
    response_model=WorkflowScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a schedule for a workflow",
)
def create_schedule(
    workflow_id: UUID,
    payload: WorkflowScheduleCreate,
    service: WorkflowService = Depends(get_service),
    _user: User = Depends(require_operator_role),
) -> WorkflowScheduleResponse:
    try:
        schedule = service.create_schedule(workflow_id, payload)
        return WorkflowScheduleResponse.model_validate(schedule)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@workflows_router.get(
    "/{workflow_id}/audit",
    response_model=list[WorkflowAuditLogResponse],
    summary="List audit logs for a workflow",
)
def list_workflow_audit(
    workflow_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    service: WorkflowService = Depends(get_service),
    _user: User = Depends(require_read_role),
) -> list[WorkflowAuditLogResponse]:
    logs = service.list_audit_logs(workflow_id=workflow_id, limit=limit)
    return [WorkflowAuditLogResponse.model_validate(log) for log in logs]


# =====================================================================
# Workflow Runs Endpoints (/api/v1/workflow-runs)
# =====================================================================

@workflow_runs_router.get(
    "",
    response_model=list[WorkflowRunResponse],
    summary="List workflow runs",
)
def list_workflow_runs(
    workflow_id: UUID | None = None,
    status: WorkflowRunStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: WorkflowService = Depends(get_service),
    _user: User = Depends(require_read_role),
) -> list[WorkflowRunResponse]:
    runs = service.list_workflow_runs(workflow_id=workflow_id, status=status, limit=limit, offset=offset)
    return [WorkflowRunResponse.model_validate(r) for r in runs]


@workflow_runs_router.get(
    "/{run_id}",
    response_model=WorkflowRunDetailResponse,
    summary="Get workflow run detail with step timeline",
)
def get_workflow_run(
    run_id: UUID,
    service: WorkflowService = Depends(get_service),
    _user: User = Depends(require_read_role),
) -> WorkflowRunDetailResponse:
    try:
        run = service.get_workflow_run(run_id)
        return WorkflowRunDetailResponse.model_validate(run)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@workflow_runs_router.post(
    "/{run_id}/cancel",
    response_model=WorkflowRunDetailResponse,
    summary="Cancel an in-progress or waiting workflow run",
)
def cancel_workflow_run(
    run_id: UUID,
    reason: str | None = Query(default=None),
    service: WorkflowService = Depends(get_service),
    user: User = Depends(require_operator_role),
) -> WorkflowRunDetailResponse:
    try:
        run = service.cancel_workflow_run(run_id, reason=reason, actor_user_id=user.id)
        return WorkflowRunDetailResponse.model_validate(run)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@workflow_runs_router.post(
    "/{run_id}/steps/{step_id}/approve",
    response_model=WorkflowRunDetailResponse,
    summary="Approve a waiting manual approval step",
)
def approve_step(
    run_id: UUID,
    step_id: UUID,
    payload: WorkflowManualApprovalAction | None = None,
    service: WorkflowService = Depends(get_service),
    user: User = Depends(require_operator_role),
) -> WorkflowRunDetailResponse:
    try:
        notes = payload.notes if payload else None
        run = service.approve_step(run_id, step_id, notes=notes, actor_user_id=user.id)
        return WorkflowRunDetailResponse.model_validate(run)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@workflow_runs_router.post(
    "/{run_id}/steps/{step_id}/reject",
    response_model=WorkflowRunDetailResponse,
    summary="Reject a waiting manual approval step",
)
def reject_step(
    run_id: UUID,
    step_id: UUID,
    payload: WorkflowManualApprovalAction | None = None,
    service: WorkflowService = Depends(get_service),
    user: User = Depends(require_operator_role),
) -> WorkflowRunDetailResponse:
    try:
        notes = payload.notes if payload else None
        run = service.reject_step(run_id, step_id, notes=notes, actor_user_id=user.id)
        return WorkflowRunDetailResponse.model_validate(run)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
