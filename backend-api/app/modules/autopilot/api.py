"""Operator APIs for GNTV Autopilot production and publishing."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.autopilot.models import (
    AutopilotApproval,
    AutopilotAsset,
    AutopilotBrief,
    AutopilotProduction,
    AutopilotPublishingAttempt,
    AutopilotPublishingDestination,
    AutopilotPublishingPlan,
    AutopilotScriptVersion,
    ProductionStatus,
)
from app.modules.autopilot.schemas import (
    ApprovalDecision,
    ApprovalRequestCreate,
    ApprovalResponse,
    AssetCreate,
    AssetResponse,
    BriefResponse,
    BriefUpsert,
    DestinationCreate,
    DestinationResponse,
    MetricsResponse,
    ProductionCreate,
    ProductionDetailResponse,
    ProductionPlanCreate,
    ProductionResponse,
    ProductionUpdate,
    PublishingAttemptResponse,
    PublishingPlanCreate,
    PublishingPlanResponse,
    PublishRequest,
    ScriptCreate,
    ScriptResponse,
    StageRequest,
)
from app.modules.autopilot.service import AutopilotService

router = APIRouter(prefix="/api/v1/autopilot", tags=["Autopilot"])

OPERATORS = {"admin", "super_admin", "operator"}
EDITORS = OPERATORS | {"editor", "editorial", "producer"}
READERS = EDITORS | {"viewer"}


def _roles(user: User) -> set[str]:
    return set(user.role_names)


def operator(user: User = Depends(get_current_user)) -> User:
    if not (_roles(user) & OPERATORS):
        raise HTTPException(status_code=403, detail="Operator or admin role required")
    return user


def editor(user: User = Depends(get_current_user)) -> User:
    if not (_roles(user) & EDITORS):
        raise HTTPException(status_code=403, detail="Editorial access required")
    return user


def reader(user: User = Depends(get_current_user)) -> User:
    if not (_roles(user) & READERS):
        raise HTTPException(status_code=403, detail="Autopilot access denied")
    return user


def service(db: Session = Depends(get_db)) -> AutopilotService:
    return AutopilotService(db)


def _commit(db: Session) -> None:
    db.commit()


@router.get("/productions", response_model=list[ProductionResponse])
def list_productions(
    status: ProductionStatus | None = None,
    svc: AutopilotService = Depends(service),
    _user: User = Depends(reader),
) -> list[AutopilotProduction]:
    return svc.list_productions(status)


@router.post("/productions", response_model=ProductionResponse, status_code=201)
def create_production(
    payload: ProductionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(editor),
) -> AutopilotProduction:
    try:
        result = AutopilotService(db).create_production(payload, user.id)
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/productions/{production_id}", response_model=ProductionDetailResponse)
def get_production(
    production_id: UUID,
    svc: AutopilotService = Depends(service),
    _user: User = Depends(reader),
) -> AutopilotProduction:
    try:
        return svc.get_production(production_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/productions/{production_id}", response_model=ProductionResponse)
def patch_production(
    production_id: UUID,
    payload: ProductionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(editor),
) -> AutopilotProduction:
    try:
        result = AutopilotService(db).update_production(production_id, payload, user.id)
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/productions/{production_id}/brief", response_model=BriefResponse)
def upsert_brief(
    production_id: UUID,
    payload: BriefUpsert,
    db: Session = Depends(get_db),
    _user: User = Depends(editor),
) -> AutopilotBrief:
    try:
        result = AutopilotService(db).upsert_brief(production_id, payload)
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/productions/{production_id}/start-research")
def start_research(
    production_id: UUID,
    payload: StageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(editor),
) -> dict[str, str]:
    try:
        result = AutopilotService(db).start_research(production_id, payload, user.id)
        _commit(db)
        return {"research_task_id": str(result.id), "status": result.status.value}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/productions/{production_id}/generate-script", response_model=ScriptResponse)
def generate_script(
    production_id: UUID,
    payload: StageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(editor),
) -> AutopilotScriptVersion:
    try:
        result = AutopilotService(db).generate_script(production_id, payload, user.id)
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/productions/{production_id}/scripts", response_model=ScriptResponse)
def create_script(
    production_id: UUID,
    payload: ScriptCreate,
    db: Session = Depends(get_db),
    user: User = Depends(editor),
) -> AutopilotScriptVersion:
    try:
        result = AutopilotService(db).create_script(production_id, payload, user.id)
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/productions/{production_id}/scripts", response_model=list[ScriptResponse])
def list_scripts(
    production_id: UUID,
    svc: AutopilotService = Depends(service),
    _user: User = Depends(reader),
) -> list[AutopilotScriptVersion]:
    return svc.get_production(production_id).scripts


@router.post("/productions/{production_id}/generate-production-plan")
def generate_production_plan(
    production_id: UUID,
    payload: ProductionPlanCreate,
    db: Session = Depends(get_db),
    user: User = Depends(editor),
) -> dict[str, str]:
    try:
        result = AutopilotService(db).create_production_plan(
            production_id, payload, user.id
        )
        _commit(db)
        return {"production_plan_id": str(result.id)}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/productions/{production_id}/assets", response_model=AssetResponse)
def add_asset(
    production_id: UUID,
    payload: AssetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(editor),
) -> AutopilotAsset:
    try:
        result = AutopilotService(db).add_asset(production_id, payload, user.id)
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/productions/{production_id}/assets", response_model=list[AssetResponse])
def list_assets(
    production_id: UUID,
    svc: AutopilotService = Depends(service),
    _user: User = Depends(reader),
) -> list[AutopilotAsset]:
    return svc.get_production(production_id).assets


@router.post("/productions/{production_id}/request-approval", response_model=ApprovalResponse)
def request_approval(
    production_id: UUID,
    payload: ApprovalRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(editor),
) -> AutopilotApproval:
    try:
        result = AutopilotService(db).request_approval(production_id, payload, user.id)
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/approvals", response_model=list[ApprovalResponse])
def list_approvals(
    svc: AutopilotService = Depends(service), _user: User = Depends(reader)
) -> list[AutopilotApproval]:
    return svc.list_approvals()


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalResponse)
def approve(
    approval_id: UUID,
    payload: ApprovalDecision,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
) -> AutopilotApproval:
    try:
        result = AutopilotService(db).decide_approval(
            approval_id, True, payload, user.id
        )
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalResponse)
def reject(
    approval_id: UUID,
    payload: ApprovalDecision,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
) -> AutopilotApproval:
    try:
        result = AutopilotService(db).decide_approval(
            approval_id, False, payload, user.id
        )
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/destinations", response_model=list[DestinationResponse])
def destinations(
    svc: AutopilotService = Depends(service), _user: User = Depends(reader)
) -> list[AutopilotPublishingDestination]:
    return svc.list_destinations()


@router.post("/destinations", response_model=DestinationResponse, status_code=201)
def create_destination(
    payload: DestinationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
) -> AutopilotPublishingDestination:
    result = AutopilotService(db).create_destination(payload, user.id)
    _commit(db)
    return result


@router.get(
    "/productions/{production_id}/publishing-plan",
    response_model=list[PublishingPlanResponse],
)
def publishing_plan(
    production_id: UUID,
    svc: AutopilotService = Depends(service),
    _user: User = Depends(reader),
) -> list[AutopilotPublishingPlan]:
    return svc.get_production(production_id).publishing_plans


@router.post(
    "/productions/{production_id}/publishing-plan",
    response_model=PublishingPlanResponse,
    status_code=201,
)
def create_publishing_plan(
    production_id: UUID,
    payload: PublishingPlanCreate,
    db: Session = Depends(get_db),
    user: User = Depends(editor),
) -> AutopilotPublishingPlan:
    try:
        result = AutopilotService(db).create_publishing_plan(
            production_id, payload, user.id
        )
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/productions/{production_id}/publish",
    response_model=list[PublishingAttemptResponse],
)
def publish(
    production_id: UUID,
    payload: PublishRequest,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
) -> list[AutopilotPublishingAttempt]:
    try:
        result = AutopilotService(db).publish(production_id, payload, user.id)
        _commit(db)
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/publications", response_model=list[PublishingAttemptResponse])
def publications(
    svc: AutopilotService = Depends(service), _user: User = Depends(reader)
) -> list[AutopilotPublishingAttempt]:
    return svc.list_attempts()


@router.post("/productions/{production_id}/cancel", response_model=ProductionResponse)
def cancel(
    production_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(operator),
) -> AutopilotProduction:
    result = AutopilotService(db).cancel_production(production_id, user.id)
    _commit(db)
    return result


@router.get("/metrics", response_model=MetricsResponse)
def metrics(
    svc: AutopilotService = Depends(service), _user: User = Depends(reader)
) -> dict[str, object]:
    return svc.metrics()
