"""Explicit safe AI tool registry and policy-enforced execution."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.events.schemas import EventPublishRequest
from app.modules.events.security import sanitize_payload
from app.modules.events.service import EventService
from app.modules.jobs.queue import DatabaseJobQueue
from app.modules.jobs.registry import default_job_registry
from app.modules.workflows.models import WorkflowStatus, WorkflowTriggerType
from app.modules.workflows.repository import WorkflowRepository
from app.modules.workflows.service import WorkflowService


class SafeAgentTool(StrEnum):
    READ_CONTENT_METADATA = "READ_CONTENT_METADATA"
    READ_CONTENT_ITEM = "READ_CONTENT_ITEM"
    SEARCH_INTERNAL_CONTENT = "SEARCH_INTERNAL_CONTENT"
    CREATE_CONTENT_DRAFT = "CREATE_CONTENT_DRAFT"
    UPDATE_CONTENT_DRAFT = "UPDATE_CONTENT_DRAFT"
    REQUEST_WORKFLOW_RUN = "REQUEST_WORKFLOW_RUN"
    READ_WORKFLOW_STATUS = "READ_WORKFLOW_STATUS"
    EMIT_INTERNAL_EVENT = "EMIT_INTERNAL_EVENT"
    ENQUEUE_APPROVED_JOB = "ENQUEUE_APPROVED_JOB"
    REQUEST_HUMAN_APPROVAL = "REQUEST_HUMAN_APPROVAL"


ToolHandler = Callable[[Session, dict[str, Any], dict[str, Any]], dict[str, Any]]


class ToolRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {
            SafeAgentTool.READ_CONTENT_METADATA: self._read_content,
            SafeAgentTool.READ_CONTENT_ITEM: self._read_content,
            SafeAgentTool.SEARCH_INTERNAL_CONTENT: self._search,
            SafeAgentTool.CREATE_CONTENT_DRAFT: self._draft,
            SafeAgentTool.UPDATE_CONTENT_DRAFT: self._draft,
            SafeAgentTool.REQUEST_WORKFLOW_RUN: self._workflow,
            SafeAgentTool.READ_WORKFLOW_STATUS: self._workflow_status,
            SafeAgentTool.EMIT_INTERNAL_EVENT: self._event,
            SafeAgentTool.ENQUEUE_APPROVED_JOB: self._job,
            SafeAgentTool.REQUEST_HUMAN_APPROVAL: self._approval,
        }

    def names(self) -> list[str]:
        return sorted(str(name) for name in self._handlers)

    def execute(
        self,
        db: Session,
        tool_name: str,
        arguments: dict[str, Any],
        control: dict[str, Any],
    ) -> dict[str, Any]:
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise ValueError(f"Unknown tool '{tool_name}'")
        return cast(
            dict[str, Any],
            sanitize_payload(handler(db, sanitize_payload(arguments), control)),
        )

    @staticmethod
    def _read_content(
        db: Session, args: dict[str, Any], control: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "content_id": args.get("content_id"),
            "found": False,
            "source": "internal_catalog",
        }

    @staticmethod
    def _search(
        db: Session, args: dict[str, Any], control: dict[str, Any]
    ) -> dict[str, Any]:
        return {"query": str(args.get("query", ""))[:200], "results": []}

    @staticmethod
    def _draft(
        db: Session, args: dict[str, Any], control: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "draft_id": str(args.get("draft_id") or f"draft-{control['run_id']}"),
            "status": "draft",
        }

    @staticmethod
    def _workflow(
        db: Session, args: dict[str, Any], control: dict[str, Any]
    ) -> dict[str, Any]:
        workflow_id = str(args.get("workflow_id", ""))
        if workflow_id not in control.get("allowed_workflow_ids", []):
            raise PermissionError("Workflow is not allowlisted by tool policy")
        workflow = WorkflowRepository(db).get_workflow(UUID(workflow_id))
        if workflow is None or workflow.status != WorkflowStatus.ACTIVE:
            raise ValueError("Workflow is not active")
        run = WorkflowService(WorkflowRepository(db)).trigger_workflow_run(
            workflow.id,
            input_metadata=args.get("input", {}),
            idempotency_key=f"agent-{control['idempotency_key']}-workflow-{workflow.id}",
            trigger_type=WorkflowTriggerType.INTERNAL_EVENT,
            trigger_source="ai_agent",
            actor_user_id=control.get("actor_user_id"),
            execute_now=False,
        )
        return {"workflow_run_id": str(run.id), "status": run.status.value}

    @staticmethod
    def _workflow_status(
        db: Session, args: dict[str, Any], control: dict[str, Any]
    ) -> dict[str, Any]:
        run = WorkflowRepository(db).get_workflow_run(
            UUID(str(args.get("workflow_run_id")))
        )
        if run is None:
            raise ValueError("Workflow run not found")
        return {"workflow_run_id": str(run.id), "status": run.status.value}

    @staticmethod
    def _event(
        db: Session, args: dict[str, Any], control: dict[str, Any]
    ) -> dict[str, Any]:
        event_type = str(args.get("event_type", ""))
        if not any(
            event_type.startswith(prefix)
            for prefix in control.get("allowed_event_namespaces", [])
        ):
            raise PermissionError("Event namespace is not allowlisted")
        event = EventService().publish_event(
            db,
            EventPublishRequest(
                event_type=event_type,
                source="ai_agent_control_plane",
                correlation_id=control["correlation_id"],
                causation_id=control.get("causation_id"),
                idempotency_key=f"agent-{control['idempotency_key']}-event-{event_type}",
                payload=args.get("payload", {}),
            ),
            actor_user_id=control.get("actor_user_id"),
        )
        return {"event_id": str(event.id), "event_type": event.event_type}

    @staticmethod
    def _job(
        db: Session, args: dict[str, Any], control: dict[str, Any]
    ) -> dict[str, Any]:
        job_type = str(args.get("job_type", ""))
        if job_type not in control.get(
            "allowed_job_types", []
        ) or not default_job_registry.is_registered(job_type):
            raise PermissionError("Job type is not allowlisted")
        if job_type == "AI_AGENT_RUN":
            raise PermissionError("Agent runs cannot recursively enqueue agents")
        job = DatabaseJobQueue().enqueue(
            db,
            job_type=job_type,
            payload=args.get("payload", {}),
            queue_name="default",
            idempotency_key=f"agent-{control['idempotency_key']}-job-{job_type}",
            correlation_id=control["correlation_id"],
            causation_id=control.get("causation_id"),
            actor_user_id=control.get("actor_user_id"),
        )
        return {"job_id": str(job.id), "status": job.status.value}

    @staticmethod
    def _approval(
        db: Session, args: dict[str, Any], control: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "requested": True,
            "reason": str(args.get("reason", "Human decision requested"))[:500],
        }


tool_registry = ToolRegistry()
