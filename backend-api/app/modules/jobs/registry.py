"""Allowlisted job type registry and safe execution handlers."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.jobs.models import DurableJob

logger = logging.getLogger(__name__)


class SafeJobType(StrEnum):
    """Allowlisted internal executable job types."""

    WORKFLOW_RUN = "WORKFLOW_RUN"
    EVENT_DISPATCH = "EVENT_DISPATCH"
    OUTBOUND_WEBHOOK_DELIVERY = "OUTBOUND_WEBHOOK_DELIVERY"
    REPORT_GENERATION = "REPORT_GENERATION"
    NOTIFICATION_EVENT = "NOTIFICATION_EVENT"
    CONTENT_PUBLISH_REQUEST = "CONTENT_PUBLISH_REQUEST"
    DISTRIBUTION_REQUEST = "DISTRIBUTION_REQUEST"
    MEDIA_PROCESSING_REQUEST = "MEDIA_PROCESSING_REQUEST"
    AI_AGENT_RUN = "AI_AGENT_RUN"
    AUTOPILOT_RESEARCH = "AUTOPILOT_RESEARCH"
    AUTOPILOT_SCRIPT_GENERATION = "AUTOPILOT_SCRIPT_GENERATION"
    AUTOPILOT_PRODUCTION_PLAN = "AUTOPILOT_PRODUCTION_PLAN"
    AUTOPILOT_ASSET_PREPARATION = "AUTOPILOT_ASSET_PREPARATION"
    AUTOPILOT_PUBLISH = "AUTOPILOT_PUBLISH"
    AUTOPILOT_POST_PUBLISH_VERIFY = "AUTOPILOT_POST_PUBLISH_VERIFY"
    RELIABILITY_HEALTH_CHECK = "RELIABILITY_HEALTH_CHECK"
    RELIABILITY_INCIDENT_EVALUATE = "RELIABILITY_INCIDENT_EVALUATE"
    RELIABILITY_RECOVERY_RUN = "RELIABILITY_RECOVERY_RUN"
    RELIABILITY_RECOVERY_VERIFY = "RELIABILITY_RECOVERY_VERIFY"
    RELIABILITY_BACKUP_VERIFY = "RELIABILITY_BACKUP_VERIFY"
    RELIABILITY_DR_READINESS_CHECK = "RELIABILITY_DR_READINESS_CHECK"


JobHandler = Callable[[Session, DurableJob], dict[str, Any]]


class UnregisteredJobTypeError(ValueError):
    """Raised when an unrecognized job type is encountered."""

    pass


class NonRetryableJobError(Exception):
    """Raised when a job encounters a deterministic, non-transient failure."""

    pass


def default_workflow_run_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    """Execute an asynchronous workflow run."""
    payload = job.payload_json or {}
    run_id_raw = payload.get("run_id")
    if not run_id_raw:
        raise NonRetryableJobError("Missing required 'run_id' in WORKFLOW_RUN payload")

    try:
        run_id = UUID(str(run_id_raw))
    except (ValueError, TypeError) as exc:
        raise NonRetryableJobError(f"Invalid UUID for 'run_id': {run_id_raw}") from exc

    # Lazy import to avoid circular dependencies
    from app.modules.workflows.engine import WorkflowEngine
    from app.modules.workflows.repository import WorkflowRepository

    run = WorkflowEngine(WorkflowRepository(db)).execute_run(run_id)
    return {
        "run_id": str(run.id),
        "status": run.status.value,
        "completed_at": run.ended_at.isoformat() if run.ended_at else None,
    }


def default_event_dispatch_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    """Dispatch a domain event asynchronously."""
    payload = job.payload_json or {}
    event_id_raw = payload.get("event_id")
    if not event_id_raw:
        raise NonRetryableJobError("Missing required 'event_id' in EVENT_DISPATCH payload")

    from app.modules.events.bus import default_event_bus
    from app.modules.events.repository import EventRepository

    try:
        event_id = UUID(str(event_id_raw))
    except (ValueError, TypeError) as exc:
        raise NonRetryableJobError(f"Invalid UUID for 'event_id': {event_id_raw}") from exc

    event = EventRepository.get_event(db, event_id)
    if event is None:
        raise NonRetryableJobError(f"Domain event '{event_id}' not found")

    dispatched = default_event_bus.dispatch(db, event)
    return {
        "event_id": str(dispatched.id),
        "event_type": dispatched.event_type,
        "status": dispatched.status.value,
    }


def default_outbound_webhook_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    """Dispatch outbound webhook delivery asynchronously."""
    payload = job.payload_json or {}
    delivery_id_raw = payload.get("delivery_id")
    if not delivery_id_raw:
        # Generic payload notification
        return {
            "endpoint": payload.get("endpoint", "safe://internal"),
            "delivered": True,
            "status": "simulated_success",
        }

    from app.modules.events.models import OutboundWebhookDelivery
    try:
        delivery_id = UUID(str(delivery_id_raw))
        delivery = db.get(OutboundWebhookDelivery, delivery_id)
        if delivery is None:
            raise NonRetryableJobError(f"Delivery '{delivery_id}' not found")
        return {
            "delivery_id": str(delivery.id),
            "status": delivery.status.value,
        }
    except Exception as exc:
        if isinstance(exc, NonRetryableJobError):
            raise
        raise NonRetryableJobError(str(exc)) from exc


def default_report_generation_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    """Compile and generate reporting datasets safely."""
    payload = job.payload_json or {}
    report_type = payload.get("report_type", "summary")
    if payload.get("fail_transient"):
        raise RuntimeError("Transient reporting engine error")
    if payload.get("fail_permanent"):
        raise NonRetryableJobError("Invalid reporting schema specification")

    return {
        "report_type": report_type,
        "generated_rows": payload.get("row_count", 42),
        "artifact_id": f"rep-{job.id.hex[:8]}",
    }


def default_notification_event_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    """Send operational notification events."""
    payload = job.payload_json or {}
    channel = payload.get("channel", "broadcast_operations")
    if payload.get("fail_transient"):
        raise RuntimeError("Notification broker connection timeout")

    return {
        "channel": channel,
        "delivered": True,
        "message_id": f"notif-{job.id.hex[:8]}",
    }


def default_content_publish_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    """Publish media catalog content asynchronously."""
    payload = job.payload_json or {}
    content_id = payload.get("content_id", "content-default")
    if payload.get("fail_transient"):
        raise RuntimeError("Media catalog database lock timeout")

    return {
        "content_id": content_id,
        "published": True,
        "published_at": job.available_at.isoformat(),
    }


def default_distribution_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    """Multi-platform syndication and distribution dispatch."""
    payload = job.payload_json or {}
    targets = payload.get("targets", ["linear", "fast_channel"])
    if payload.get("fail_transient"):
        raise RuntimeError("CDN syndication ingest 503")

    return {
        "targets": targets,
        "status": "enqueued_for_syndication",
        "batches": len(targets),
    }


def default_media_processing_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    """Media transcoding and probe execution."""
    payload = job.payload_json or {}
    asset_id = payload.get("asset_id", "asset-1")
    if payload.get("fail_transient"):
        raise RuntimeError("Transcoder pipeline IO timeout")

    return {
        "asset_id": asset_id,
        "renditions": ["1080p", "720p", "480p"],
        "status": "ready",
    }


def default_ai_agent_run_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    """Execute one persisted AI agent run through the bounded control-plane engine."""
    run_id_raw = (job.payload_json or {}).get("agent_run_id")
    if not run_id_raw:
        raise NonRetryableJobError(
            "Missing required 'agent_run_id' in AI_AGENT_RUN payload"
        )
    try:
        run_id = UUID(str(run_id_raw))
    except (ValueError, TypeError) as exc:
        raise NonRetryableJobError("Invalid agent_run_id") from exc
    from app.modules.agents.engine import AgentExecutionEngine
    from app.modules.agents.models import AgentToolCall, ToolCallStatus
    from sqlalchemy import select

    engine = AgentExecutionEngine(db)
    approved_call = db.scalar(
        select(AgentToolCall)
        .where(
            AgentToolCall.agent_run_id == run_id,
            AgentToolCall.status == ToolCallStatus.APPROVED,
        )
        .order_by(AgentToolCall.created_at.desc())
    )
    run = (
        engine.resume_approved_tool(run_id, approved_call.id)
        if approved_call
        else engine.execute(run_id)
    )
    return {"agent_run_id": str(run.id), "status": run.status.value}


def default_autopilot_research_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    payload = job.payload_json or {}
    task_id = payload.get("research_task_id")
    if not task_id:
        raise NonRetryableJobError("Missing research_task_id")
    from app.modules.autopilot.service import AutopilotService

    task = AutopilotService(db).complete_research_task(UUID(str(task_id)))
    return {"research_task_id": str(task.id), "status": task.status.value}


def default_autopilot_passthrough_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    return {"status": "recorded", "payload": job.payload_json or {}}


def default_autopilot_publish_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    payload = job.payload_json or {}
    attempt_id = payload.get("attempt_id")
    if not attempt_id:
        raise NonRetryableJobError("Missing attempt_id")
    from app.modules.autopilot.service import AutopilotService

    attempt = AutopilotService(db).execute_publish_attempt(UUID(str(attempt_id)))
    return {"attempt_id": str(attempt.id), "status": attempt.status.value}


def default_autopilot_verify_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    payload = job.payload_json or {}
    attempt_id = payload.get("attempt_id")
    if not attempt_id:
        raise NonRetryableJobError("Missing attempt_id")
    from app.modules.autopilot.service import AutopilotService

    attempt = AutopilotService(db).verify_publication(UUID(str(attempt_id)))
    return {"attempt_id": str(attempt.id), "status": attempt.status.value}


def default_reliability_health_check_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    from app.modules.reliability.service import ReliabilityService

    payload = job.payload_json or {}
    correlation_id = payload.get("correlation_id")
    snapshot = ReliabilityService(db).trigger_health_check(correlation_id=correlation_id)
    return {
        "snapshot_id": str(snapshot.id),
        "overall_status": snapshot.overall_status.value,
        "health_score": snapshot.health_score,
    }


def default_reliability_incident_evaluate_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    payload = job.payload_json or {}
    incident_id = payload.get("incident_id")
    if not incident_id:
        raise NonRetryableJobError("Missing incident_id")
    from app.modules.reliability.service import ReliabilityService

    incident = ReliabilityService(db).get_incident(UUID(str(incident_id)))
    return {"incident_id": str(incident.id), "state": incident.state.value}


def default_reliability_recovery_run_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    payload = job.payload_json or {}
    run_id = payload.get("run_id")
    if not run_id:
        raise NonRetryableJobError("Missing run_id")
    from app.modules.reliability.service import ReliabilityService

    run = ReliabilityService(db).execute_recovery_run(UUID(str(run_id)))
    return {"run_id": str(run.id), "status": run.status.value}


def default_reliability_recovery_verify_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    payload = job.payload_json or {}
    run_id = payload.get("run_id")
    if not run_id:
        raise NonRetryableJobError("Missing run_id")
    from app.modules.reliability.service import ReliabilityService

    run = ReliabilityService(db).verify_recovery(UUID(str(run_id)))
    return {"run_id": str(run.id), "verification_status": run.verification_status}


def default_reliability_backup_verify_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    payload = job.payload_json or {}
    backup_id = payload.get("backup_id")
    if not backup_id:
        raise NonRetryableJobError("Missing backup_id")
    from app.modules.reliability.service import ReliabilityService

    record = ReliabilityService(db).verify_backup(UUID(str(backup_id)))
    return {"backup_id": str(record.id), "verification_result": record.verification_result}


def default_reliability_dr_readiness_check_handler(db: Session, job: DurableJob) -> dict[str, Any]:
    from app.modules.reliability.service import ReliabilityService

    readiness = ReliabilityService(db).evaluate_dr_readiness()
    return {"overall_status": readiness.overall_status.value}


class JobTypeRegistry:
    """Registry maintaining allowlisted safe executable job types."""

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(SafeJobType.WORKFLOW_RUN, default_workflow_run_handler)
        self.register(SafeJobType.EVENT_DISPATCH, default_event_dispatch_handler)
        self.register(
            SafeJobType.OUTBOUND_WEBHOOK_DELIVERY, default_outbound_webhook_handler
        )
        self.register(SafeJobType.REPORT_GENERATION, default_report_generation_handler)
        self.register(SafeJobType.NOTIFICATION_EVENT, default_notification_event_handler)
        self.register(
            SafeJobType.CONTENT_PUBLISH_REQUEST, default_content_publish_handler
        )
        self.register(SafeJobType.DISTRIBUTION_REQUEST, default_distribution_handler)
        self.register(
            SafeJobType.MEDIA_PROCESSING_REQUEST, default_media_processing_handler
        )
        self.register(SafeJobType.AI_AGENT_RUN, default_ai_agent_run_handler)
        self.register(SafeJobType.AUTOPILOT_RESEARCH, default_autopilot_research_handler)
        self.register(
            SafeJobType.AUTOPILOT_SCRIPT_GENERATION,
            default_autopilot_passthrough_handler,
        )
        self.register(
            SafeJobType.AUTOPILOT_PRODUCTION_PLAN,
            default_autopilot_passthrough_handler,
        )
        self.register(
            SafeJobType.AUTOPILOT_ASSET_PREPARATION,
            default_autopilot_passthrough_handler,
        )
        self.register(SafeJobType.AUTOPILOT_PUBLISH, default_autopilot_publish_handler)
        self.register(
            SafeJobType.AUTOPILOT_POST_PUBLISH_VERIFY,
            default_autopilot_verify_handler,
        )
        self.register(
            SafeJobType.RELIABILITY_HEALTH_CHECK,
            default_reliability_health_check_handler,
        )
        self.register(
            SafeJobType.RELIABILITY_INCIDENT_EVALUATE,
            default_reliability_incident_evaluate_handler,
        )
        self.register(
            SafeJobType.RELIABILITY_RECOVERY_RUN,
            default_reliability_recovery_run_handler,
        )
        self.register(
            SafeJobType.RELIABILITY_RECOVERY_VERIFY,
            default_reliability_recovery_verify_handler,
        )
        self.register(
            SafeJobType.RELIABILITY_BACKUP_VERIFY,
            default_reliability_backup_verify_handler,
        )
        self.register(
            SafeJobType.RELIABILITY_DR_READINESS_CHECK,
            default_reliability_dr_readiness_check_handler,
        )

    def register(self, job_type: str, handler: JobHandler) -> None:
        # Check against allowlist enum values
        valid_types = {t.value for t in SafeJobType}
        if job_type not in valid_types:
            raise UnregisteredJobTypeError(
                f"Job type '{job_type}' is not an allowlisted safe job type"
            )
        self._handlers[job_type] = handler

    def is_registered(self, job_type: str) -> bool:
        return job_type in self._handlers

    def get_handler(self, job_type: str) -> JobHandler | None:
        return self._handlers.get(job_type)

    def list_types(
        self, include_autopilot: bool = False, include_reliability: bool = False
    ) -> dict[str, str]:
        """Return {job_type: description} for all registered handlers."""
        hidden_prefixes: list[str] = []
        if not include_autopilot:
            hidden_prefixes.append("AUTOPILOT_")
        if not include_reliability:
            hidden_prefixes.append("RELIABILITY_")
        return {
            t.value: t.name.replace("_", " ").title()
            for t in SafeJobType
            if t.value in self._handlers
            and not any(t.value.startswith(prefix) for prefix in hidden_prefixes)
        }

    def execute(self, db: Session, job: DurableJob) -> dict[str, Any]:
        handler = self.get_handler(job.job_type)
        if handler is None:
            raise UnregisteredJobTypeError(
                f"Unknown or unregistered job type: '{job.job_type}'"
            )
        return handler(db, job)


# Global default registry instance
default_job_registry = JobTypeRegistry()

# Alias for modules that import 'job_registry' directly
job_registry = default_job_registry
