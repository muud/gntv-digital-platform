"""Sprint 8.6 Reliability, Monitoring, Recovery & Disaster Recovery acceptance tests."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.user import Role, User
from app.modules.events.models import DomainEvent
from app.modules.jobs.models import DurableJob, JobDeadLetter, JobDeadLetterStatus, JobStatus
from app.modules.jobs.registry import SafeJobType, default_job_registry
from app.modules.reliability.models import (
    BackupStatus,
    BackupType,
    ComponentType,
    DRReadinessStatus,
    HealthStatus,
    IncidentSeverity,
    IncidentState,
    RecoveryActionType,
    RecoveryRunStatus,
)
from app.modules.reliability.schemas import (
    AlertRuleCreate,
    AlertRuleUpdate,
    BackupRecordCreate,
    DisasterRecoveryPlanCreate,
    DisasterRecoveryPlanUpdate,
    IncidentCreateRequest,
    ResiliencePolicyCreate,
    ResiliencePolicyUpdate,
)
from app.modules.reliability.service import ReliabilityService
from app.modules.workflows.models import WorkflowRun, WorkflowRunStatus, WorkflowTriggerType
from app.utils.jwt import create_access_token


@pytest.fixture()
def runtime() -> Iterator[tuple[Session, TestClient]]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    def override() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override
    try:
        yield db, TestClient(app)
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def make_user(db: Session, role_name: str) -> User:
    role = db.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        role = Role(name=role_name, description=role_name)
        db.add(role)
    user = User(
        email=f"{role_name}-{uuid4().hex}@gntv.test",
        hashed_password="hash",
        is_active=True,
        is_verified=True,
    )
    user.roles.append(role)
    db.add(user)
    db.commit()
    return user


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


# ==============================================================================
# 1. Health Monitoring & Aggregation Tests
# ==============================================================================
def test_component_health_states_and_aggregation(runtime: tuple[Session, TestClient]) -> None:
    db, _ = runtime
    svc = ReliabilityService(db)

    # Trigger health check across all components
    snapshot = svc.trigger_health_check()
    assert snapshot.overall_status in {HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY}
    assert snapshot.health_score >= 0.0
    assert snapshot.healthy_count + snapshot.degraded_count + snapshot.unhealthy_count + snapshot.unknown_count == len(ComponentType)

    # Check component listings
    components = svc.list_components()
    assert len(components) == len(ComponentType)
    comp_names = {c["component"] for c in components}
    for comp in ComponentType:
        assert comp.value in comp_names

    # Specific component check
    single_snapshot = svc.trigger_health_check(component=ComponentType.DATABASE)
    assert len(single_snapshot.checks) == 1
    assert single_snapshot.checks[0].component == ComponentType.DATABASE
    assert single_snapshot.checks[0].status == HealthStatus.HEALTHY

    # Verify domain event was emitted
    domain_event = db.scalars(
        select(DomainEvent).where(DomainEvent.event_type == "reliability.health.updated")
    ).first()
    assert domain_event is not None
    assert domain_event.source == "reliability"


def test_health_evaluation_degraded_conditions(runtime: tuple[Session, TestClient]) -> None:
    db, _ = runtime
    svc = ReliabilityService(db)

    # Insert > 50 failed workflow runs to trigger degraded state for WORKFLOW_ENGINE
    for _ in range(55):
        wf_run = WorkflowRun(
            workflow_id=uuid4(),
            workflow_version=1,
            trigger_type=WorkflowTriggerType.MANUAL,
            status=WorkflowRunStatus.FAILED,
            idempotency_key=f"wf-key-{uuid4()}",
            correlation_id=f"corr-{uuid4()}",
            input_metadata_json={},
        )
        db.add(wf_run)
    db.commit()

    # Evaluate health
    snapshot = svc.trigger_health_check(component=ComponentType.WORKFLOW_ENGINE)
    assert snapshot.overall_status == HealthStatus.DEGRADED
    assert snapshot.degraded_count == 1

    # Should automatically create incident for WORKFLOW_ENGINE
    incidents = svc.list_incidents(component=ComponentType.WORKFLOW_ENGINE)
    assert len(incidents) >= 1
    assert incidents[0].state == IncidentState.DETECTED
    assert incidents[0].severity == IncidentSeverity.MAJOR

    # Verify domain event for component degradation
    degraded_event = db.scalars(
        select(DomainEvent).where(DomainEvent.event_type == "reliability.component.degraded")
    ).first()
    assert degraded_event is not None
    assert degraded_event.payload_json["component"] == ComponentType.WORKFLOW_ENGINE.value


# ==============================================================================
# 2. Incident Creation, Deduplication & State Transitions
# ==============================================================================
def test_incident_lifecycle_and_state_transitions(runtime: tuple[Session, TestClient]) -> None:
    db, _ = runtime
    svc = ReliabilityService(db)
    operator = make_user(db, "operator")

    # Create incident
    req = IncidentCreateRequest(
        title="Database Latency Spike",
        description="P99 query latency exceeded 1500ms on primary read replica",
        component=ComponentType.DATABASE,
        severity=IncidentSeverity.MAJOR,
        failure_reason="Connection pool exhaustion",
        correlation_id=f"corr-{uuid4()}",
    )
    incident = svc.create_incident(req, actor_user_id=operator.id)
    assert incident.state == IncidentState.DETECTED
    assert incident.title == "Database Latency Spike"
    assert incident.retry_count == 0

    # Transition: DETECTED -> ACKNOWLEDGED
    acked = svc.acknowledge_incident(incident.id, actor_user_id=operator.id, notes="Investigating pool size")
    assert acked.state == IncidentState.ACKNOWLEDGED
    assert acked.acknowledged_by_user_id == operator.id
    assert acked.acknowledged_at is not None

    # Invalid transition: ACKNOWLEDGED -> CLOSED (must go through RESOLVED with verification)
    with pytest.raises(ValueError, match="Invalid incident state transition"):
        svc.close_incident(incident.id, actor_user_id=operator.id, recovery_verification_summary="Should fail")

    # Transition to RECOVERING via starting a recovery run
    run = svc.start_recovery_run(
        incident_id=incident.id,
        action_type=RecoveryActionType.VERIFY_COMPONENT_HEALTH,
        parameters_json={"component": "DATABASE"},
        actor_user_id=operator.id,
    )
    assert run.status == RecoveryRunStatus.SUCCEEDED
    assert run.result_json.get("status") == "HEALTHY"

    # Incident transitioned to MONITORING after recovery run completed
    reloaded = svc.get_incident(incident.id)
    assert reloaded.state == IncidentState.MONITORING

    # Transition: MONITORING -> RESOLVED
    resolved = svc.resolve_incident(
        incident.id,
        actor_user_id=operator.id,
        resolution_summary="Connection pool max size increased and verified stable",
    )
    assert resolved.state == IncidentState.RESOLVED
    assert resolved.resolved_at is not None
    assert resolved.resolution_summary is not None

    # Transition: RESOLVED -> CLOSED
    closed = svc.close_incident(
        incident.id,
        actor_user_id=operator.id,
        recovery_verification_summary="Post-incident monitoring clean for 15 minutes",
    )
    assert closed.state == IncidentState.CLOSED
    assert closed.closed_at is not None
    assert closed.recovery_verification_summary is not None

    # Verify timeline events
    detail = svc.get_incident(incident.id)
    event_types = [e.event_type for e in detail.events]
    assert "INCIDENT_CREATED" in event_types
    assert "STATE_CHANGED" in event_types
    assert "RECOVERY_INITIATED" in event_types


def test_incident_deduplication_within_window(runtime: tuple[Session, TestClient]) -> None:
    db, _ = runtime
    svc = ReliabilityService(db)

    # Set policy with 600s dedup window
    policy_req = ResiliencePolicyCreate(
        name="api_dedup_policy",
        component=ComponentType.API.value,
        incident_deduplication_window_seconds=600,
    )
    svc.create_resilience_policy(policy_req)

    # First degraded condition triggers incident
    svc.engine._handle_unhealthy_condition(
        component=ComponentType.API,
        status=HealthStatus.DEGRADED,
        reason="API 504 timeouts",
    )
    incidents_1 = svc.list_incidents(component=ComponentType.API)
    assert len(incidents_1) == 1
    assert incidents_1[0].retry_count == 0

    # Second degraded condition within window is deduplicated
    svc.engine._handle_unhealthy_condition(
        component=ComponentType.API,
        status=HealthStatus.DEGRADED,
        reason="API 504 timeouts recurred",
    )
    incidents_2 = svc.list_incidents(component=ComponentType.API)
    assert len(incidents_2) == 1  # No new incident created
    assert incidents_2[0].retry_count == 1


# ==============================================================================
# 3. Alert Rules, Occurrences & Cooldown
# ==============================================================================
def test_alert_rules_cooldown_and_deduplication(runtime: tuple[Session, TestClient]) -> None:
    db, _ = runtime
    svc = ReliabilityService(db)
    operator = make_user(db, "operator")

    rule_req = AlertRuleCreate(
        name="DB_HIGH_LATENCY",
        rule_type="DATABASE_LATENCY",
        severity=IncidentSeverity.CRITICAL,
        component="DATABASE",
        threshold_value=500.0,
        cooldown_seconds=300,
    )
    rule = svc.create_alert_rule(rule_req, created_by=operator.id)
    assert rule.name == "DB_HIGH_LATENCY"
    assert rule.is_enabled is True

    # Trigger alert 1 -> Delivered
    occ1 = svc.engine.trigger_alert(
        rule_type="DATABASE_LATENCY",
        component="DATABASE",
        message="Database query latency 850ms exceeds threshold",
        severity=IncidentSeverity.CRITICAL,
    )
    assert occ1 is not None
    assert occ1.component == "DATABASE"

    # Trigger alert 2 immediately -> Suppressed by cooldown
    occ2 = svc.engine.trigger_alert(
        rule_type="DATABASE_LATENCY",
        component="DATABASE",
        message="Database query latency 890ms exceeds threshold",
        severity=IncidentSeverity.CRITICAL,
    )
    assert occ2 is None  # Suppressed

    # Update rule
    updated = svc.update_alert_rule(rule.id, AlertRuleUpdate(cooldown_seconds=120, is_enabled=False))
    assert updated.cooldown_seconds == 120
    assert updated.is_enabled is False

    # List occurrences
    occs = svc.list_alert_occurrences()
    assert len(occs) >= 1


# ==============================================================================
# 4. Recovery Orchestration & Human Approval Gate
# ==============================================================================
def test_recovery_approval_gate_for_critical_actions(runtime: tuple[Session, TestClient]) -> None:
    db, _ = runtime
    svc = ReliabilityService(db)
    operator = make_user(db, "operator")

    incident = svc.create_incident(
        IncidentCreateRequest(
            title="Service Degradation",
            description="High error rate",
            component=ComponentType.API,
            severity=IncidentSeverity.MAJOR,
        ),
        actor_user_id=operator.id,
    )

    # MARK_COMPONENT_DEGRADED is in CRITICAL_RECOVERY_ACTIONS -> requires approval
    run = svc.start_recovery_run(
        incident_id=incident.id,
        action_type=RecoveryActionType.MARK_COMPONENT_DEGRADED,
        parameters_json={"component": "API"},
        actor_user_id=operator.id,
    )
    assert run.requires_approval is True
    assert run.status == RecoveryRunStatus.PENDING_APPROVAL
    assert run.approved_at is None

    # Operator approves the recovery run -> executes
    approved = svc.approve_recovery_run(
        run_id=run.id,
        approver_user_id=operator.id,
        comments="Approved by on-call engineer",
    )
    assert approved.status == RecoveryRunStatus.SUCCEEDED
    assert approved.approved_by_user_id == operator.id
    assert approved.approved_at is not None
    assert approved.result_json.get("status") == "marked_degraded"

    # Verify recovery verification
    verified = svc.verify_recovery(run.id, verification_details="Component state validated manually")
    assert verified.verification_status == "VERIFIED"


def test_recovery_allowlisted_actions_and_failure_handling(runtime: tuple[Session, TestClient]) -> None:
    db, _ = runtime
    svc = ReliabilityService(db)
    operator = make_user(db, "operator")

    incident = svc.create_incident(
        IncidentCreateRequest(
            title="Durable Job Failure",
            description="Job execution halted",
            component=ComponentType.JOB_QUEUE,
            severity=IncidentSeverity.MINOR,
        ),
        actor_user_id=operator.id,
    )

    # 1. RETRY_FAILED_JOB
    job = DurableJob(
        job_type=SafeJobType.WORKFLOW_RUN,
        queue_name="default",
        status=JobStatus.FAILED,
        correlation_id=f"corr-{uuid4()}",
    )
    db.add(job)
    db.commit()

    run_job = svc.start_recovery_run(
        incident_id=incident.id,
        action_type=RecoveryActionType.RETRY_FAILED_JOB,
        parameters_json={"job_id": str(job.id)},
        actor_user_id=operator.id,
    )
    assert run_job.status == RecoveryRunStatus.SUCCEEDED
    assert run_job.result_json.get("status") == "requeued"
    reloaded_job = db.get(DurableJob, job.id)
    assert reloaded_job.status == JobStatus.QUEUED

    # 2. REQUEUE_DLQ_JOB
    job2 = DurableJob(
        job_type=SafeJobType.WORKFLOW_RUN,
        queue_name="default",
        status=JobStatus.FAILED,
        payload_json={"workflow_id": str(uuid4())},
        idempotency_key=f"dlq-job-{uuid4()}",
        correlation_id=f"corr-{uuid4()}",
    )
    db.add(job2)
    db.flush()

    dlq = JobDeadLetter(
        job_id=job2.id,
        status=JobDeadLetterStatus.OPEN,
        reason="timeout",
        retry_count=3,
    )
    db.add(dlq)
    db.commit()

    run_dlq = svc.start_recovery_run(
        incident_id=incident.id,
        action_type=RecoveryActionType.REQUEUE_DLQ_JOB,
        parameters_json={"dlq_id": str(dlq.id)},
        actor_user_id=operator.id,
    )
    assert run_dlq.status == RecoveryRunStatus.SUCCEEDED
    assert run_dlq.result_json.get("status") == "requeued"

    # 3. ESCALATE_INCIDENT (Critical action approved and executed)
    run_esc = svc.start_recovery_run(
        incident_id=incident.id,
        action_type=RecoveryActionType.ESCALATE_INCIDENT,
        parameters_json={"incident_id": str(incident.id)},
        actor_user_id=operator.id,
    )
    svc.approve_recovery_run(run_esc.id, approver_user_id=operator.id)
    reloaded_inc = svc.get_incident(incident.id)
    assert reloaded_inc.severity == IncidentSeverity.CRITICAL


# ==============================================================================
# 5. Backup Records & Disaster Recovery Readiness
# ==============================================================================
def test_backup_metadata_and_verification(runtime: tuple[Session, TestClient]) -> None:
    db, _ = runtime
    svc = ReliabilityService(db)

    # Create backup record
    create_req = BackupRecordCreate(
        resource_type="DATABASE",
        logical_identifier="gntv_media_hub_primary",
        provider="MOCK_LOCAL",
        backup_type=BackupType.SNAPSHOT,
        retention_days=30,
    )
    backup = svc.create_backup_record(create_req)
    assert backup.status == BackupStatus.COMPLETED
    assert backup.resource_type == "DATABASE"

    # Verify backup record
    verified = svc.verify_backup(backup.id, verification_details="Checksum and size matched")
    assert verified.status == BackupStatus.VERIFIED
    assert verified.verification_result == "PASSED"
    assert verified.checksum is not None
    assert verified.size_bytes is not None


def test_dr_plans_and_readiness_evaluation(runtime: tuple[Session, TestClient]) -> None:
    db, _ = runtime
    svc = ReliabilityService(db)
    operator = make_user(db, "operator")

    # Create DR plan
    plan_req = DisasterRecoveryPlanCreate(
        plan_version="v2026.1",
        name="Global DR Regional Failover Plan",
        description="Procedures for primary database and streaming node recovery",
        rto_target_minutes=30,
        rpo_target_minutes=15,
        activation_criteria="Total regional outage exceeding 10 minutes",
        recovery_priorities_json=["DATABASE", "API", "WORKFLOW_ENGINE", "JOB_QUEUE"],
        verification_checklist_json=["DB replica synced", "Workers reporting heartbeat"],
    )
    plan = svc.create_dr_plan(plan_req, created_by_user_id=operator.id)
    assert plan.is_active is False

    # Activate plan
    activated = svc.activate_dr_plan(plan.id, approved_by_user_id=operator.id)
    assert activated.is_active is True
    assert activated.approved_by_user_id == operator.id

    # Create and verify fresh DB backup
    backup = svc.create_backup_record(
        BackupRecordCreate(
            resource_type="DATABASE",
            logical_identifier="db_main",
            retention_days=14,
        )
    )
    svc.verify_backup(backup.id)

    # Evaluate readiness
    svc.trigger_health_check()
    readiness = svc.evaluate_dr_readiness()
    assert readiness.overall_status in {DRReadinessStatus.READY, DRReadinessStatus.PARTIALLY_READY}
    assert readiness.rto_target_minutes == 30
    assert readiness.rpo_target_minutes == 15
    assert readiness.active_plan is not None
    assert readiness.checklist_status["active_dr_plan"] is True


# ==============================================================================
# 6. Durable Job Integration Tests
# ==============================================================================
def test_durable_jobs_reliability_execution(runtime: tuple[Session, TestClient]) -> None:
    db, _ = runtime
    registry = default_job_registry
    operator = make_user(db, "operator")

    # Verify all 6 job types are registered
    assert registry.is_registered(SafeJobType.RELIABILITY_HEALTH_CHECK)
    assert registry.is_registered(SafeJobType.RELIABILITY_INCIDENT_EVALUATE)
    assert registry.is_registered(SafeJobType.RELIABILITY_RECOVERY_RUN)
    assert registry.is_registered(SafeJobType.RELIABILITY_RECOVERY_VERIFY)
    assert registry.is_registered(SafeJobType.RELIABILITY_BACKUP_VERIFY)
    assert registry.is_registered(SafeJobType.RELIABILITY_DR_READINESS_CHECK)

    # Execute RELIABILITY_HEALTH_CHECK job
    health_job = DurableJob(
        job_type=SafeJobType.RELIABILITY_HEALTH_CHECK,
        queue_name="reliability",
        payload_json={"correlation_id": "job-test-1"},
    )
    result_health = registry.execute(db, health_job)
    assert "overall_status" in result_health
    assert "health_score" in result_health

    # Execute RELIABILITY_INCIDENT_EVALUATE job
    svc = ReliabilityService(db)
    inc = svc.create_incident(
        IncidentCreateRequest(
            title="Evaluation Target",
            description="Evaluating incident",
            component=ComponentType.STUDIO,
        ),
        actor_user_id=operator.id,
    )
    eval_job = DurableJob(
        job_type=SafeJobType.RELIABILITY_INCIDENT_EVALUATE,
        queue_name="reliability",
        payload_json={"incident_id": str(inc.id)},
    )
    result_eval = registry.execute(db, eval_job)
    assert result_eval["incident_id"] == str(inc.id)
    assert result_eval["state"] == IncidentState.DETECTED.value

    # Execute RELIABILITY_BACKUP_VERIFY job
    backup = svc.create_backup_record(
        BackupRecordCreate(
            resource_type="DATABASE",
            logical_identifier="backup_verify_job",
        )
    )
    b_job = DurableJob(
        job_type=SafeJobType.RELIABILITY_BACKUP_VERIFY,
        queue_name="reliability",
        payload_json={"backup_id": str(backup.id)},
    )
    result_b = registry.execute(db, b_job)
    assert result_b["verification_result"] == "PASSED"

    # Execute RELIABILITY_DR_READINESS_CHECK job
    dr_job = DurableJob(
        job_type=SafeJobType.RELIABILITY_DR_READINESS_CHECK,
        queue_name="reliability",
        payload_json={},
    )
    result_dr = registry.execute(db, dr_job)
    assert "overall_status" in result_dr


# ==============================================================================
# 7. RBAC & REST API Acceptance Tests
# ==============================================================================
def test_rbac_partner_denial_and_operator_allowed(runtime: tuple[Session, TestClient]) -> None:
    db, client = runtime
    partner = make_user(db, "partner")
    operator = make_user(db, "operator")

    partner_headers = auth(partner)
    operator_headers = auth(operator)

    # 1. Partner access must be denied with 403
    r_denied_health = client.get("/api/v1/reliability/health/overview", headers=partner_headers)
    assert r_denied_health.status_code == 403

    r_denied_inc = client.get("/api/v1/reliability/incidents", headers=partner_headers)
    assert r_denied_inc.status_code == 403

    r_denied_policies = client.get("/api/v1/reliability/policies", headers=partner_headers)
    assert r_denied_policies.status_code == 403

    r_denied_dr = client.get("/api/v1/reliability/dr/readiness", headers=partner_headers)
    assert r_denied_dr.status_code == 403

    r_denied_recovery = client.post(
        "/api/v1/reliability/recovery/runs",
        headers=partner_headers,
        json={"incident_id": str(uuid4()), "action_type": "VERIFY_COMPONENT_HEALTH"},
    )
    assert r_denied_recovery.status_code == 403

    # 2. Operator access must succeed
    r_ok_health = client.get("/api/v1/reliability/health/overview", headers=operator_headers)
    assert r_ok_health.status_code == 200
    assert "active_incidents_count" in r_ok_health.json()

    r_ok_comps = client.get("/api/v1/reliability/components", headers=operator_headers)
    assert r_ok_comps.status_code == 200
    assert isinstance(r_ok_comps.json(), list)

    r_ok_metrics = client.get("/api/v1/reliability/metrics", headers=operator_headers)
    assert r_ok_metrics.status_code == 200
    assert "healthy_component_count" in r_ok_metrics.json()


def test_api_full_operator_flow(runtime: tuple[Session, TestClient]) -> None:
    db, client = runtime
    operator = make_user(db, "admin")
    headers = auth(operator)

    # 1. Trigger health check
    res_hc = client.post("/api/v1/reliability/health/check", headers=headers, json={"component": "DATABASE"})
    assert res_hc.status_code == 200
    snapshot_data = res_hc.json()
    assert snapshot_data["overall_status"] == "HEALTHY"

    # 2. Create and manage incident via API
    res_inc = client.post(
        "/api/v1/reliability/incidents",
        headers=headers,
        json={
            "title": "API Gateway 502 Rate",
            "description": "Transient bad gateway responses detected",
            "component": "API",
            "severity": "MAJOR",
        },
    )
    assert res_inc.status_code == 201
    inc_id = res_inc.json()["id"]

    # Acknowledge incident
    res_ack = client.post(f"/api/v1/reliability/incidents/{inc_id}/acknowledge", headers=headers, json={"notes": "Checked ingress logs"})
    assert res_ack.status_code == 200
    assert res_ack.json()["state"] == "ACKNOWLEDGED"

    # Start recovery run
    res_rec = client.post(
        "/api/v1/reliability/recovery/runs",
        headers=headers,
        json={
            "incident_id": inc_id,
            "action_type": "VERIFY_COMPONENT_HEALTH",
            "parameters_json": {"component": "API"},
        },
    )
    assert res_rec.status_code == 201
    run_id = res_rec.json()["id"]

    # Verify recovery run
    res_v = client.post(f"/api/v1/reliability/recovery/runs/{run_id}/verify", headers=headers, json={"verification_details": "API ingress healthy"})
    assert res_v.status_code == 200
    assert res_v.json()["verification_status"] == "VERIFIED"

    # Resolve incident
    res_res = client.post(
        f"/api/v1/reliability/incidents/{inc_id}/resolve",
        headers=headers,
        json={"resolution_summary": "Upstream proxy connection pool cleared"},
    )
    assert res_res.status_code == 200
    assert res_res.json()["state"] == "RESOLVED"

    # Close incident
    res_close = client.post(
        f"/api/v1/reliability/incidents/{inc_id}/close",
        headers=headers,
        json={"recovery_verification_summary": "P99 and 5xx return code rates within SLA"},
    )
    assert res_close.status_code == 200
    assert res_close.json()["state"] == "CLOSED"

    # 3. Create & List Alert Rules
    res_rule = client.post(
        "/api/v1/reliability/alerts/rules",
        headers=headers,
        json={
            "name": "WORKER_HEARTBEAT_RULE",
            "rule_type": "WORKER_HEARTBEAT_MISSING",
            "severity": "CRITICAL",
            "component": "WORKERS",
            "threshold_value": 1.0,
            "window_seconds": 120,
            "cooldown_seconds": 180,
        },
    )
    assert res_rule.status_code == 201
    rule_id = res_rule.json()["id"]

    res_rules_list = client.get("/api/v1/reliability/alerts/rules", headers=headers)
    assert res_rules_list.status_code == 200
    assert any(r["id"] == rule_id for r in res_rules_list.json())

    # 4. Resilience Policies
    res_pol = client.post(
        "/api/v1/reliability/policies",
        headers=headers,
        json={
            "name": "workers_resilience_policy",
            "component": "WORKERS",
            "max_automatic_retries": 3,
            "recovery_cooldown_seconds": 300,
        },
    )
    assert res_pol.status_code == 201
    pol_id = res_pol.json()["id"]

    res_pol_get = client.get(f"/api/v1/reliability/policies/{pol_id}", headers=headers)
    assert res_pol_get.status_code == 200
    assert res_pol_get.json()["name"] == "workers_resilience_policy"

    # 5. Backups via API
    res_backup = client.post(
        "/api/v1/reliability/backups",
        headers=headers,
        json={
            "resource_type": "DATABASE",
            "logical_identifier": "api_db_snapshot",
            "backup_type": "FULL",
        },
    )
    assert res_backup.status_code == 201
    backup_id = res_backup.json()["id"]

    res_verify_b = client.post(f"/api/v1/reliability/backups/{backup_id}/verify", headers=headers, json={"verification_details": "API test verification"})
    assert res_verify_b.status_code == 200
    assert res_verify_b.json()["verification_result"] == "PASSED"

    # 6. DR Plans & Readiness
    res_dr_plan = client.post(
        "/api/v1/reliability/dr/plans",
        headers=headers,
        json={
            "plan_version": "v2026.api",
            "name": "API DR Plan",
            "description": "API DR test",
            "rto_target_minutes": 20,
            "rpo_target_minutes": 10,
            "activation_criteria": "Active failover criteria",
        },
    )
    assert res_dr_plan.status_code == 201
    dr_plan_id = res_dr_plan.json()["id"]

    res_act = client.post(f"/api/v1/reliability/dr/plans/{dr_plan_id}/activate", headers=headers)
    assert res_act.status_code == 200
    assert res_act.json()["is_active"] is True

    res_readiness = client.get("/api/v1/reliability/dr/readiness", headers=headers)
    assert res_readiness.status_code == 200
    assert res_readiness.json()["overall_status"] in ["READY", "PARTIALLY_READY"]

    # 7. Metrics
    res_m = client.get("/api/v1/reliability/metrics", headers=headers)
    assert res_m.status_code == 200
    assert "healthy_component_count" in res_m.json()


def test_api_crud_and_error_branches(runtime: tuple[Session, TestClient]) -> None:
    db, client = runtime
    operator = make_user(db, "operator")
    headers = auth(operator)
    fake_id = str(uuid4())

    # 1. Health overview & components
    res = client.get("/api/v1/reliability/health/overview", headers=headers)
    assert res.status_code == 200

    res = client.get("/api/v1/reliability/components", headers=headers)
    assert res.status_code == 200

    res = client.post("/api/v1/reliability/health/check", headers=headers, json={"component": "DATABASE"})
    assert res.status_code == 200

    # 2. Incident list filters & 404s
    res = client.get("/api/v1/reliability/incidents", headers=headers, params={"state": "DETECTED", "component": "DATABASE", "severity": "MAJOR"})
    assert res.status_code == 200

    res = client.get(f"/api/v1/reliability/incidents/{fake_id}", headers=headers)
    assert res.status_code == 404

    res = client.post(f"/api/v1/reliability/incidents/{fake_id}/acknowledge", headers=headers, json={"notes": "test"})
    assert res.status_code == 400

    # Create an incident to test invalid transitions
    res_inc = client.post(
        "/api/v1/reliability/incidents",
        headers=headers,
        json={
            "component": "DATABASE",
            "severity": "MAJOR",
            "title": "CRUD Incident",
            "description": "testing",
        },
    )
    assert res_inc.status_code == 201
    inc_id = res_inc.json()["id"]

    # Invalid resolve without acknowledging or recovering
    res = client.post(f"/api/v1/reliability/incidents/{inc_id}/resolve", headers=headers, json={"resolution_summary": "done"})
    assert res.status_code == 400

    # Invalid close without resolving
    res = client.post(f"/api/v1/reliability/incidents/{inc_id}/close", headers=headers, json={"recovery_verification_summary": "done"})
    assert res.status_code == 400

    # 3. Recovery actions and runs
    res = client.get("/api/v1/reliability/recovery/runs", headers=headers, params={"incident_id": inc_id})
    assert res.status_code == 200

    res = client.get(f"/api/v1/reliability/recovery/runs/{fake_id}", headers=headers)
    assert res.status_code == 404

    res = client.post(f"/api/v1/reliability/recovery/runs/{fake_id}/approve", headers=headers, json={"comments": "test"})
    assert res.status_code == 400

    res = client.post(f"/api/v1/reliability/recovery/runs/{fake_id}/verify", headers=headers, json={"verification_details": "test"})
    assert res.status_code == 400

    # 4. Alert Rules CRUD & 404s
    res = client.get("/api/v1/reliability/alerts/rules", headers=headers, params={"component": "DATABASE", "is_enabled": True})
    assert res.status_code == 200

    res = client.get(f"/api/v1/reliability/alerts/rules/{fake_id}", headers=headers)
    assert res.status_code == 404

    res_rule = client.post(
        "/api/v1/reliability/alerts/rules",
        headers=headers,
        json={
            "name": "api_crud_rule",
            "rule_type": "high_latency",
            "component": "DATABASE",
            "severity": "WARNING",
            "threshold_value": 10.0,
        },
    )
    assert res_rule.status_code == 201
    rule_id = res_rule.json()["id"]

    res = client.get(f"/api/v1/reliability/alerts/rules/{rule_id}", headers=headers)
    assert res.status_code == 200

    res = client.patch(f"/api/v1/reliability/alerts/rules/{rule_id}", headers=headers, json={"threshold_value": 20.0})
    assert res.status_code == 200
    assert res.json()["threshold_value"] == 20.0

    res = client.patch(f"/api/v1/reliability/alerts/rules/{fake_id}", headers=headers, json={"threshold_value": 30.0})
    assert res.status_code == 404

    res = client.get("/api/v1/reliability/alerts/occurrences", headers=headers, params={"limit": 10})
    assert res.status_code == 200

    res = client.post(
        "/api/v1/reliability/alerts/trigger",
        headers=headers,
        json={
            "rule_type": "high_latency",
            "component": "DATABASE",
            "message": "Manual alert test",
            "severity": "WARNING",
        },
    )
    assert res.status_code == 200

    res = client.delete(f"/api/v1/reliability/alerts/rules/{rule_id}", headers=headers)
    assert res.status_code == 200

    res = client.delete(f"/api/v1/reliability/alerts/rules/{fake_id}", headers=headers)
    assert res.status_code == 404

    # 5. Resilience Policies CRUD & 404s
    res = client.get("/api/v1/reliability/policies", headers=headers)
    assert res.status_code == 200

    res = client.get(f"/api/v1/reliability/policies/{fake_id}", headers=headers)
    assert res.status_code == 404

    res_pol = client.post(
        "/api/v1/reliability/policies",
        headers=headers,
        json={
            "name": "crud_pol",
            "component": "API",
            "incident_deduplication_window_seconds": 120,
        },
    )
    assert res_pol.status_code == 201
    pol_id = res_pol.json()["id"]

    res = client.patch(f"/api/v1/reliability/policies/{pol_id}", headers=headers, json={"incident_deduplication_window_seconds": 240})
    assert res.status_code == 200
    assert res.json()["incident_deduplication_window_seconds"] == 240

    res = client.patch(f"/api/v1/reliability/policies/{fake_id}", headers=headers, json={"incident_deduplication_window_seconds": 300})
    assert res.status_code == 404

    res = client.delete(f"/api/v1/reliability/policies/{pol_id}", headers=headers)
    assert res.status_code == 200

    res = client.delete(f"/api/v1/reliability/policies/{fake_id}", headers=headers)
    assert res.status_code == 404

    # 6. Backups CRUD & 404s
    res = client.get("/api/v1/reliability/backups", headers=headers, params={"resource_type": "DATABASE"})
    assert res.status_code == 200

    res = client.get(f"/api/v1/reliability/backups/{fake_id}", headers=headers)
    assert res.status_code == 404

    res = client.post(f"/api/v1/reliability/backups/{fake_id}/verify", headers=headers, json={"verification_details": "x"})
    assert res.status_code == 400

    # 7. DR Plans CRUD & 404s
    res = client.get("/api/v1/reliability/dr/plans", headers=headers)
    assert res.status_code == 200

    res = client.get(f"/api/v1/reliability/dr/plans/{fake_id}", headers=headers)
    assert res.status_code == 404

    res = client.patch(f"/api/v1/reliability/dr/plans/{fake_id}", headers=headers, json={"name": "Updated"})
    assert res.status_code == 404

    res = client.post(f"/api/v1/reliability/dr/plans/{fake_id}/activate", headers=headers)
    assert res.status_code == 400

    # Create and update DR Plan
    res_plan = client.post(
        "/api/v1/reliability/dr/plans",
        headers=headers,
        json={
            "plan_version": "v2026.crud",
            "name": "CRUD DR Plan",
            "description": "plan test",
            "rto_target_minutes": 15,
            "rpo_target_minutes": 5,
            "activation_criteria": "failover",
        },
    )
    assert res_plan.status_code == 201
    plan_id = res_plan.json()["id"]

    res = client.patch(f"/api/v1/reliability/dr/plans/{plan_id}", headers=headers, json={"description": "updated desc"})
    assert res.status_code == 200
    assert res.json()["description"] == "updated desc"

    res = client.post(f"/api/v1/reliability/dr/plans/{plan_id}/activate", headers=headers)
    assert res.status_code == 200
    assert res.json()["is_active"] is True


def test_additional_recovery_actions_and_edge_cases(runtime: tuple[Session, TestClient]) -> None:
    db, _ = runtime
    svc = ReliabilityService(db)

    # 1. Create incident
    req = IncidentCreateRequest(
        component=ComponentType.DATABASE,
        severity=IncidentSeverity.MAJOR,
        title="Recovery Edge Cases",
        description="Testing recovery actions",
    )
    inc = svc.create_incident(req)

    # 2. Test remaining recovery actions
    # RESTART_WORKFLOW_RUN with missing / valid run id
    run_wf = svc.start_recovery_run(inc.id, RecoveryActionType.RESTART_WORKFLOW_RUN, parameters_json={})
    assert run_wf.status == RecoveryRunStatus.SUCCEEDED

    wf_run = WorkflowRun(
        workflow_id=uuid4(),
        workflow_version=1,
        trigger_type=WorkflowTriggerType.MANUAL,
        status=WorkflowRunStatus.FAILED,
        idempotency_key=f"wf-key-{uuid4()}",
        correlation_id=f"corr-{uuid4()}",
        input_metadata_json={},
    )
    db.add(wf_run)
    db.commit()

    run_wf2 = svc.start_recovery_run(inc.id, RecoveryActionType.RESTART_WORKFLOW_RUN, parameters_json={"workflow_run_id": str(wf_run.id)})
    assert run_wf2.status == RecoveryRunStatus.SUCCEEDED
    assert run_wf2.result_json.get("status") == "restarted"

    # RETRY_WEBHOOK_DELIVERY
    run_wh = svc.start_recovery_run(inc.id, RecoveryActionType.RETRY_WEBHOOK_DELIVERY, parameters_json={"delivery_id": str(uuid4())})
    assert run_wh.status == RecoveryRunStatus.SUCCEEDED

    # RETRY_AGENT_RUN
    run_ag = svc.start_recovery_run(inc.id, RecoveryActionType.RETRY_AGENT_RUN, parameters_json={"agent_run_id": str(uuid4())})
    assert run_ag.status == RecoveryRunStatus.SUCCEEDED

    # RETRY_AUTOPILOT_PUBLICATION
    run_ap = svc.start_recovery_run(inc.id, RecoveryActionType.RETRY_AUTOPILOT_PUBLICATION, parameters_json={"attempt_id": str(uuid4())})
    assert run_ap.status == RecoveryRunStatus.SUCCEEDED

    # MARK_COMPONENT_DEGRADED (Requires approval)
    run_deg = svc.start_recovery_run(inc.id, RecoveryActionType.MARK_COMPONENT_DEGRADED, parameters_json={"component": "DATABASE"})
    assert run_deg.status == RecoveryRunStatus.PENDING_APPROVAL
    app_deg = svc.approve_recovery_run(run_deg.id, approver_user_id=1)
    assert app_deg.status == RecoveryRunStatus.SUCCEEDED

    # 3. Direct service methods and error paths
    fake_id = uuid4()
    with pytest.raises(ValueError, match="Incident '.*' not found"):
        svc.get_incident(fake_id)

    with pytest.raises(ValueError, match="Recovery run '.*' not found"):
        svc.get_recovery_run(fake_id)

    with pytest.raises(ValueError, match="Alert rule '.*' not found"):
        svc.get_alert_rule(fake_id)

    with pytest.raises(ValueError, match="Alert rule '.*' not found"):
        svc.update_alert_rule(fake_id, AlertRuleUpdate())

    with pytest.raises(ValueError, match="Alert rule '.*' not found"):
        svc.delete_alert_rule(fake_id)

    with pytest.raises(ValueError, match="Resilience policy '.*' not found"):
        svc.get_resilience_policy(fake_id)

    with pytest.raises(ValueError, match="Resilience policy '.*' not found"):
        svc.update_resilience_policy(fake_id, ResiliencePolicyUpdate())

    with pytest.raises(ValueError, match="Resilience policy '.*' not found"):
        svc.delete_resilience_policy(fake_id)

    with pytest.raises(ValueError, match="Backup record '.*' not found"):
        svc.get_backup_record(fake_id)

    with pytest.raises(ValueError, match="DR plan '.*' not found"):
        svc.get_dr_plan(fake_id)

    with pytest.raises(ValueError, match="DR plan '.*' not found"):
        svc.update_dr_plan(fake_id, DisasterRecoveryPlanUpdate())

    with pytest.raises(ValueError, match=r"(?i)dr plan .* not found"):
        svc.activate_dr_plan(fake_id, approved_by_user_id=1)

    # 4. Metrics evaluation
    metrics = svc.get_metrics()
    assert metrics.healthy_component_count >= 0
    assert metrics.unresolved_incident_count >= 1
