"""Reliability Engine for GNTV DIGITAL.

Aggregates component health, detects failures, evaluates alert rules,
maintains incident lifecycles, and emits domain events.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
import time
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.reliability.models import (
    AlertOccurrence,
    ComponentType,
    HealthStatus,
    IncidentSeverity,
    IncidentState,
    ReliabilityIncident,
    ServiceHealthCheck,
    SystemHealthSnapshot,
)
from app.modules.reliability.providers import (
    NotificationProvider,
    default_notification_provider,
)
from app.modules.reliability.repository import ReliabilityRepository

logger = logging.getLogger(__name__)

# Valid state machine transitions
ALLOWED_INCIDENT_TRANSITIONS: dict[IncidentState, set[IncidentState]] = {
    IncidentState.DETECTED: {IncidentState.ACKNOWLEDGED, IncidentState.RECOVERING},
    IncidentState.ACKNOWLEDGED: {IncidentState.RECOVERING, IncidentState.MONITORING},
    IncidentState.RECOVERING: {IncidentState.MONITORING, IncidentState.ACKNOWLEDGED},
    IncidentState.MONITORING: {IncidentState.RESOLVED, IncidentState.RECOVERING},
    IncidentState.RESOLVED: {IncidentState.CLOSED, IncidentState.MONITORING},
    IncidentState.CLOSED: set(),  # Terminal state
}


class ReliabilityEngine:
    """Core reliability engine handling monitoring, incidents, and alerting."""

    def __init__(
        self,
        repository: ReliabilityRepository,
        notifier: NotificationProvider | None = None,
    ) -> None:
        self.repo = repository
        self.db: Session = repository.db
        self.notifier = notifier or default_notification_provider

    # --- Health Monitoring & Aggregation ---
    def check_component_health(self, component: ComponentType) -> tuple[HealthStatus, float, str | None, dict[str, Any]]:
        """Run safe, bounded health check for a platform component."""
        start_time = time.perf_counter()
        status = HealthStatus.HEALTHY
        reason: str | None = None
        details: dict[str, Any] = {}

        try:
            if component == ComponentType.DATABASE:
                self.db.execute(text("SELECT 1"))
                details["connection"] = "active"

            elif component == ComponentType.API:
                details["status"] = "operational"

            elif component == ComponentType.EVENT_BUS:
                from app.modules.events.models import DomainEvent
                stmt = select(DomainEvent).order_by(DomainEvent.created_at.desc()).limit(1)
                latest_event = self.db.scalars(stmt).first()
                details["latest_event_id"] = str(latest_event.id) if latest_event else None

            elif component == ComponentType.WORKFLOW_ENGINE:
                from app.modules.workflows.models import WorkflowRun, WorkflowRunStatus
                failed_runs = self.db.query(WorkflowRun).filter(WorkflowRun.status == WorkflowRunStatus.FAILED).count()
                details["failed_runs_count"] = failed_runs
                if failed_runs > 50:
                    status = HealthStatus.DEGRADED
                    reason = f"High workflow failure count: {failed_runs}"

            elif component == ComponentType.JOB_QUEUE:
                from app.modules.jobs.models import JobDeadLetter
                dlq_count = self.db.query(JobDeadLetter).count()
                details["dlq_count"] = dlq_count
                if dlq_count > 25:
                    status = HealthStatus.DEGRADED
                    reason = f"High durable job DLQ count: {dlq_count}"

            elif component == ComponentType.WORKERS:
                from app.modules.jobs.models import WorkerRecord
                ten_min_ago = datetime.now(UTC) - timedelta(minutes=10)
                active_workers = self.db.query(WorkerRecord).filter(WorkerRecord.last_heartbeat_at >= ten_min_ago).count()
                details["active_workers"] = active_workers

            elif component == ComponentType.AI_AGENT_CONTROL:
                from app.modules.agents.models import AgentRun, AgentRunStatus
                failed_agent_runs = self.db.query(AgentRun).filter(AgentRun.status == AgentRunStatus.FAILED).count()
                details["failed_agent_runs"] = failed_agent_runs

            elif component == ComponentType.AUTOPILOT:
                from app.modules.autopilot.models import AutopilotProduction, ProductionStatus
                failed_prod = self.db.query(AutopilotProduction).filter(AutopilotProduction.status == ProductionStatus.FAILED).count()
                details["failed_productions"] = failed_prod

            elif component == ComponentType.PUBLISHING:
                from app.modules.autopilot.models import AutopilotPublishingAttempt, PublishAttemptStatus
                failed_pub = self.db.query(AutopilotPublishingAttempt).filter(AutopilotPublishingAttempt.status == PublishAttemptStatus.FAILED).count()
                details["failed_publications"] = failed_pub

            elif component == ComponentType.STUDIO:
                details["contracts"] = "valid"

        except Exception as exc:  # noqa: BLE001
            status = HealthStatus.UNHEALTHY
            reason = f"Health check failed with error: {exc}"
            details["error"] = str(exc)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return status, elapsed_ms, reason, details

    def evaluate_platform_health(
        self,
        correlation_id: str | None = None,
        components_to_check: list[ComponentType] | None = None,
    ) -> SystemHealthSnapshot:
        """Run bounded checks across all components and record a platform snapshot."""
        target_components = components_to_check or list(ComponentType)

        healthy_count = 0
        degraded_count = 0
        unhealthy_count = 0
        unknown_count = 0
        check_records: list[ServiceHealthCheck] = []

        # Create uncommitted snapshot to obtain ID for checks
        snapshot = self.repo.create_snapshot(
            overall_status=HealthStatus.HEALTHY,
            health_score=100.0,
            healthy_count=0,
            degraded_count=0,
            unhealthy_count=0,
            unknown_count=0,
            correlation_id=correlation_id,
        )

        for comp in target_components:
            status, latency_ms, reason, details = self.check_component_health(comp)
            check = self.repo.create_health_check(
                component=comp,
                status=status,
                latency_ms=latency_ms,
                failure_reason=reason,
                details_json=details,
                snapshot_id=snapshot.id,
            )
            check_records.append(check)

            if status == HealthStatus.HEALTHY:
                healthy_count += 1
            elif status == HealthStatus.DEGRADED:
                degraded_count += 1
                self._handle_unhealthy_condition(comp, status, reason or "Component degraded", correlation_id)
            elif status == HealthStatus.UNHEALTHY:
                unhealthy_count += 1
                self._handle_unhealthy_condition(comp, status, reason or "Component unhealthy", correlation_id)
            else:
                unknown_count += 1

        total = len(target_components)
        if unhealthy_count > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif degraded_count > 0:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        # Health score: 100 - (degraded * 15) - (unhealthy * 35) - (unknown * 10)
        score = 100.0 - (degraded_count * 15.0) - (unhealthy_count * 35.0) - (unknown_count * 10.0)
        score = max(0.0, min(100.0, score))

        snapshot.overall_status = overall_status
        snapshot.health_score = score
        snapshot.healthy_count = healthy_count
        snapshot.degraded_count = degraded_count
        snapshot.unhealthy_count = unhealthy_count
        snapshot.unknown_count = unknown_count
        snapshot.details_json = {
            "total_components": total,
            "checked_at": datetime.now(UTC).isoformat(),
        }

        self._emit_domain_event(
            "reliability.health.updated",
            {
                "snapshot_id": str(snapshot.id),
                "overall_status": overall_status.value,
                "health_score": score,
                "healthy_count": healthy_count,
                "degraded_count": degraded_count,
                "unhealthy_count": unhealthy_count,
            },
            correlation_id=correlation_id,
        )

        return snapshot

    def _handle_unhealthy_condition(
        self,
        component: ComponentType,
        status: HealthStatus,
        reason: str,
        correlation_id: str | None = None,
    ) -> None:
        """Handle degraded or unhealthy component by checking policy, deduplicating, and raising incident/alert."""
        policy = self.repo.get_effective_policy_for_component(component.value)
        dedup_window = policy.incident_deduplication_window_seconds if policy else 600

        # Check deduplication
        existing = self.repo.find_recent_active_incident(component, window_seconds=dedup_window)
        if existing:
            # Update retry/occurrence count and add timeline event
            existing.retry_count += 1
            self.repo.add_incident_event(
                incident_id=existing.id,
                event_type="HEALTH_FAILURE_RECURRED",
                message=f"Recurring failure on {component.value}: {reason}",
                metadata_json={"status": status.value, "retry_count": existing.retry_count},
            )
            return

        # Create new incident
        severity = IncidentSeverity.CRITICAL if status == HealthStatus.UNHEALTHY else IncidentSeverity.MAJOR
        incident = self.repo.create_incident(
            title=f"{component.value} {status.value.lower()}",
            description=f"Automated health monitor detected failure on {component.value}: {reason}",
            component=component,
            severity=severity,
            state=IncidentState.DETECTED,
            failure_reason=reason,
            correlation_id=correlation_id,
            metadata_json={"detected_by": "ReliabilityEngine"},
        )
        self.repo.add_incident_event(
            incident_id=incident.id,
            event_type="INCIDENT_DETECTED",
            from_state=None,
            to_state=IncidentState.DETECTED.value,
            message=f"Incident automatically created for {component.value}",
        )

        self._emit_domain_event(
            "reliability.incident.created",
            {
                "incident_id": str(incident.id),
                "component": component.value,
                "severity": severity.value,
                "state": IncidentState.DETECTED.value,
            },
            correlation_id=correlation_id,
        )

        self._emit_domain_event(
            "reliability.component.degraded",
            {
                "component": component.value,
                "status": status.value,
                "reason": reason,
            },
            correlation_id=correlation_id,
        )

        # Trigger alert with cooldown
        self.trigger_alert(
            rule_type="COMPONENT_HEALTH_DEGRADED",
            component=component.value,
            message=f"{component.value} health is {status.value}: {reason}",
            severity=severity,
            correlation_id=correlation_id,
            incident_id=incident.id,
        )

    # --- Alerting with Cooldown & Deduplication ---
    def trigger_alert(
        self,
        rule_type: str,
        component: str,
        message: str,
        severity: IncidentSeverity = IncidentSeverity.WARNING,
        correlation_id: str | None = None,
        incident_id: UUID | None = None,
        payload_json: dict[str, Any] | None = None,
    ) -> AlertOccurrence | None:
        """Trigger an alert, respecting cooldown and deduplication."""
        policy = self.repo.get_effective_policy_for_component(component)
        cooldown = policy.alert_cooldown_seconds if policy else 300

        dedup_key = f"{rule_type}:{component}:{severity.value}"
        recent = self.repo.get_recent_occurrence_by_dedup_key(dedup_key, cooldown_seconds=cooldown)
        if recent is not None:
            logger.info("Alert suppressed by cooldown: %s", dedup_key)
            return None

        # Check if matching rule exists
        rule = self.repo.get_alert_rule_by_name(f"{rule_type}_{component}")
        rule_id = rule.id if rule else None

        occurrence = self.repo.create_alert_occurrence(
            rule_id=rule_id,
            component=component,
            severity=severity,
            message=message,
            dedup_key=dedup_key,
            correlation_id=correlation_id,
            payload_json=payload_json or {},
            incident_id=incident_id,
        )

        # Dispatch via notification provider
        self.notifier.send_alert(
            component=component,
            severity=severity.value,
            message=message,
            correlation_id=correlation_id,
            payload=payload_json,
        )

        return occurrence

    # --- Incident Lifecycle & State Transitions ---
    def transition_incident(
        self,
        incident_id: UUID,
        target_state: IncidentState,
        actor_user_id: int | None = None,
        message: str = "",
        resolution_summary: str | None = None,
        recovery_verification_summary: str | None = None,
    ) -> ReliabilityIncident:
        """Enforce strict incident state machine transitions."""
        incident = self.repo.get_incident(incident_id)
        if incident is None:
            raise ValueError(f"Incident '{incident_id}' not found")

        current_state = incident.state
        if target_state not in ALLOWED_INCIDENT_TRANSITIONS.get(current_state, set()):
            raise ValueError(
                f"Invalid incident state transition from '{current_state.value}' to '{target_state.value}'"
            )

        # Specific requirements per transition
        now = datetime.now(UTC)
        if target_state == IncidentState.ACKNOWLEDGED:
            incident.acknowledged_at = now
            incident.acknowledged_by_user_id = actor_user_id

        elif target_state == IncidentState.RESOLVED:
            if not resolution_summary and not incident.resolution_summary:
                raise ValueError("Resolution summary is required to resolve an incident")
            incident.resolved_at = now
            incident.resolved_by_user_id = actor_user_id
            if resolution_summary:
                incident.resolution_summary = resolution_summary

        elif target_state == IncidentState.CLOSED:
            if not recovery_verification_summary and not incident.recovery_verification_summary:
                raise ValueError("Recovery verification summary is required to close an incident")
            incident.closed_at = now
            incident.closed_by_user_id = actor_user_id
            if recovery_verification_summary:
                incident.recovery_verification_summary = recovery_verification_summary

        incident.state = target_state
        self.repo.add_incident_event(
            incident_id=incident.id,
            event_type="STATE_CHANGED",
            from_state=current_state.value,
            to_state=target_state.value,
            message=message or f"Transitioned from {current_state.value} to {target_state.value}",
            actor_user_id=actor_user_id,
        )

        event_name = (
            "reliability.incident.acknowledged"
            if target_state == IncidentState.ACKNOWLEDGED
            else "reliability.incident.resolved"
            if target_state == IncidentState.RESOLVED
            else "reliability.incident.updated"
        )
        self._emit_domain_event(
            event_name,
            {
                "incident_id": str(incident.id),
                "component": incident.component.value,
                "from_state": current_state.value,
                "to_state": target_state.value,
            },
            correlation_id=incident.correlation_id,
        )

        return incident

    # --- Domain Event Emission ---
    def _emit_domain_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
    ) -> None:
        """Safely emit an internal domain event via the events module if present."""
        try:
            from app.modules.events.models import DomainEvent, EventProcessingStatus
            now = datetime.now(UTC)
            event = DomainEvent(
                event_type=event_type,
                source="reliability",
                payload_json=payload,
                status=EventProcessingStatus.RECEIVED,
                correlation_id=correlation_id or f"rel-{now.timestamp()}",
                created_at=now,
                idempotency_key=f"{event_type}:{now.timestamp()}:{payload.get('incident_id', '')}",
            )
            self.db.add(event)
            self.db.flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not persist domain event %s: %s", event_type, exc)
