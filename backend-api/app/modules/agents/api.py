"""Operator APIs for the AI Agent Control Plane."""

from __future__ import annotations

from typing import Any, Callable, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.agents.models import (
    AgentAuditLog,
    AgentDefinition,
    AgentRun,
    AgentStatus,
    ApprovalPolicy,
    ModelPolicy,
    ToolPolicy,
)
from app.modules.agents.schemas import (
    AgentCreate,
    AgentResponse,
    AgentRunCreate,
    AgentRunResponse,
    AgentUpdate,
    ApprovalDecision,
    ApprovalPolicyCreate,
    ApprovalPolicyResponse,
    ApprovalResponse,
    InstructionCreate,
    ModelPolicyCreate,
    ModelPolicyResponse,
    ToolCallResponse,
    ToolPolicyCreate,
    ToolPolicyResponse,
)
from app.modules.agents.service import AgentControlService

agents_router = APIRouter(prefix="/api/v1/agents", tags=["AI Agents"])
runs_router = APIRouter(prefix="/api/v1/agent-runs", tags=["AI Agent Runs"])
approvals_router = APIRouter(
    prefix="/api/v1/agent-approvals", tags=["AI Agent Approvals"]
)
model_policies_router = APIRouter(
    prefix="/api/v1/agent-model-policies", tags=["AI Agent Policies"]
)
tool_policies_router = APIRouter(
    prefix="/api/v1/agent-tool-policies", tags=["AI Agent Policies"]
)
approval_policies_router = APIRouter(
    prefix="/api/v1/agent-approval-policies", tags=["AI Agent Policies"]
)
metrics_router = APIRouter(prefix="/api/v1/agent-metrics", tags=["AI Agent Metrics"])

OPERATORS = {"admin", "super_admin", "operator"}
INVOKERS = OPERATORS | {"editor", "editorial", "producer"}
READERS = INVOKERS | {"viewer"}


def service(db: Session = Depends(get_db)) -> AgentControlService:
    return AgentControlService(db)


def _roles(user: User) -> set[str]:
    return set(user.role_names)


def operator(user: User = Depends(get_current_user)) -> User:
    if not (_roles(user) & OPERATORS):
        raise HTTPException(status_code=403, detail="Operator or admin role required")
    return user


def invoker(user: User = Depends(get_current_user)) -> User:
    if not (_roles(user) & INVOKERS):
        raise HTTPException(status_code=403, detail="Agent invocation is not permitted")
    return user


def reader(user: User = Depends(get_current_user)) -> User:
    if not (_roles(user) & READERS):
        raise HTTPException(status_code=403, detail="Agent control plane access denied")
    return user


def _commit(db: Session) -> None:
    db.commit()


@agents_router.get("", response_model=list[AgentResponse])
def list_agents(
    svc: AgentControlService = Depends(service), _user: User = Depends(reader)
) -> list[AgentDefinition]:
    return svc.agents()


@agents_router.post("", response_model=AgentResponse, status_code=201)
def create_agent(
    payload: AgentCreate, db: Session = Depends(get_db), user: User = Depends(operator)
) -> AgentDefinition:
    try:
        result = AgentControlService(db).create_agent(payload, user.id)
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@agents_router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(
    agent_id: UUID,
    svc: AgentControlService = Depends(service),
    _user: User = Depends(reader),
) -> AgentDefinition:
    try:
        return svc.agent(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@agents_router.patch("/{agent_id}", response_model=AgentResponse)
def patch_agent(
    agent_id: UUID,
    payload: AgentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
) -> AgentDefinition:
    try:
        result = AgentControlService(db).update_agent(agent_id, payload, user.id)
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _transition(
    agent_id: UUID, target: AgentStatus, db: Session, user: User
) -> AgentDefinition:
    try:
        result = AgentControlService(db).transition(agent_id, target, user.id)
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@agents_router.post("/{agent_id}/activate", response_model=AgentResponse)
def activate_agent(
    agent_id: UUID, db: Session = Depends(get_db), user: User = Depends(operator)
) -> AgentDefinition:
    return _transition(agent_id, AgentStatus.ACTIVE, db, user)


@agents_router.post("/{agent_id}/pause", response_model=AgentResponse)
def pause_agent(
    agent_id: UUID, db: Session = Depends(get_db), user: User = Depends(operator)
) -> AgentDefinition:
    return _transition(agent_id, AgentStatus.PAUSED, db, user)


@agents_router.post("/{agent_id}/archive", response_model=AgentResponse)
def archive_agent(
    agent_id: UUID, db: Session = Depends(get_db), user: User = Depends(operator)
) -> AgentDefinition:
    return _transition(agent_id, AgentStatus.ARCHIVED, db, user)


@agents_router.post("/{agent_id}/instructions", status_code=201)
def create_instruction(
    agent_id: UUID,
    payload: InstructionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
) -> dict[str, object]:
    try:
        row = AgentControlService(db).create_instruction(agent_id, payload, user.id)
        _commit(db)
        return {"id": str(row.id), "version": row.version, "active": row.is_active}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@agents_router.post(
    "/{agent_id}/instructions/{version}/activate", response_model=AgentResponse
)
def activate_instruction(
    agent_id: UUID,
    version: int,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
) -> AgentDefinition:
    try:
        result = AgentControlService(db).activate_instruction(
            agent_id, version, user.id
        )
        _commit(db)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@agents_router.post(
    "/{agent_id}/runs", response_model=AgentRunResponse, status_code=201
)
def create_run(
    agent_id: UUID,
    payload: AgentRunCreate,
    db: Session = Depends(get_db),
    user: User = Depends(invoker),
) -> AgentRun:
    try:
        result = AgentControlService(db).create_run(agent_id, payload, user.id)
        _commit(db)
        return AgentControlService(db).run(result.id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@runs_router.get("", response_model=list[AgentRunResponse])
def list_runs(
    svc: AgentControlService = Depends(service), _user: User = Depends(reader)
) -> list[AgentRun]:
    return svc.runs()


@runs_router.get("/{run_id}", response_model=AgentRunResponse)
def get_run(
    run_id: UUID,
    svc: AgentControlService = Depends(service),
    _user: User = Depends(reader),
) -> AgentRun:
    try:
        return svc.run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@runs_router.post("/{run_id}/cancel", response_model=AgentRunResponse)
def cancel_run(
    run_id: UUID, db: Session = Depends(get_db), user: User = Depends(operator)
) -> AgentRun:
    try:
        result = AgentControlService(db).cancel(run_id, user.id)
        _commit(db)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@runs_router.post("/{run_id}/retry", response_model=AgentRunResponse, status_code=201)
def retry_run(
    run_id: UUID, db: Session = Depends(get_db), user: User = Depends(operator)
) -> AgentRun:
    try:
        result = AgentControlService(db).retry(run_id, user.id)
        _commit(db)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@runs_router.get("/{run_id}/tool-calls", response_model=list[ToolCallResponse])
def tool_calls(
    run_id: UUID,
    svc: AgentControlService = Depends(service),
    _user: User = Depends(reader),
) -> list[Any]:
    try:
        return svc.run(run_id).tool_calls
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@approvals_router.get("", response_model=list[ApprovalResponse])
def list_approvals(
    svc: AgentControlService = Depends(service), _user: User = Depends(reader)
) -> list[Any]:
    return svc.approvals()


def _decision(
    approval_id: UUID,
    payload: ApprovalDecision,
    approved: bool,
    db: Session,
    user: User,
) -> AgentRun:
    try:
        result = AgentControlService(db).decide_approval(
            approval_id, approved, user.id, payload.reason
        )
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@approvals_router.post("/{approval_id}/approve", response_model=AgentRunResponse)
def approve(
    approval_id: UUID,
    payload: ApprovalDecision,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
) -> AgentRun:
    return _decision(approval_id, payload, True, db, user)


@approvals_router.post("/{approval_id}/reject", response_model=AgentRunResponse)
def reject(
    approval_id: UUID,
    payload: ApprovalDecision,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
) -> AgentRun:
    return _decision(approval_id, payload, False, db, user)


def _policy_create(
    payload: Any, model: Callable[[Any, int | None], Any], db: Session, user: User
) -> Any:
    try:
        result = model(payload, user.id)
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@model_policies_router.get("", response_model=list[ModelPolicyResponse])
def model_policies(
    svc: AgentControlService = Depends(service), _user: User = Depends(reader)
) -> list[Any]:
    return svc.list_policies(ModelPolicy)


@model_policies_router.post("", response_model=ModelPolicyResponse, status_code=201)
def create_model_policy(
    payload: ModelPolicyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
) -> ModelPolicy:
    return cast(
        ModelPolicy,
        _policy_create(payload, AgentControlService(db).create_model_policy, db, user),
    )


@tool_policies_router.get("", response_model=list[ToolPolicyResponse])
def tool_policies(
    svc: AgentControlService = Depends(service), _user: User = Depends(operator)
) -> list[Any]:
    return svc.list_policies(ToolPolicy)


@tool_policies_router.post("", response_model=ToolPolicyResponse, status_code=201)
def create_tool_policy(
    payload: ToolPolicyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
) -> ToolPolicy:
    return cast(
        ToolPolicy,
        _policy_create(payload, AgentControlService(db).create_tool_policy, db, user),
    )


@approval_policies_router.get("", response_model=list[ApprovalPolicyResponse])
def approval_policies(
    svc: AgentControlService = Depends(service), _user: User = Depends(operator)
) -> list[Any]:
    return svc.list_policies(ApprovalPolicy)


@approval_policies_router.post(
    "", response_model=ApprovalPolicyResponse, status_code=201
)
def create_approval_policy(
    payload: ApprovalPolicyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
) -> ApprovalPolicy:
    return cast(
        ApprovalPolicy,
        _policy_create(
            payload, AgentControlService(db).create_approval_policy, db, user
        ),
    )


@metrics_router.get("")
def metrics(
    svc: AgentControlService = Depends(service), _user: User = Depends(reader)
) -> dict[str, Any]:
    return svc.metrics()


@agents_router.get("/{agent_id}/audit")
def audit(
    agent_id: UUID, db: Session = Depends(get_db), _user: User = Depends(operator)
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(AgentAuditLog)
        .where(AgentAuditLog.agent_id == agent_id)
        .order_by(AgentAuditLog.created_at.desc())
    ).all()
    return [
        {
            "action": row.action.value,
            "created_at": row.created_at,
            "correlation_id": row.correlation_id,
            "metadata": row.metadata_json,
        }
        for row in rows
    ]
