"""Data repository for Reliability, Monitoring, Recovery & DR."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.modules.reliability.models import (
    AlertOccurrence,
    AlertRule,
    BackupRecord,
    BackupStatus,
    ComponentType,
    DisasterRecoveryPlan,
    HealthStatus,
    IncidentEvent,
    IncidentSeverity,
    IncidentState,
    RecoveryActionType,
    RecoveryRun,
    RecoveryRunStatus,
    RecoveryStep,
    RecoveryStepStatus,
    ReliabilityIncident,
    ResiliencePolicy,
    ServiceHealthCheck,
    SystemHealthSnapshot,
)


class ReliabilityRepository:
    """Encapsulates database operations for platform reliability."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Health Snapshots & Checks ---
    def create_snapshot(
        self,
        overall_status: HealthStatus,
        health_score: float,
        healthy_count: int,
        degraded_count: int,
        unhealthy_count: int,
        unknown_count: int,
        details_json: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> SystemHealthSnapshot:
        snapshot = SystemHealthSnapshot(
            overall_status=overall_status,
            health_score=health_score,
            healthy_count=healthy_count,
            degraded_count=degraded_count,
            unhealthy_count=unhealthy_count,
            unknown_count=unknown_count,
            details_json=details_json or {},
            correlation_id=correlation_id,
        )
        self.db.add(snapshot)
        self.db.flush()
        return snapshot

    def get_latest_snapshot(self) -> SystemHealthSnapshot | None:
        stmt = (
            select(SystemHealthSnapshot)
            .options(selectinload(SystemHealthSnapshot.checks))
            .order_by(desc(SystemHealthSnapshot.observed_at))
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def list_snapshots(self, limit: int = 20) -> list[SystemHealthSnapshot]:
        stmt = (
            select(SystemHealthSnapshot)
            .options(selectinload(SystemHealthSnapshot.checks))
            .order_by(desc(SystemHealthSnapshot.observed_at))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def create_health_check(
        self,
        component: ComponentType,
        status: HealthStatus,
        latency_ms: float,
        failure_reason: str | None = None,
        details_json: dict[str, Any] | None = None,
        snapshot_id: UUID | None = None,
    ) -> ServiceHealthCheck:
        check = ServiceHealthCheck(
            component=component,
            status=status,
            latency_ms=latency_ms,
            failure_reason=failure_reason,
            details_json=details_json or {},
            snapshot_id=snapshot_id,
        )
        self.db.add(check)
        self.db.flush()
        return check

    def list_latest_checks(self) -> list[ServiceHealthCheck]:
        latest_checks: list[ServiceHealthCheck] = []
        for comp in ComponentType:
            stmt = (
                select(ServiceHealthCheck)
                .where(ServiceHealthCheck.component == comp)
                .order_by(desc(ServiceHealthCheck.observed_at))
                .limit(1)
            )
            item = self.db.scalars(stmt).first()
            if item:
                latest_checks.append(item)
        return latest_checks

    # --- Incidents ---
    def create_incident(
        self,
        title: str,
        description: str,
        component: ComponentType,
        severity: IncidentSeverity = IncidentSeverity.WARNING,
        state: IncidentState = IncidentState.DETECTED,
        failure_reason: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        assigned_to_user_id: int | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> ReliabilityIncident:
        incident = ReliabilityIncident(
            title=title,
            description=description,
            component=component,
            severity=severity,
            state=state,
            failure_reason=failure_reason,
            correlation_id=correlation_id,
            causation_id=causation_id,
            assigned_to_user_id=assigned_to_user_id,
            metadata_json=metadata_json or {},
        )
        self.db.add(incident)
        self.db.flush()
        return incident

    def get_incident(self, incident_id: UUID) -> ReliabilityIncident | None:
        stmt = (
            select(ReliabilityIncident)
            .options(
                selectinload(ReliabilityIncident.events),
                selectinload(ReliabilityIncident.recovery_runs).selectinload(RecoveryRun.steps),
            )
            .where(ReliabilityIncident.id == incident_id)
        )
        return self.db.scalars(stmt).first()

    def list_incidents(
        self,
        state: IncidentState | None = None,
        component: ComponentType | None = None,
        severity: IncidentSeverity | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReliabilityIncident]:
        stmt = select(ReliabilityIncident).order_by(desc(ReliabilityIncident.created_at))
        if state is not None:
            stmt = stmt.where(ReliabilityIncident.state == state)
        if component is not None:
            stmt = stmt.where(ReliabilityIncident.component == component)
        if severity is not None:
            stmt = stmt.where(ReliabilityIncident.severity == severity)
        stmt = stmt.offset(offset).limit(limit)
        return list(self.db.scalars(stmt).all())

    def find_recent_active_incident(
        self,
        component: ComponentType,
        window_seconds: int = 600,
    ) -> ReliabilityIncident | None:
        threshold = datetime.now(UTC) - timedelta(seconds=window_seconds)
        stmt = (
            select(ReliabilityIncident)
            .where(
                ReliabilityIncident.component == component,
                ReliabilityIncident.state.in_(
                    [
                        IncidentState.DETECTED,
                        IncidentState.ACKNOWLEDGED,
                        IncidentState.RECOVERING,
                        IncidentState.MONITORING,
                    ]
                ),
                ReliabilityIncident.created_at >= threshold,
            )
            .order_by(desc(ReliabilityIncident.created_at))
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def add_incident_event(
        self,
        incident_id: UUID,
        event_type: str,
        message: str,
        from_state: str | None = None,
        to_state: str | None = None,
        actor_user_id: int | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> IncidentEvent:
        event = IncidentEvent(
            incident_id=incident_id,
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            message=message,
            actor_user_id=actor_user_id,
            metadata_json=metadata_json or {},
        )
        self.db.add(event)
        self.db.flush()
        inc = self.db.get(ReliabilityIncident, incident_id)
        if inc is not None:
            self.db.expire(inc, ["events"])
        return event

    # --- Recovery Runs ---
    def create_recovery_run(
        self,
        incident_id: UUID,
        action_type: RecoveryActionType,
        status: RecoveryRunStatus = RecoveryRunStatus.PENDING_APPROVAL,
        requires_approval: bool = False,
        approved_by_user_id: int | None = None,
        approved_at: datetime | None = None,
        parameters_json: dict[str, Any] | None = None,
        result_json: dict[str, Any] | None = None,
    ) -> RecoveryRun:
        run = RecoveryRun(
            incident_id=incident_id,
            action_type=action_type,
            status=status,
            requires_approval=requires_approval,
            approved_by_user_id=approved_by_user_id,
            approved_at=approved_at,
            parameters_json=parameters_json or {},
            result_json=result_json or {},
            verification_status="PENDING",
        )
        self.db.add(run)
        self.db.flush()
        inc = self.db.get(ReliabilityIncident, incident_id)
        if inc is not None:
            self.db.expire(inc, ["recovery_runs"])
        return run

    def get_recovery_run(self, run_id: UUID) -> RecoveryRun | None:
        stmt = (
            select(RecoveryRun)
            .options(selectinload(RecoveryRun.steps))
            .where(RecoveryRun.id == run_id)
        )
        return self.db.scalars(stmt).first()

    def list_recovery_runs(
        self,
        incident_id: UUID | None = None,
        status: RecoveryRunStatus | None = None,
        limit: int = 50,
    ) -> list[RecoveryRun]:
        stmt = (
            select(RecoveryRun)
            .options(selectinload(RecoveryRun.steps))
            .order_by(desc(RecoveryRun.created_at))
        )
        if incident_id is not None:
            stmt = stmt.where(RecoveryRun.incident_id == incident_id)
        if status is not None:
            stmt = stmt.where(RecoveryRun.status == status)
        return list(self.db.scalars(stmt.limit(limit)).all())

    def add_recovery_step(
        self,
        recovery_run_id: UUID,
        step_order: int,
        name: str,
        status: RecoveryStepStatus = RecoveryStepStatus.PENDING,
        output_json: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> RecoveryStep:
        step = RecoveryStep(
            recovery_run_id=recovery_run_id,
            step_order=step_order,
            name=name,
            status=status,
            output_json=output_json or {},
            error_message=error_message,
        )
        self.db.add(step)
        self.db.flush()
        r = self.db.get(RecoveryRun, recovery_run_id)
        if r is not None:
            self.db.expire(r, ["steps"])
        return step

    # --- Alerts ---
    def create_alert_rule(
        self,
        name: str,
        rule_type: str,
        severity: IncidentSeverity,
        component: str,
        threshold_value: float = 1.0,
        window_seconds: int = 300,
        cooldown_seconds: int = 300,
        is_enabled: bool = True,
        created_by: int | None = None,
    ) -> AlertRule:
        rule = AlertRule(
            name=name,
            rule_type=rule_type,
            severity=severity,
            component=component,
            threshold_value=threshold_value,
            window_seconds=window_seconds,
            cooldown_seconds=cooldown_seconds,
            is_enabled=is_enabled,
            created_by=created_by,
        )
        self.db.add(rule)
        self.db.flush()
        return rule

    def get_alert_rule(self, rule_id: UUID) -> AlertRule | None:
        return self.db.get(AlertRule, rule_id)

    def get_alert_rule_by_name(self, name: str) -> AlertRule | None:
        stmt = select(AlertRule).where(AlertRule.name == name)
        return self.db.scalars(stmt).first()

    def list_alert_rules(self, is_enabled: bool | None = None) -> list[AlertRule]:
        stmt = select(AlertRule).order_by(AlertRule.name)
        if is_enabled is not None:
            stmt = stmt.where(AlertRule.is_enabled == is_enabled)
        return list(self.db.scalars(stmt).all())

    def delete_alert_rule(self, rule_id: UUID) -> bool:
        rule = self.db.get(AlertRule, rule_id)
        if rule:
            self.db.delete(rule)
            self.db.flush()
            return True
        return False

    def create_alert_occurrence(
        self,
        rule_id: UUID | None,
        component: str,
        severity: IncidentSeverity,
        message: str,
        dedup_key: str,
        correlation_id: str | None = None,
        payload_json: dict[str, Any] | None = None,
        incident_id: UUID | None = None,
    ) -> AlertOccurrence:
        occ = AlertOccurrence(
            rule_id=rule_id,
            component=component,
            severity=severity,
            message=message,
            dedup_key=dedup_key,
            correlation_id=correlation_id,
            payload_json=payload_json or {},
            incident_id=incident_id,
        )
        self.db.add(occ)
        self.db.flush()
        return occ

    def get_recent_occurrence_by_dedup_key(
        self,
        dedup_key: str,
        cooldown_seconds: int = 300,
    ) -> AlertOccurrence | None:
        cutoff = datetime.now(UTC) - timedelta(seconds=cooldown_seconds)
        stmt = (
            select(AlertOccurrence)
            .where(
                AlertOccurrence.dedup_key == dedup_key,
                AlertOccurrence.triggered_at >= cutoff,
            )
            .order_by(desc(AlertOccurrence.triggered_at))
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def list_alert_occurrences(self, limit: int = 50) -> list[AlertOccurrence]:
        stmt = select(AlertOccurrence).order_by(desc(AlertOccurrence.triggered_at)).limit(limit)
        return list(self.db.scalars(stmt).all())

    # --- Resilience Policies ---
    def create_resilience_policy(
        self,
        name: str,
        component: str | None = None,
        max_automatic_retries: int = 3,
        recovery_cooldown_seconds: int = 300,
        escalation_threshold_minutes: int = 60,
        health_failure_threshold: int = 3,
        incident_deduplication_window_seconds: int = 600,
        alert_cooldown_seconds: int = 300,
        auto_recovery_permitted: bool = True,
        human_approval_required: bool = False,
        is_active: bool = True,
        audit_metadata_json: dict[str, Any] | None = None,
        created_by: int | None = None,
    ) -> ResiliencePolicy:
        policy = ResiliencePolicy(
            name=name,
            component=component,
            max_automatic_retries=max_automatic_retries,
            recovery_cooldown_seconds=recovery_cooldown_seconds,
            escalation_threshold_minutes=escalation_threshold_minutes,
            health_failure_threshold=health_failure_threshold,
            incident_deduplication_window_seconds=incident_deduplication_window_seconds,
            alert_cooldown_seconds=alert_cooldown_seconds,
            auto_recovery_permitted=auto_recovery_permitted,
            human_approval_required=human_approval_required,
            is_active=is_active,
            audit_metadata_json=audit_metadata_json or {},
            created_by=created_by,
        )
        self.db.add(policy)
        self.db.flush()
        return policy

    def get_resilience_policy(self, policy_id: UUID) -> ResiliencePolicy | None:
        return self.db.get(ResiliencePolicy, policy_id)

    def get_resilience_policy_by_name(self, name: str) -> ResiliencePolicy | None:
        stmt = select(ResiliencePolicy).where(ResiliencePolicy.name == name)
        return self.db.scalars(stmt).first()

    def get_effective_policy_for_component(self, component: str | None) -> ResiliencePolicy | None:
        if component:
            stmt = (
                select(ResiliencePolicy)
                .where(
                    ResiliencePolicy.component == component,
                    ResiliencePolicy.is_active.is_(True),
                )
                .limit(1)
            )
            found = self.db.scalars(stmt).first()
            if found:
                return found
        # Fallback to global policy (component is None)
        stmt_global = (
            select(ResiliencePolicy)
            .where(
                ResiliencePolicy.component.is_(None),
                ResiliencePolicy.is_active.is_(True),
            )
            .limit(1)
        )
        return self.db.scalars(stmt_global).first()

    def list_resilience_policies(self, is_active: bool | None = None) -> list[ResiliencePolicy]:
        stmt = select(ResiliencePolicy).order_by(ResiliencePolicy.name)
        if is_active is not None:
            stmt = stmt.where(ResiliencePolicy.is_active == is_active)
        return list(self.db.scalars(stmt).all())

    def delete_resilience_policy(self, policy_id: UUID) -> bool:
        policy = self.db.get(ResiliencePolicy, policy_id)
        if policy:
            self.db.delete(policy)
            self.db.flush()
            return True
        return False

    # --- Backup Records ---
    def create_backup_record(
        self,
        resource_type: str,
        logical_identifier: str,
        provider: str = "MOCK_LOCAL",
        backup_type: Any = "SNAPSHOT",
        retention_days: int = 30,
        checksum: str | None = None,
        size_bytes: int | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> BackupRecord:
        record = BackupRecord(
            resource_type=resource_type,
            logical_identifier=logical_identifier,
            provider=provider,
            backup_type=backup_type,
            retention_days=retention_days,
            checksum=checksum,
            size_bytes=size_bytes,
            metadata_json=metadata_json or {},
            status=BackupStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        self.db.add(record)
        self.db.flush()
        return record

    def get_backup_record(self, backup_id: UUID) -> BackupRecord | None:
        return self.db.get(BackupRecord, backup_id)

    def list_backup_records(
        self,
        resource_type: str | None = None,
        status: BackupStatus | None = None,
        limit: int = 50,
    ) -> list[BackupRecord]:
        stmt = select(BackupRecord).order_by(desc(BackupRecord.started_at))
        if resource_type is not None:
            stmt = stmt.where(BackupRecord.resource_type == resource_type)
        if status is not None:
            stmt = stmt.where(BackupRecord.status == status)
        return list(self.db.scalars(stmt.limit(limit)).all())

    def get_latest_backup_for_resource(self, resource_type: str) -> BackupRecord | None:
        stmt = (
            select(BackupRecord)
            .where(BackupRecord.resource_type == resource_type)
            .order_by(desc(BackupRecord.started_at))
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    # --- Disaster Recovery Plans ---
    def create_dr_plan(
        self,
        plan_version: str,
        name: str,
        description: str,
        rto_target_minutes: int = 30,
        rpo_target_minutes: int = 15,
        activation_criteria: str = "",
        recovery_priorities_json: list[str] | None = None,
        dependencies_json: dict[str, Any] | None = None,
        verification_checklist_json: list[str] | None = None,
        requires_approval: bool = True,
        is_active: bool = False,
        created_by_user_id: int | None = None,
    ) -> DisasterRecoveryPlan:
        plan = DisasterRecoveryPlan(
            plan_version=plan_version,
            name=name,
            description=description,
            rto_target_minutes=rto_target_minutes,
            rpo_target_minutes=rpo_target_minutes,
            activation_criteria=activation_criteria,
            recovery_priorities_json=recovery_priorities_json or [],
            dependencies_json=dependencies_json or {},
            verification_checklist_json=verification_checklist_json or [],
            requires_approval=requires_approval,
            is_active=is_active,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(plan)
        self.db.flush()
        return plan

    def get_dr_plan(self, plan_id: UUID) -> DisasterRecoveryPlan | None:
        return self.db.get(DisasterRecoveryPlan, plan_id)

    def get_dr_plan_by_version(self, plan_version: str) -> DisasterRecoveryPlan | None:
        stmt = select(DisasterRecoveryPlan).where(DisasterRecoveryPlan.plan_version == plan_version)
        return self.db.scalars(stmt).first()

    def get_active_dr_plan(self) -> DisasterRecoveryPlan | None:
        stmt = select(DisasterRecoveryPlan).where(DisasterRecoveryPlan.is_active.is_(True)).limit(1)
        return self.db.scalars(stmt).first()

    def set_active_dr_plan(self, plan_id: UUID) -> DisasterRecoveryPlan:
        # Deactivate any currently active plan
        stmt = select(DisasterRecoveryPlan).where(DisasterRecoveryPlan.is_active.is_(True))
        for active in self.db.scalars(stmt).all():
            active.is_active = False

        plan = self.db.get(DisasterRecoveryPlan, plan_id)
        if plan is None:
            raise ValueError(f"DR Plan {plan_id} not found")
        plan.is_active = True
        self.db.flush()
        return plan

    def list_dr_plans(self) -> list[DisasterRecoveryPlan]:
        stmt = select(DisasterRecoveryPlan).order_by(desc(DisasterRecoveryPlan.created_at))
        return list(self.db.scalars(stmt).all())

    # --- Metrics Aggregation ---
    def count_incidents_by_severity(self) -> dict[str, int]:
        stmt = select(
            ReliabilityIncident.severity,
            func.count(ReliabilityIncident.id),
        ).group_by(ReliabilityIncident.severity)
        return {str(sev.value if hasattr(sev, "value") else sev): count for sev, count in self.db.execute(stmt).all()}

    def count_unresolved_incidents(self) -> int:
        stmt = select(func.count(ReliabilityIncident.id)).where(
            ReliabilityIncident.state.in_(
                [
                    IncidentState.DETECTED,
                    IncidentState.ACKNOWLEDGED,
                    IncidentState.RECOVERING,
                    IncidentState.MONITORING,
                ]
            )
        )
        return int(self.db.scalar(stmt) or 0)
