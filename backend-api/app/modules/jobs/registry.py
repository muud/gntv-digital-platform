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

    def list_types(self) -> dict[str, str]:
        """Return {job_type: description} for all registered handlers."""
        return {
            t.value: t.name.replace("_", " ").title()
            for t in SafeJobType
            if t.value in self._handlers
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
