"""Service layer coordinating repositories, engine, queue, and audit logs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.modules.workflows.engine import WorkflowEngine, sanitize_metadata
from app.modules.workflows.models import (
    Workflow,
    WorkflowAuditAction,
    WorkflowAuditLog,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowSchedule,
    WorkflowStatus,
    WorkflowStepDefinition,
    WorkflowStepExecution,
    WorkflowStepStatus,
    WorkflowTrigger,
    WorkflowTriggerType,
)
from app.modules.workflows.queue import WorkflowQueue, default_workflow_queue
from app.modules.workflows.repository import WorkflowRepository
from app.modules.workflows.schemas import (
    WorkflowCreate,
    WorkflowScheduleCreate,
    WorkflowTriggerCreate,
    WorkflowUpdate,
)


class WorkflowService:
    """Service handling workflow lifecycle, run dispatching, and queue interactions."""

    def __init__(
        self,
        repo: WorkflowRepository,
        queue: WorkflowQueue = default_workflow_queue,
        engine: WorkflowEngine | None = None,
    ) -> None:
        self.repo = repo
        self.queue = queue
        self.engine = engine or WorkflowEngine(repo)

    # 1. Workflow Management
    def create_workflow(self, payload: WorkflowCreate, user_id: int | None = None) -> Workflow:
        workflow = Workflow(
            name=payload.name,
            description=payload.description,
            workflow_type=payload.workflow_type,
            status=WorkflowStatus.DRAFT,
            is_enabled=True,
            timeout_seconds=payload.timeout_seconds,
            retry_policy_json=payload.retry_policy.model_dump() if payload.retry_policy else None,
            created_by_user_id=user_id,
        )
        steps = [
            WorkflowStepDefinition(
                step_order=s.step_order,
                name=s.name,
                step_type=s.step_type,
                config_json=sanitize_metadata(s.config_json),
                is_required=s.is_required,
                timeout_seconds=s.timeout_seconds,
                max_retries=s.max_retries,
                retry_delay_seconds=s.retry_delay_seconds,
                backoff_multiplier=s.backoff_multiplier,
            )
            for s in payload.steps
        ]
        audit = WorkflowAuditLog(
            action=WorkflowAuditAction.WORKFLOW_CREATED,
            actor_user_id=user_id,
            metadata_json={"name": payload.name, "step_count": len(steps)},
        )
        return self.repo.create_workflow(workflow, steps, audit)

    def get_workflow(self, workflow_id: UUID) -> Workflow:
        workflow = self.repo.get_workflow(workflow_id)
        if workflow is None:
            raise ValueError(f"Workflow {workflow_id} not found")
        return workflow

    def list_workflows(
        self,
        status: WorkflowStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Workflow]:
        return self.repo.list_workflows(status=status, limit=limit, offset=offset)

    def update_workflow(
        self,
        workflow_id: UUID,
        payload: WorkflowUpdate,
        user_id: int | None = None,
    ) -> Workflow:
        workflow = self.get_workflow(workflow_id)
        if payload.name is not None:
            workflow.name = payload.name
        if payload.description is not None:
            workflow.description = payload.description
        if payload.workflow_type is not None:
            workflow.workflow_type = payload.workflow_type
        if payload.is_enabled is not None:
            workflow.is_enabled = payload.is_enabled
        if payload.timeout_seconds is not None:
            workflow.timeout_seconds = payload.timeout_seconds
        if payload.retry_policy is not None:
            workflow.retry_policy_json = payload.retry_policy.model_dump()

        workflow.version += 1
        workflow.updated_at = datetime.now(UTC)

        audit = WorkflowAuditLog(
            workflow_id=workflow.id,
            action=WorkflowAuditAction.WORKFLOW_UPDATED,
            actor_user_id=user_id,
            metadata_json={"new_version": workflow.version},
        )
        return self.repo.update_workflow(workflow, audit)

    def activate_workflow(self, workflow_id: UUID, user_id: int | None = None) -> Workflow:
        workflow = self.get_workflow(workflow_id)
        if workflow.status == WorkflowStatus.ARCHIVED:
            raise ValueError("Archived workflows cannot be activated")
        if not workflow.steps:
            raise ValueError("Workflow must contain at least one step before activation")

        workflow.status = WorkflowStatus.ACTIVE
        workflow.is_enabled = True
        workflow.updated_at = datetime.now(UTC)

        audit = WorkflowAuditLog(
            workflow_id=workflow.id,
            action=WorkflowAuditAction.WORKFLOW_ACTIVATED,
            actor_user_id=user_id,
            metadata_json={"status": WorkflowStatus.ACTIVE.value},
        )
        return self.repo.update_workflow(workflow, audit)

    def pause_workflow(self, workflow_id: UUID, user_id: int | None = None) -> Workflow:
        workflow = self.get_workflow(workflow_id)
        if workflow.status != WorkflowStatus.ACTIVE:
            raise ValueError(f"Cannot pause workflow in '{workflow.status.value}' state")

        workflow.status = WorkflowStatus.PAUSED
        workflow.updated_at = datetime.now(UTC)

        audit = WorkflowAuditLog(
            workflow_id=workflow.id,
            action=WorkflowAuditAction.WORKFLOW_PAUSED,
            actor_user_id=user_id,
            metadata_json={"status": WorkflowStatus.PAUSED.value},
        )
        return self.repo.update_workflow(workflow, audit)

    # 2. Workflow Run Dispatch & Execution
    def trigger_workflow_run(
        self,
        workflow_id: UUID,
        input_metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        trigger_type: WorkflowTriggerType = WorkflowTriggerType.MANUAL,
        trigger_source: str | None = None,
        actor_user_id: int | None = None,
        execute_now: bool = True,
    ) -> WorkflowRun:
        workflow = self.get_workflow(workflow_id)
        if workflow.status != WorkflowStatus.ACTIVE:
            raise ValueError(f"Cannot run workflow in '{workflow.status.value}' state")
        if not workflow.is_enabled:
            raise ValueError("Workflow is disabled")

        resolved_idempotency_key = idempotency_key or f"wf-run-{uuid4().hex}"

        # Idempotency check: return existing run if key matches
        existing_run = self.repo.get_workflow_run_by_idempotency(workflow_id, resolved_idempotency_key)
        if existing_run is not None:
            return existing_run

        sanitized_input = sanitize_metadata(input_metadata or {})
        run = WorkflowRun(
            workflow_id=workflow.id,
            workflow_version=workflow.version,
            status=WorkflowRunStatus.QUEUED,
            trigger_type=trigger_type,
            trigger_source=trigger_source or "operator_api",
            idempotency_key=resolved_idempotency_key,
            actor_user_id=actor_user_id,
            input_metadata_json=sanitized_input,
            current_step_order=1,
            retry_count=0,
        )

        steps = [
            WorkflowStepExecution(
                step_definition_id=sd.id,
                step_order=sd.step_order,
                step_name=sd.name,
                step_type=sd.step_type,
                status=WorkflowStepStatus.PENDING,
                idempotency_key=f"{resolved_idempotency_key}-step-{sd.step_order}",
                timeout_seconds=sd.timeout_seconds,
                max_retries=sd.max_retries,
                retry_delay_seconds=sd.retry_delay_seconds,
                backoff_multiplier=sd.backoff_multiplier,
                is_required=sd.is_required,
                input_json=sd.config_json,
            )
            for sd in sorted(workflow.steps, key=lambda s: s.step_order)
        ]

        audit = WorkflowAuditLog(
            workflow_id=workflow.id,
            action=WorkflowAuditAction.RUN_QUEUED,
            actor_user_id=actor_user_id,
            metadata_json={"trigger_type": trigger_type.value, "idempotency_key": resolved_idempotency_key},
        )
        created_run = self.repo.create_workflow_run(run, steps, audit)

        # Enqueue in queue abstraction
        self.queue.enqueue(created_run.id)

        if execute_now:
            return self.engine.execute_run(created_run.id)
        return created_run

    def get_workflow_run(self, run_id: UUID) -> WorkflowRun:
        run = self.repo.get_workflow_run(run_id)
        if run is None:
            raise ValueError(f"Workflow run {run_id} not found")
        return run

    def list_workflow_runs(
        self,
        workflow_id: UUID | None = None,
        status: WorkflowRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowRun]:
        return self.repo.list_workflow_runs(workflow_id=workflow_id, status=status, limit=limit, offset=offset)

    def cancel_workflow_run(
        self,
        run_id: UUID,
        reason: str | None = None,
        actor_user_id: int | None = None,
    ) -> WorkflowRun:
        return self.engine.cancel_run(run_id, reason=reason, actor_user_id=actor_user_id)

    # 3. Manual Approval
    def approve_step(
        self,
        run_id: UUID,
        step_id: UUID,
        notes: str | None = None,
        actor_user_id: int | None = None,
    ) -> WorkflowRun:
        return self.engine.resume_run_after_approval(
            run_id=run_id,
            step_id=step_id,
            approved=True,
            notes=notes,
            actor_user_id=actor_user_id,
        )

    def reject_step(
        self,
        run_id: UUID,
        step_id: UUID,
        notes: str | None = None,
        actor_user_id: int | None = None,
    ) -> WorkflowRun:
        return self.engine.resume_run_after_approval(
            run_id=run_id,
            step_id=step_id,
            approved=False,
            notes=notes,
            actor_user_id=actor_user_id,
        )

    # 4. Triggers & Schedules
    def create_trigger(self, workflow_id: UUID, payload: WorkflowTriggerCreate) -> WorkflowTrigger:
        self.get_workflow(workflow_id)
        trigger = WorkflowTrigger(
            workflow_id=workflow_id,
            trigger_type=payload.trigger_type,
            name=payload.name,
            event_pattern=payload.event_pattern,
            schedule_cron=payload.schedule_cron,
            schedule_timezone=payload.schedule_timezone,
            is_enabled=payload.is_enabled,
            metadata_json=sanitize_metadata(payload.metadata_json),
        )
        return self.repo.create_trigger(trigger)

    def list_triggers(self, workflow_id: UUID) -> list[WorkflowTrigger]:
        self.get_workflow(workflow_id)
        return self.repo.list_triggers(workflow_id)

    def create_schedule(self, workflow_id: UUID, payload: WorkflowScheduleCreate) -> WorkflowSchedule:
        self.get_workflow(workflow_id)
        schedule = WorkflowSchedule(
            workflow_id=workflow_id,
            schedule_type=payload.schedule_type,
            cron_expression=payload.cron_expression,
            next_run_at=payload.next_run_at,
            timezone=payload.timezone,
            is_enabled=payload.is_enabled,
        )
        return self.repo.create_schedule(schedule)

    def list_schedules(self, workflow_id: UUID | None = None) -> list[WorkflowSchedule]:
        return self.repo.list_schedules(workflow_id)

    # 5. Metrics & Audits
    def get_metrics_summary(self) -> dict[str, Any]:
        return self.repo.get_metrics_summary()

    def list_audit_logs(
        self,
        workflow_id: UUID | None = None,
        run_id: UUID | None = None,
        limit: int = 50,
    ) -> list[WorkflowAuditLog]:
        return self.repo.list_audit_logs(workflow_id=workflow_id, run_id=run_id, limit=limit)
