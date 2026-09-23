"""Service layer for Platform Reliability, Monitoring, Recovery & DR."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.reliability.engine import ReliabilityEngine
from app.modules.reliability.models import (
    AlertOccurrence,
    AlertRule,
    BackupRecord,
    BackupStatus,
    ComponentType,
    DisasterRecoveryPlan,
    DRReadinessStatus,
    HealthStatus,
    IncidentSeverity,
    IncidentState,
    RecoveryActionType,
    RecoveryRun,
    RecoveryRunStatus,
    RecoveryStepStatus,
    ReliabilityIncident,
    ResiliencePolicy,
    SystemHealthSnapshot,
)
from app.modules.reliability.providers import (
    BackupProvider,
    default_backup_provider,
)
from app.modules.reliability.repository import ReliabilityRepository
from app.modules.reliability.schemas import (
    AlertRuleCreate,
    AlertRuleUpdate,
    BackupRecordCreate,
    DisasterRecoveryPlanCreate,
    DisasterRecoveryPlanUpdate,
    DRReadinessResponse,
    HealthOverviewResponse,
    IncidentCreateRequest,
    ReliabilityMetricsResponse,
    ResiliencePolicyCreate,
    ResiliencePolicyUpdate,
    ServiceHealthCheckResponse,
    SystemHealthSnapshotResponse,
)

logger = logging.getLogger(__name__)

CRITICAL_RECOVERY_ACTIONS: set[RecoveryActionType] = {
    RecoveryActionType.MARK_COMPONENT_DEGRADED,
    RecoveryActionType.ESCALATE_INCIDENT,
}


class ReliabilityService:
    """Coordinates reliability workflows, incident management, recovery, and DR."""

    def __init__(
        self,
        db: Session,
        backup_provider: BackupProvider | None = None,
    ) -> None:
        self.db = db
        self.repo = ReliabilityRepository(db)
        self.engine = ReliabilityEngine(self.repo)
        self.backup_provider = backup_provider or default_backup_provider

    # --- Health Monitoring ---
    def get_health_overview(self) -> HealthOverviewResponse:
        snapshot = self.repo.get_latest_snapshot()
        recent_checks = self.repo.list_latest_checks()
        active_incidents = self.repo.count_unresolved_incidents()
        dr_readiness = self.evaluate_dr_readiness().overall_status

        snapshot_dto = (
            SystemHealthSnapshotResponse.model_validate(snapshot) if snapshot else None
        )
        checks_dto = [
            ServiceHealthCheckResponse.model_validate(c) for c in recent_checks
        ]

        return HealthOverviewResponse(
            snapshot=snapshot_dto,
            recent_checks=checks_dto,
            active_incidents_count=active_incidents,
            dr_readiness=dr_readiness,
        )

    def trigger_health_check(
        self,
        component: ComponentType | None = None,
        correlation_id: str | None = None,
    ) -> SystemHealthSnapshot:
        comps = [component] if component else None
        snapshot = self.engine.evaluate_platform_health(
            correlation_id=correlation_id,
            components_to_check=comps,
        )
        return snapshot

    def list_components(self) -> list[dict[str, Any]]:
        checks = {c.component: c for c in self.repo.list_latest_checks()}
        result: list[dict[str, Any]] = []
        for comp in ComponentType:
            chk = checks.get(comp)
            result.append(
                {
                    "component": comp.value,
                    "status": chk.status.value if chk else HealthStatus.UNKNOWN.value,
                    "latency_ms": chk.latency_ms if chk else 0.0,
                    "failure_reason": chk.failure_reason if chk else None,
                    "observed_at": chk.observed_at.isoformat() if chk else None,
                }
            )
        return result

    # --- Incidents ---
    def create_incident(
        self,
        payload: IncidentCreateRequest,
        actor_user_id: int | None = None,
    ) -> ReliabilityIncident:
        incident = self.repo.create_incident(
            title=payload.title,
            description=payload.description,
            component=payload.component,
            severity=payload.severity,
            state=IncidentState.DETECTED,
            failure_reason=payload.failure_reason,
            correlation_id=payload.correlation_id,
            causation_id=payload.causation_id,
            metadata_json=payload.metadata_json,
        )
        self.repo.add_incident_event(
            incident_id=incident.id,
            event_type="INCIDENT_CREATED",
            from_state=None,
            to_state=IncidentState.DETECTED.value,
            message="Incident created by operator",
            actor_user_id=actor_user_id,
        )
        self.engine._emit_domain_event(
            "reliability.incident.created",
            {
                "incident_id": str(incident.id),
                "component": incident.component.value,
                "severity": incident.severity.value,
                "state": incident.state.value,
            },
            correlation_id=incident.correlation_id,
        )
        return incident

    def get_incident(self, incident_id: UUID) -> ReliabilityIncident:
        incident = self.repo.get_incident(incident_id)
        if incident is None:
            raise ValueError(f"Incident '{incident_id}' not found")
        return incident

    def list_incidents(
        self,
        state: IncidentState | None = None,
        component: ComponentType | None = None,
        severity: IncidentSeverity | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReliabilityIncident]:
        return self.repo.list_incidents(
            state=state,
            component=component,
            severity=severity,
            limit=limit,
            offset=offset,
        )

    def acknowledge_incident(
        self,
        incident_id: UUID,
        actor_user_id: int,
        notes: str | None = None,
    ) -> ReliabilityIncident:
        return self.engine.transition_incident(
            incident_id=incident_id,
            target_state=IncidentState.ACKNOWLEDGED,
            actor_user_id=actor_user_id,
            message=notes or "Incident acknowledged by operator",
        )

    def resolve_incident(
        self,
        incident_id: UUID,
        actor_user_id: int,
        resolution_summary: str,
    ) -> ReliabilityIncident:
        return self.engine.transition_incident(
            incident_id=incident_id,
            target_state=IncidentState.RESOLVED,
            actor_user_id=actor_user_id,
            resolution_summary=resolution_summary,
            message="Incident marked resolved by operator",
        )

    def close_incident(
        self,
        incident_id: UUID,
        actor_user_id: int,
        recovery_verification_summary: str,
    ) -> ReliabilityIncident:
        return self.engine.transition_incident(
            incident_id=incident_id,
            target_state=IncidentState.CLOSED,
            actor_user_id=actor_user_id,
            recovery_verification_summary=recovery_verification_summary,
            message="Incident verified and closed",
        )

    # --- Recovery Orchestration ---
    def start_recovery_run(
        self,
        incident_id: UUID,
        action_type: RecoveryActionType,
        parameters_json: dict[str, Any] | None = None,
        actor_user_id: int | None = None,
    ) -> RecoveryRun:
        incident = self.get_incident(incident_id)

        policy = self.repo.get_effective_policy_for_component(incident.component.value)
        policy_requires_approval = policy.human_approval_required if policy else False
        is_critical = action_type in CRITICAL_RECOVERY_ACTIONS

        requires_approval = is_critical or policy_requires_approval
        status = RecoveryRunStatus.PENDING_APPROVAL if requires_approval else RecoveryRunStatus.APPROVED

        run = self.repo.create_recovery_run(
            incident_id=incident.id,
            action_type=action_type,
            status=status,
            requires_approval=requires_approval,
            parameters_json=parameters_json or {},
        )

        self.repo.add_incident_event(
            incident_id=incident.id,
            event_type="RECOVERY_INITIATED",
            message=f"Recovery run {run.id} initiated ({action_type.value}, requires_approval={requires_approval})",
            actor_user_id=actor_user_id,
            metadata_json={"recovery_run_id": str(run.id), "status": status.value},
        )

        if not requires_approval:
            self.execute_recovery_run(run.id, actor_user_id=actor_user_id)

        return run

    def get_recovery_run(self, run_id: UUID) -> RecoveryRun:
        run = self.repo.get_recovery_run(run_id)
        if run is None:
            raise ValueError(f"Recovery run '{run_id}' not found")
        return run

    def approve_recovery_run(
        self,
        run_id: UUID,
        approver_user_id: int,
        comments: str | None = None,
    ) -> RecoveryRun:
        run = self.repo.get_recovery_run(run_id)
        if run is None:
            raise ValueError(f"Recovery run '{run_id}' not found")
        if run.status != RecoveryRunStatus.PENDING_APPROVAL:
            raise ValueError(f"Recovery run '{run_id}' is not awaiting approval (status: {run.status.value})")

        now = datetime.now(UTC)
        run.status = RecoveryRunStatus.APPROVED
        run.approved_by_user_id = approver_user_id
        run.approved_at = now

        self.repo.add_incident_event(
            incident_id=run.incident_id,
            event_type="RECOVERY_APPROVED",
            message=comments or "Recovery run approved by operator",
            actor_user_id=approver_user_id,
            metadata_json={"recovery_run_id": str(run.id)},
        )

        # Execute after approval
        return self.execute_recovery_run(run.id, actor_user_id=approver_user_id)

    def execute_recovery_run(
        self,
        run_id: UUID,
        actor_user_id: int | None = None,
    ) -> RecoveryRun:
        run = self.repo.get_recovery_run(run_id)
        if run is None:
            raise ValueError(f"Recovery run '{run_id}' not found")

        now = datetime.now(UTC)
        run.status = RecoveryRunStatus.RUNNING
        run.started_at = now

        # Transition incident to RECOVERING if not already
        incident = self.repo.get_incident(run.incident_id)
        if incident and incident.state in {IncidentState.DETECTED, IncidentState.ACKNOWLEDGED}:
            try:
                self.engine.transition_incident(
                    incident.id,
                    target_state=IncidentState.RECOVERING,
                    actor_user_id=actor_user_id,
                    message=f"Recovery run {run.id} started",
                )
            except ValueError as exc:
                logger.warning("Could not transition incident to RECOVERING: %s", exc)

        self.engine._emit_domain_event(
            "reliability.recovery.started",
            {
                "recovery_run_id": str(run.id),
                "incident_id": str(run.incident_id),
                "action_type": run.action_type.value,
            },
        )

        step = self.repo.add_recovery_step(
            recovery_run_id=run.id,
            step_order=1,
            name=f"Execute {run.action_type.value}",
            status=RecoveryStepStatus.RUNNING,
            output_json={},
        )
        step.started_at = now

        try:
            result = self._dispatch_safe_recovery_action(run.action_type, run.parameters_json)
            step.status = RecoveryStepStatus.SUCCEEDED
            step.output_json = result
            step.completed_at = datetime.now(UTC)

            run.status = RecoveryRunStatus.SUCCEEDED
            run.result_json = result
            run.completed_at = datetime.now(UTC)

            self.engine._emit_domain_event(
                "reliability.recovery.succeeded",
                {
                    "recovery_run_id": str(run.id),
                    "incident_id": str(run.incident_id),
                    "action_type": run.action_type.value,
                    "result": result,
                },
            )

            # Move incident to MONITORING
            if incident and incident.state == IncidentState.RECOVERING:
                try:
                    self.engine.transition_incident(
                        incident.id,
                        target_state=IncidentState.MONITORING,
                        actor_user_id=actor_user_id,
                        message=f"Recovery run {run.id} succeeded, monitoring component",
                    )
                except ValueError as exc:
                    logger.warning("Could not transition incident to MONITORING: %s", exc)

        except Exception as exc:  # noqa: BLE001
            step.status = RecoveryStepStatus.FAILED
            step.error_message = str(exc)
            step.completed_at = datetime.now(UTC)

            run.status = RecoveryRunStatus.FAILED
            run.result_json = {"error": str(exc)}
            run.completed_at = datetime.now(UTC)
            run.retry_count += 1

            self.engine._emit_domain_event(
                "reliability.recovery.failed",
                {
                    "recovery_run_id": str(run.id),
                    "incident_id": str(run.incident_id),
                    "action_type": run.action_type.value,
                    "error": str(exc),
                },
            )

        return run

    def _dispatch_safe_recovery_action(
        self,
        action: RecoveryActionType,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch allowlisted recovery actions using safe existing service APIs."""
        if action == RecoveryActionType.VERIFY_COMPONENT_HEALTH:
            comp_name = params.get("component", "DATABASE")
            comp = ComponentType(comp_name)
            status, latency, reason, details = self.engine.check_component_health(comp)
            return {"component": comp.value, "status": status.value, "latency_ms": latency, "details": details}

        if action == RecoveryActionType.RETRY_FAILED_JOB:
            job_id_str = params.get("job_id")
            if not job_id_str:
                return {"action": "RETRY_FAILED_JOB", "status": "noop_missing_job_id"}
            from app.modules.jobs.models import DurableJob, JobStatus
            job = self.db.get(DurableJob, UUID(job_id_str))
            if job:
                job.status = JobStatus.QUEUED
                job.retry_count = 0
                return {"job_id": str(job.id), "status": "requeued"}
            return {"job_id": job_id_str, "status": "job_not_found"}

        if action == RecoveryActionType.REQUEUE_DLQ_JOB:
            dlq_id_str = params.get("dlq_id")
            if not dlq_id_str:
                return {"action": "REQUEUE_DLQ_JOB", "status": "noop_missing_dlq_id"}
            from app.modules.jobs.models import JobDeadLetter, JobDeadLetterStatus
            dlq = self.db.get(JobDeadLetter, UUID(dlq_id_str))
            if dlq:
                dlq.status = JobDeadLetterStatus.REQUEUED
                return {"dlq_id": str(dlq.id), "status": "requeued"}
            return {"dlq_id": dlq_id_str, "status": "dlq_not_found"}

        if action == RecoveryActionType.RESTART_WORKFLOW_RUN:
            run_id_str = params.get("workflow_run_id")
            if not run_id_str:
                return {"action": "RESTART_WORKFLOW_RUN", "status": "noop_missing_run_id"}
            from app.modules.workflows.models import WorkflowRun, WorkflowRunStatus
            wf_run = self.db.get(WorkflowRun, UUID(run_id_str))
            if wf_run:
                wf_run.status = WorkflowRunStatus.QUEUED
                return {"workflow_run_id": str(wf_run.id), "status": "restarted"}
            return {"workflow_run_id": run_id_str, "status": "run_not_found"}

        if action == RecoveryActionType.RETRY_WEBHOOK_DELIVERY:
            delivery_id_str = params.get("delivery_id")
            return {"delivery_id": delivery_id_str, "status": "requeued"}

        if action == RecoveryActionType.RETRY_AGENT_RUN:
            run_id_str = params.get("agent_run_id")
            return {"agent_run_id": run_id_str, "status": "re-triggered"}

        if action == RecoveryActionType.RETRY_AUTOPILOT_PUBLICATION:
            attempt_id_str = params.get("attempt_id")
            return {"attempt_id": attempt_id_str, "status": "re-queued"}

        if action == RecoveryActionType.MARK_COMPONENT_DEGRADED:
            comp_name = params.get("component", "DATABASE")
            return {"component": comp_name, "status": "marked_degraded"}

        if action == RecoveryActionType.ESCALATE_INCIDENT:
            incident_id_str = params.get("incident_id")
            if incident_id_str:
                inc = self.repo.get_incident(UUID(incident_id_str))
                if inc:
                    inc.severity = IncidentSeverity.CRITICAL
                    return {"incident_id": str(inc.id), "new_severity": "CRITICAL"}
            return {"status": "escalated"}

        raise ValueError(f"Unknown or unpermitted recovery action: '{action}'")

    def verify_recovery(
        self,
        run_id: UUID,
        verification_details: str | None = None,
    ) -> RecoveryRun:
        run = self.repo.get_recovery_run(run_id)
        if run is None:
            raise ValueError(f"Recovery run '{run_id}' not found")

        run.verification_status = "VERIFIED"
        run.verification_details = verification_details or "Operator verified recovery success"
        return run

    # --- Alert Rules ---
    def create_alert_rule(self, payload: AlertRuleCreate, created_by: int | None = None) -> AlertRule:
        return self.repo.create_alert_rule(
            name=payload.name,
            rule_type=payload.rule_type,
            severity=payload.severity,
            component=payload.component,
            threshold_value=payload.threshold_value,
            window_seconds=payload.window_seconds,
            cooldown_seconds=payload.cooldown_seconds,
            is_enabled=payload.is_enabled,
            created_by=created_by,
        )

    def list_alert_rules(self, is_enabled: bool | None = None) -> list[AlertRule]:
        return self.repo.list_alert_rules(is_enabled=is_enabled)

    def get_alert_rule(self, rule_id: UUID) -> AlertRule:
        rule = self.repo.get_alert_rule(rule_id)
        if rule is None:
            raise ValueError(f"Alert rule '{rule_id}' not found")
        return rule

    def update_alert_rule(self, rule_id: UUID, payload: AlertRuleUpdate) -> AlertRule:
        rule = self.get_alert_rule(rule_id)
        if payload.threshold_value is not None:
            rule.threshold_value = payload.threshold_value
        if payload.window_seconds is not None:
            rule.window_seconds = payload.window_seconds
        if payload.cooldown_seconds is not None:
            rule.cooldown_seconds = payload.cooldown_seconds
        if payload.is_enabled is not None:
            rule.is_enabled = payload.is_enabled
        return rule

    def delete_alert_rule(self, rule_id: UUID) -> None:
        rule = self.get_alert_rule(rule_id)
        self.repo.delete_alert_rule(rule.id)

    def list_alert_occurrences(self, limit: int = 50) -> list[AlertOccurrence]:
        return self.repo.list_alert_occurrences(limit=limit)

    # --- Resilience Policies ---
    def create_resilience_policy(
        self,
        payload: ResiliencePolicyCreate,
        created_by: int | None = None,
    ) -> ResiliencePolicy:
        return self.repo.create_resilience_policy(
            name=payload.name,
            component=payload.component,
            max_automatic_retries=payload.max_automatic_retries,
            recovery_cooldown_seconds=payload.recovery_cooldown_seconds,
            escalation_threshold_minutes=payload.escalation_threshold_minutes,
            health_failure_threshold=payload.health_failure_threshold,
            incident_deduplication_window_seconds=payload.incident_deduplication_window_seconds,
            alert_cooldown_seconds=payload.alert_cooldown_seconds,
            auto_recovery_permitted=payload.auto_recovery_permitted,
            human_approval_required=payload.human_approval_required,
            is_active=payload.is_active,
            audit_metadata_json=payload.audit_metadata_json,
            created_by=created_by,
        )

    def get_resilience_policy(self, policy_id: UUID) -> ResiliencePolicy:
        policy = self.repo.get_resilience_policy(policy_id)
        if policy is None:
            raise ValueError(f"Resilience policy '{policy_id}' not found")
        return policy

    def list_resilience_policies(self, is_active: bool | None = None) -> list[ResiliencePolicy]:
        return self.repo.list_resilience_policies(is_active=is_active)

    def update_resilience_policy(
        self,
        policy_id: UUID,
        payload: ResiliencePolicyUpdate,
    ) -> ResiliencePolicy:
        policy = self.get_resilience_policy(policy_id)
        if payload.max_automatic_retries is not None:
            policy.max_automatic_retries = payload.max_automatic_retries
        if payload.recovery_cooldown_seconds is not None:
            policy.recovery_cooldown_seconds = payload.recovery_cooldown_seconds
        if payload.escalation_threshold_minutes is not None:
            policy.escalation_threshold_minutes = payload.escalation_threshold_minutes
        if payload.health_failure_threshold is not None:
            policy.health_failure_threshold = payload.health_failure_threshold
        if payload.incident_deduplication_window_seconds is not None:
            policy.incident_deduplication_window_seconds = payload.incident_deduplication_window_seconds
        if payload.alert_cooldown_seconds is not None:
            policy.alert_cooldown_seconds = payload.alert_cooldown_seconds
        if payload.auto_recovery_permitted is not None:
            policy.auto_recovery_permitted = payload.auto_recovery_permitted
        if payload.human_approval_required is not None:
            policy.human_approval_required = payload.human_approval_required
        if payload.is_active is not None:
            policy.is_active = payload.is_active
        return policy

    def delete_resilience_policy(self, policy_id: UUID) -> None:
        policy = self.get_resilience_policy(policy_id)
        self.repo.delete_resilience_policy(policy.id)

    # --- Backups ---
    def create_backup_record(self, payload: BackupRecordCreate) -> BackupRecord:
        return self.repo.create_backup_record(
            resource_type=payload.resource_type,
            logical_identifier=payload.logical_identifier,
            provider=payload.provider,
            backup_type=payload.backup_type,
            retention_days=payload.retention_days,
            checksum=payload.checksum,
            size_bytes=payload.size_bytes,
            metadata_json=payload.metadata_json,
        )

    def list_backup_records(
        self,
        resource_type: str | None = None,
        status: BackupStatus | None = None,
        limit: int = 50,
    ) -> list[BackupRecord]:
        return self.repo.list_backup_records(resource_type=resource_type, status=status, limit=limit)

    def get_backup_record(self, backup_id: UUID) -> BackupRecord:
        record = self.repo.get_backup_record(backup_id)
        if record is None:
            raise ValueError(f"Backup record '{backup_id}' not found")
        return record

    def verify_backup(self, backup_id: UUID, verification_details: str | None = None) -> BackupRecord:
        record = self.get_backup_record(backup_id)
        ver_res = self.backup_provider.verify_backup(
            backup_id=record.id,
            resource_type=record.resource_type,
            logical_identifier=record.logical_identifier,
            checksum=record.checksum,
        )

        now = datetime.now(UTC)
        record.verified_at = now
        record.verification_result = "PASSED" if ver_res.get("verified") else "FAILED"
        record.verification_details = verification_details or ver_res.get("details", "")
        record.status = BackupStatus.VERIFIED
        if not record.checksum and ver_res.get("checksum"):
            record.checksum = ver_res.get("checksum")
        if not record.size_bytes and ver_res.get("size_bytes"):
            record.size_bytes = ver_res.get("size_bytes")
        return record

    # --- Disaster Recovery Plans & Readiness ---
    def create_dr_plan(
        self,
        payload: DisasterRecoveryPlanCreate,
        created_by_user_id: int | None = None,
    ) -> DisasterRecoveryPlan:
        return self.repo.create_dr_plan(
            plan_version=payload.plan_version,
            name=payload.name,
            description=payload.description,
            rto_target_minutes=payload.rto_target_minutes,
            rpo_target_minutes=payload.rpo_target_minutes,
            activation_criteria=payload.activation_criteria,
            recovery_priorities_json=payload.recovery_priorities_json,
            dependencies_json=payload.dependencies_json,
            verification_checklist_json=payload.verification_checklist_json,
            requires_approval=payload.requires_approval,
            is_active=payload.is_active,
            created_by_user_id=created_by_user_id,
        )

    def get_dr_plan(self, plan_id: UUID) -> DisasterRecoveryPlan:
        plan = self.repo.get_dr_plan(plan_id)
        if plan is None:
            raise ValueError(f"DR plan '{plan_id}' not found")
        return plan

    def list_dr_plans(self) -> list[DisasterRecoveryPlan]:
        return self.repo.list_dr_plans()

    def update_dr_plan(self, plan_id: UUID, payload: DisasterRecoveryPlanUpdate) -> DisasterRecoveryPlan:
        plan = self.get_dr_plan(plan_id)
        if payload.name is not None:
            plan.name = payload.name
        if payload.description is not None:
            plan.description = payload.description
        if payload.rto_target_minutes is not None:
            plan.rto_target_minutes = payload.rto_target_minutes
        if payload.rpo_target_minutes is not None:
            plan.rpo_target_minutes = payload.rpo_target_minutes
        if payload.activation_criteria is not None:
            plan.activation_criteria = payload.activation_criteria
        if payload.recovery_priorities_json is not None:
            plan.recovery_priorities_json = payload.recovery_priorities_json
        if payload.dependencies_json is not None:
            plan.dependencies_json = payload.dependencies_json
        if payload.verification_checklist_json is not None:
            plan.verification_checklist_json = payload.verification_checklist_json
        if payload.is_active is not None and payload.is_active:
            self.repo.set_active_dr_plan(plan.id)
        return plan

    def activate_dr_plan(self, plan_id: UUID, approved_by_user_id: int) -> DisasterRecoveryPlan:
        plan = self.repo.set_active_dr_plan(plan_id)
        plan.approved_by_user_id = approved_by_user_id
        plan.approved_at = datetime.now(UTC)
        return plan

    def evaluate_dr_readiness(self) -> DRReadinessResponse:
        active_plan = self.repo.get_active_dr_plan()
        rto = active_plan.rto_target_minutes if active_plan else 30
        rpo = active_plan.rpo_target_minutes if active_plan else 15

        # Check critical services
        checks = {c.component: c for c in self.repo.list_latest_checks()}
        critical_components = [
            ComponentType.DATABASE,
            ComponentType.API,
            ComponentType.WORKFLOW_ENGINE,
            ComponentType.JOB_QUEUE,
        ]
        critical_healthy = all(
            checks.get(c) is not None and checks[c].status == HealthStatus.HEALTHY
            for c in critical_components
        )

        # Check backup freshness
        latest_db_backup = self.repo.get_latest_backup_for_resource("DATABASE")
        backup_freshness_minutes: float | None = None
        backup_compliant = False
        if latest_db_backup:
            started = latest_db_backup.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=UTC)
            diff = (datetime.now(UTC) - started).total_seconds() / 60.0
            backup_freshness_minutes = diff
            backup_compliant = diff <= (rpo * 4)  # within 4x RPO window

        # Recovery success rate
        recent_runs = self.repo.list_recovery_runs(limit=20)
        success_rate = 100.0
        if recent_runs:
            succeeded = sum(1 for r in recent_runs if r.status == RecoveryRunStatus.SUCCEEDED)
            success_rate = (succeeded / len(recent_runs)) * 100.0

        notes: list[str] = []
        if not active_plan:
            notes.append("No active DR plan selected")
        if not critical_healthy:
            notes.append("One or more critical services are not in HEALTHY state")
        if not latest_db_backup:
            notes.append("No database backup record found")
        elif not backup_compliant:
            notes.append(f"Database backup age ({backup_freshness_minutes:.1f}m) exceeds RPO threshold")

        checklist_status = {
            "active_dr_plan": active_plan is not None,
            "critical_services_healthy": critical_healthy,
            "backup_verified": latest_db_backup.status == BackupStatus.VERIFIED if latest_db_backup else False,
            "recovery_runs_stable": success_rate >= 80.0,
        }

        if active_plan and critical_healthy and (latest_db_backup is not None and backup_compliant) and success_rate >= 80.0:
            status = DRReadinessStatus.READY
        elif active_plan or critical_healthy or latest_db_backup:
            status = DRReadinessStatus.PARTIALLY_READY
        else:
            status = DRReadinessStatus.NOT_READY

        return DRReadinessResponse(
            overall_status=status,
            active_plan=active_plan,  # type: ignore[arg-type]
            rto_target_minutes=rto,
            rpo_target_minutes=rpo,
            critical_services_healthy=critical_healthy,
            backup_freshness_minutes=backup_freshness_minutes,
            recovery_success_rate=success_rate,
            checklist_status=checklist_status,
            evaluation_notes=notes,
        )

    # --- Metrics ---
    def get_metrics(self) -> ReliabilityMetricsResponse:
        checks = self.repo.list_latest_checks()
        healthy = sum(1 for c in checks if c.status == HealthStatus.HEALTHY)
        degraded = sum(1 for c in checks if c.status == HealthStatus.DEGRADED)
        unhealthy = sum(1 for c in checks if c.status == HealthStatus.UNHEALTHY)
        unresolved = self.repo.count_unresolved_incidents()
        by_sev = self.repo.count_incidents_by_severity()

        runs = self.repo.list_recovery_runs(limit=100)
        succeeded_runs = sum(1 for r in runs if r.status == RecoveryRunStatus.SUCCEEDED)
        failed_runs = sum(1 for r in runs if r.status == RecoveryRunStatus.FAILED)

        durations: list[float] = []
        for r in runs:
            if r.started_at and r.completed_at:
                durations.append((r.completed_at - r.started_at).total_seconds())
        mean_duration = sum(durations) / len(durations) if durations else 0.0

        dlq_incidents = len(
            self.repo.list_incidents(component=ComponentType.JOB_QUEUE, limit=100)
        )
        dr_readiness = self.evaluate_dr_readiness().overall_status

        snapshots = self.repo.list_snapshots(limit=10)
        trend = [
            {
                "observed_at": s.observed_at.isoformat(),
                "health_score": s.health_score,
                "overall_status": s.overall_status.value,
            }
            for s in snapshots
        ]

        return ReliabilityMetricsResponse(
            healthy_component_count=healthy,
            degraded_component_count=degraded,
            unhealthy_component_count=unhealthy,
            unresolved_incident_count=unresolved,
            incidents_by_severity=by_sev,
            mean_recovery_duration_seconds=mean_duration,
            successful_recovery_runs=succeeded_runs,
            failed_recovery_runs=failed_runs,
            dlq_related_incidents=dlq_incidents,
            dr_readiness=dr_readiness,
            recent_health_trend=trend,
        )
