"""FastAPI endpoints for GNTV Reliability Operations Subsystem."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.modules.reliability.models import (
    BackupStatus,
    ComponentType,
    IncidentSeverity,
    IncidentState,
    RecoveryRunStatus,
)
from app.modules.reliability.schemas import (
    AlertOccurrenceResponse,
    AlertRuleCreate,
    AlertRuleResponse,
    AlertRuleUpdate,
    ApproveRecoveryRequest,
    BackupRecordCreate,
    BackupRecordResponse,
    DisasterRecoveryPlanCreate,
    DisasterRecoveryPlanResponse,
    DisasterRecoveryPlanUpdate,
    DRReadinessResponse,
    HealthOverviewResponse,
    IncidentAcknowledgeRequest,
    IncidentCloseRequest,
    IncidentCreateRequest,
    IncidentResolveRequest,
    RecoveryRunDetailResponse,
    RecoveryRunResponse,
    ReliabilityIncidentDetailResponse,
    ReliabilityIncidentResponse,
    ReliabilityMetricsResponse,
    ResiliencePolicyCreate,
    ResiliencePolicyResponse,
    ResiliencePolicyUpdate,
    StartRecoveryRequest,
    SystemHealthSnapshotResponse,
    TriggerAlertRequest,
    TriggerHealthCheckRequest,
    VerifyBackupRequest,
    VerifyRecoveryRequest,
)
from app.modules.reliability.service import ReliabilityService

router = APIRouter(prefix="/api/v1/reliability", tags=["Reliability Operations"])

OPERATOR_ROLES = {"admin", "super_admin", "operator"}


def require_operator(user: User = Depends(get_current_user)) -> User:
    role_names = set(user.role_names)
    if not (role_names & OPERATOR_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator or admin role required for reliability operations",
        )
    return user


def get_service(db: Session = Depends(get_db)) -> ReliabilityService:
    return ReliabilityService(db)


def _commit(db: Session) -> None:
    db.commit()


# --- Health Monitoring Endpoints ---
@router.get("/health/overview", response_model=HealthOverviewResponse)
def get_health_overview(
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> HealthOverviewResponse:
    return svc.get_health_overview()


@router.post("/health/check", response_model=SystemHealthSnapshotResponse)
def trigger_health_check(
    payload: TriggerHealthCheckRequest,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> SystemHealthSnapshotResponse:
    snapshot = svc.trigger_health_check(
        component=payload.component,
        correlation_id=payload.correlation_id,
    )
    _commit(db)
    return SystemHealthSnapshotResponse.model_validate(snapshot)


@router.get("/components")
def list_components(
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> list[dict[str, object]]:
    return svc.list_components()


# --- Incidents Endpoints ---
@router.get("/incidents", response_model=list[ReliabilityIncidentResponse])
def list_incidents(
    state: IncidentState | None = None,
    component: ComponentType | None = None,
    severity: IncidentSeverity | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> list[ReliabilityIncidentResponse]:
    items = svc.list_incidents(
        state=state,
        component=component,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    return [ReliabilityIncidentResponse.model_validate(i) for i in items]


@router.post("/incidents", response_model=ReliabilityIncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreateRequest,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    user: User = Depends(require_operator),
) -> ReliabilityIncidentResponse:
    incident = svc.create_incident(payload, actor_user_id=user.id)
    _commit(db)
    return ReliabilityIncidentResponse.model_validate(incident)


@router.get("/incidents/{incident_id}", response_model=ReliabilityIncidentDetailResponse)
def get_incident(
    incident_id: UUID,
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> ReliabilityIncidentDetailResponse:
    try:
        inc = svc.get_incident(incident_id)
        return ReliabilityIncidentDetailResponse.model_validate(inc)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/incidents/{incident_id}/acknowledge", response_model=ReliabilityIncidentResponse)
def acknowledge_incident(
    incident_id: UUID,
    payload: IncidentAcknowledgeRequest,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    user: User = Depends(require_operator),
) -> ReliabilityIncidentResponse:
    try:
        inc = svc.acknowledge_incident(incident_id, actor_user_id=user.id, notes=payload.notes)
        _commit(db)
        return ReliabilityIncidentResponse.model_validate(inc)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/incidents/{incident_id}/resolve", response_model=ReliabilityIncidentResponse)
def resolve_incident(
    incident_id: UUID,
    payload: IncidentResolveRequest,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    user: User = Depends(require_operator),
) -> ReliabilityIncidentResponse:
    try:
        inc = svc.resolve_incident(
            incident_id,
            actor_user_id=user.id,
            resolution_summary=payload.resolution_summary,
        )
        _commit(db)
        return ReliabilityIncidentResponse.model_validate(inc)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/incidents/{incident_id}/close", response_model=ReliabilityIncidentResponse)
def close_incident(
    incident_id: UUID,
    payload: IncidentCloseRequest,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    user: User = Depends(require_operator),
) -> ReliabilityIncidentResponse:
    try:
        inc = svc.close_incident(
            incident_id,
            actor_user_id=user.id,
            recovery_verification_summary=payload.recovery_verification_summary,
        )
        _commit(db)
        return ReliabilityIncidentResponse.model_validate(inc)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# --- Recovery Endpoints ---
@router.get("/recovery/runs", response_model=list[RecoveryRunResponse])
def list_recovery_runs(
    incident_id: UUID | None = None,
    run_status: RecoveryRunStatus | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> list[RecoveryRunResponse]:
    runs = svc.repo.list_recovery_runs(incident_id=incident_id, status=run_status, limit=limit)
    return [RecoveryRunResponse.model_validate(r) for r in runs]


@router.post("/recovery/runs", response_model=RecoveryRunResponse, status_code=status.HTTP_201_CREATED)
def start_recovery_run(
    payload: StartRecoveryRequest,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    user: User = Depends(require_operator),
) -> RecoveryRunResponse:
    try:
        run = svc.start_recovery_run(
            incident_id=payload.incident_id,
            action_type=payload.action_type,
            parameters_json=payload.parameters_json,
            actor_user_id=user.id,
        )
        _commit(db)
        return RecoveryRunResponse.model_validate(run)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/recovery/runs/{run_id}", response_model=RecoveryRunDetailResponse)
def get_recovery_run(
    run_id: UUID,
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> RecoveryRunDetailResponse:
    try:
        run = svc.get_recovery_run(run_id)
        return RecoveryRunDetailResponse.model_validate(run)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/recovery/runs/{run_id}/approve", response_model=RecoveryRunResponse)
def approve_recovery_run(
    run_id: UUID,
    payload: ApproveRecoveryRequest,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    user: User = Depends(require_operator),
) -> RecoveryRunResponse:
    try:
        run = svc.approve_recovery_run(
            run_id=run_id,
            approver_user_id=user.id,
            comments=payload.comments,
        )
        _commit(db)
        return RecoveryRunResponse.model_validate(run)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/recovery/runs/{run_id}/execute", response_model=RecoveryRunResponse)
def execute_recovery_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    user: User = Depends(require_operator),
) -> RecoveryRunResponse:
    try:
        run = svc.execute_recovery_run(run_id=run_id, actor_user_id=user.id)
        _commit(db)
        return RecoveryRunResponse.model_validate(run)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/recovery/runs/{run_id}/verify", response_model=RecoveryRunResponse)
def verify_recovery_run(
    run_id: UUID,
    payload: VerifyRecoveryRequest,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> RecoveryRunResponse:
    try:
        run = svc.verify_recovery(run_id=run_id, verification_details=payload.verification_details)
        _commit(db)
        return RecoveryRunResponse.model_validate(run)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# --- Alerts Endpoints ---
@router.get("/alerts/rules", response_model=list[AlertRuleResponse])
def list_alert_rules(
    is_enabled: bool | None = None,
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> list[AlertRuleResponse]:
    rules = svc.list_alert_rules(is_enabled=is_enabled)
    return [AlertRuleResponse.model_validate(r) for r in rules]


@router.post("/alerts/rules", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
def create_alert_rule(
    payload: AlertRuleCreate,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    user: User = Depends(require_operator),
) -> AlertRuleResponse:
    try:
        rule = svc.create_alert_rule(payload, created_by=user.id)
        _commit(db)
        return AlertRuleResponse.model_validate(rule)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/alerts/rules/{rule_id}", response_model=AlertRuleResponse)
def get_alert_rule(
    rule_id: UUID,
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> AlertRuleResponse:
    try:
        rule = svc.get_alert_rule(rule_id)
        return AlertRuleResponse.model_validate(rule)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/alerts/rules/{rule_id}", response_model=AlertRuleResponse)
def update_alert_rule(
    rule_id: UUID,
    payload: AlertRuleUpdate,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> AlertRuleResponse:
    try:
        rule = svc.update_alert_rule(rule_id, payload)
        _commit(db)
        return AlertRuleResponse.model_validate(rule)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/alerts/rules/{rule_id}")
def delete_alert_rule(
    rule_id: UUID,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> dict[str, str]:
    try:
        svc.delete_alert_rule(rule_id)
        _commit(db)
        return {"status": "deleted"}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/alerts/occurrences", response_model=list[AlertOccurrenceResponse])
def list_alert_occurrences(
    limit: int = Query(default=50, ge=1, le=100),
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> list[AlertOccurrenceResponse]:
    occs = svc.list_alert_occurrences(limit=limit)
    return [AlertOccurrenceResponse.model_validate(o) for o in occs]


@router.post("/alerts/trigger", response_model=AlertOccurrenceResponse | None)
def trigger_alert(
    payload: TriggerAlertRequest,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> AlertOccurrenceResponse | None:
    occ = svc.engine.trigger_alert(
        rule_type=payload.rule_type,
        component=payload.component,
        message=payload.message,
        severity=payload.severity,
        correlation_id=payload.correlation_id,
        payload_json=payload.payload_json,
    )
    _commit(db)
    return AlertOccurrenceResponse.model_validate(occ) if occ else None


# --- Resilience Policies Endpoints ---
@router.get("/policies", response_model=list[ResiliencePolicyResponse])
def list_resilience_policies(
    is_active: bool | None = None,
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> list[ResiliencePolicyResponse]:
    policies = svc.list_resilience_policies(is_active=is_active)
    return [ResiliencePolicyResponse.model_validate(p) for p in policies]


@router.post("/policies", response_model=ResiliencePolicyResponse, status_code=status.HTTP_201_CREATED)
def create_resilience_policy(
    payload: ResiliencePolicyCreate,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    user: User = Depends(require_operator),
) -> ResiliencePolicyResponse:
    try:
        policy = svc.create_resilience_policy(payload, created_by=user.id)
        _commit(db)
        return ResiliencePolicyResponse.model_validate(policy)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/policies/{policy_id}", response_model=ResiliencePolicyResponse)
def get_resilience_policy(
    policy_id: UUID,
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> ResiliencePolicyResponse:
    try:
        p = svc.get_resilience_policy(policy_id)
        return ResiliencePolicyResponse.model_validate(p)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/policies/{policy_id}", response_model=ResiliencePolicyResponse)
def update_resilience_policy(
    policy_id: UUID,
    payload: ResiliencePolicyUpdate,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> ResiliencePolicyResponse:
    try:
        policy = svc.update_resilience_policy(policy_id, payload)
        _commit(db)
        return ResiliencePolicyResponse.model_validate(policy)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/policies/{policy_id}")
def delete_resilience_policy(
    policy_id: UUID,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> dict[str, str]:
    try:
        svc.delete_resilience_policy(policy_id)
        _commit(db)
        return {"status": "deleted"}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# --- Backup Records Endpoints ---
@router.get("/backups", response_model=list[BackupRecordResponse])
def list_backups(
    resource_type: str | None = None,
    status_filter: BackupStatus | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> list[BackupRecordResponse]:
    backups = svc.list_backup_records(resource_type=resource_type, status=status_filter, limit=limit)
    return [BackupRecordResponse.model_validate(b) for b in backups]


@router.post("/backups", response_model=BackupRecordResponse, status_code=status.HTTP_201_CREATED)
def create_backup_record(
    payload: BackupRecordCreate,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> BackupRecordResponse:
    backup = svc.create_backup_record(payload)
    _commit(db)
    return BackupRecordResponse.model_validate(backup)


@router.get("/backups/{backup_id}", response_model=BackupRecordResponse)
def get_backup_record(
    backup_id: UUID,
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> BackupRecordResponse:
    try:
        b = svc.get_backup_record(backup_id)
        return BackupRecordResponse.model_validate(b)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/backups/{backup_id}/verify", response_model=BackupRecordResponse)
def verify_backup_record(
    backup_id: UUID,
    payload: VerifyBackupRequest,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> BackupRecordResponse:
    try:
        b = svc.verify_backup(backup_id, verification_details=payload.verification_details)
        _commit(db)
        return BackupRecordResponse.model_validate(b)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# --- Disaster Recovery Endpoints ---
@router.get("/dr/plans", response_model=list[DisasterRecoveryPlanResponse])
def list_dr_plans(
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> list[DisasterRecoveryPlanResponse]:
    plans = svc.list_dr_plans()
    return [DisasterRecoveryPlanResponse.model_validate(p) for p in plans]


@router.post("/dr/plans", response_model=DisasterRecoveryPlanResponse, status_code=status.HTTP_201_CREATED)
def create_dr_plan(
    payload: DisasterRecoveryPlanCreate,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    user: User = Depends(require_operator),
) -> DisasterRecoveryPlanResponse:
    try:
        plan = svc.create_dr_plan(payload, created_by_user_id=user.id)
        _commit(db)
        return DisasterRecoveryPlanResponse.model_validate(plan)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/dr/plans/{plan_id}", response_model=DisasterRecoveryPlanResponse)
def get_dr_plan(
    plan_id: UUID,
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> DisasterRecoveryPlanResponse:
    try:
        plan = svc.get_dr_plan(plan_id)
        return DisasterRecoveryPlanResponse.model_validate(plan)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/dr/plans/{plan_id}", response_model=DisasterRecoveryPlanResponse)
def update_dr_plan(
    plan_id: UUID,
    payload: DisasterRecoveryPlanUpdate,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> DisasterRecoveryPlanResponse:
    try:
        plan = svc.update_dr_plan(plan_id, payload)
        _commit(db)
        return DisasterRecoveryPlanResponse.model_validate(plan)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/dr/plans/{plan_id}/activate", response_model=DisasterRecoveryPlanResponse)
def activate_dr_plan(
    plan_id: UUID,
    db: Session = Depends(get_db),
    svc: ReliabilityService = Depends(get_service),
    user: User = Depends(require_operator),
) -> DisasterRecoveryPlanResponse:
    try:
        plan = svc.activate_dr_plan(plan_id, approved_by_user_id=user.id)
        _commit(db)
        return DisasterRecoveryPlanResponse.model_validate(plan)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/dr/readiness", response_model=DRReadinessResponse)
def get_dr_readiness(
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> DRReadinessResponse:
    return svc.evaluate_dr_readiness()


# --- Metrics Endpoints ---
@router.get("/metrics", response_model=ReliabilityMetricsResponse)
def get_metrics(
    svc: ReliabilityService = Depends(get_service),
    _user: User = Depends(require_operator),
) -> ReliabilityMetricsResponse:
    return svc.get_metrics()
