"""Data access layer for Workflow Orchestration & Job Execution Platform."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.modules.workflows.models import (
    Workflow,
    WorkflowAuditLog,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowSchedule,
    WorkflowStatus,
    WorkflowStepDefinition,
    WorkflowStepExecution,
    WorkflowStepStatus,
    WorkflowTrigger,
)


class WorkflowRepository:
    """Repository handling persistence for workflows, runs, steps, triggers, and audits."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # 1. Workflows
    def create_workflow(
        self,
        workflow: Workflow,
        steps: list[WorkflowStepDefinition],
        audit: WorkflowAuditLog | None = None,
    ) -> Workflow:
        self.db.add(workflow)
        self.db.flush()
        for step in steps:
            step.workflow_id = workflow.id
            self.db.add(step)
        if audit is not None:
            audit.workflow_id = workflow.id
            self.db.add(audit)
        self.db.commit()
        self.db.refresh(workflow)
        return workflow

    def get_workflow(self, workflow_id: UUID) -> Workflow | None:
        return (
            self.db.query(Workflow)
            .options(joinedload(Workflow.steps))
            .filter(Workflow.id == workflow_id)
            .one_or_none()
        )

    def list_workflows(
        self,
        status: WorkflowStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Workflow]:
        query = self.db.query(Workflow).options(joinedload(Workflow.steps))
        if status is not None:
            query = query.filter(Workflow.status == status)
        return query.order_by(Workflow.created_at.desc()).offset(offset).limit(limit).all()

    def update_workflow(
        self,
        workflow: Workflow,
        audit: WorkflowAuditLog | None = None,
    ) -> Workflow:
        self.db.add(workflow)
        if audit is not None:
            self.db.add(audit)
        self.db.commit()
        self.db.refresh(workflow)
        return workflow

    # 2. Workflow Runs
    def create_workflow_run(
        self,
        run: WorkflowRun,
        steps: list[WorkflowStepExecution],
        audit: WorkflowAuditLog | None = None,
    ) -> WorkflowRun:
        self.db.add(run)
        self.db.flush()
        for step in steps:
            step.run_id = run.id
            self.db.add(step)
        if audit is not None:
            audit.run_id = run.id
            self.db.add(audit)
        self.db.commit()
        self.db.refresh(run)
        return run

    def get_workflow_run(self, run_id: UUID) -> WorkflowRun | None:
        return (
            self.db.query(WorkflowRun)
            .options(
                joinedload(WorkflowRun.step_executions),
                joinedload(WorkflowRun.workflow).joinedload(Workflow.steps),
            )
            .filter(WorkflowRun.id == run_id)
            .one_or_none()
        )

    def get_workflow_run_by_idempotency(
        self,
        workflow_id: UUID,
        idempotency_key: str,
    ) -> WorkflowRun | None:
        return (
            self.db.query(WorkflowRun)
            .options(joinedload(WorkflowRun.step_executions))
            .filter(
                WorkflowRun.workflow_id == workflow_id,
                WorkflowRun.idempotency_key == idempotency_key,
            )
            .one_or_none()
        )

    def list_workflow_runs(
        self,
        workflow_id: UUID | None = None,
        status: WorkflowRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowRun]:
        query = self.db.query(WorkflowRun).options(joinedload(WorkflowRun.step_executions))
        if workflow_id is not None:
            query = query.filter(WorkflowRun.workflow_id == workflow_id)
        if status is not None:
            query = query.filter(WorkflowRun.status == status)
        return query.order_by(WorkflowRun.created_at.desc()).offset(offset).limit(limit).all()

    def update_workflow_run(
        self,
        run: WorkflowRun,
        audit: WorkflowAuditLog | None = None,
    ) -> WorkflowRun:
        self.db.add(run)
        if audit is not None:
            self.db.add(audit)
        self.db.commit()
        self.db.refresh(run)
        return run

    # 3. Steps
    def get_step_execution(self, step_id: UUID) -> WorkflowStepExecution | None:
        return self.db.query(WorkflowStepExecution).filter(WorkflowStepExecution.id == step_id).one_or_none()

    def get_step_execution_by_order(self, run_id: UUID, step_order: int) -> WorkflowStepExecution | None:
        return (
            self.db.query(WorkflowStepExecution)
            .filter(
                WorkflowStepExecution.run_id == run_id,
                WorkflowStepExecution.step_order == step_order,
            )
            .one_or_none()
        )

    def update_step_execution(
        self,
        step: WorkflowStepExecution,
        audit: WorkflowAuditLog | None = None,
    ) -> WorkflowStepExecution:
        self.db.add(step)
        if audit is not None:
            self.db.add(audit)
        self.db.commit()
        self.db.refresh(step)
        return step

    # 4. Triggers & Schedules
    def create_trigger(self, trigger: WorkflowTrigger) -> WorkflowTrigger:
        self.db.add(trigger)
        self.db.commit()
        self.db.refresh(trigger)
        return trigger

    def list_triggers(self, workflow_id: UUID) -> list[WorkflowTrigger]:
        return (
            self.db.query(WorkflowTrigger)
            .filter(WorkflowTrigger.workflow_id == workflow_id)
            .order_by(WorkflowTrigger.created_at.asc())
            .all()
        )

    def create_schedule(self, schedule: WorkflowSchedule) -> WorkflowSchedule:
        self.db.add(schedule)
        self.db.commit()
        self.db.refresh(schedule)
        return schedule

    def list_schedules(self, workflow_id: UUID | None = None) -> list[WorkflowSchedule]:
        query = self.db.query(WorkflowSchedule)
        if workflow_id is not None:
            query = query.filter(WorkflowSchedule.workflow_id == workflow_id)
        return query.order_by(WorkflowSchedule.created_at.desc()).all()

    # 5. Audits
    def create_audit_log(self, audit: WorkflowAuditLog) -> WorkflowAuditLog:
        self.db.add(audit)
        self.db.commit()
        self.db.refresh(audit)
        return audit

    def list_audit_logs(
        self,
        workflow_id: UUID | None = None,
        run_id: UUID | None = None,
        limit: int = 50,
    ) -> list[WorkflowAuditLog]:
        query = self.db.query(WorkflowAuditLog)
        if workflow_id is not None:
            query = query.filter(WorkflowAuditLog.workflow_id == workflow_id)
        if run_id is not None:
            query = query.filter(WorkflowAuditLog.run_id == run_id)
        return query.order_by(WorkflowAuditLog.created_at.desc()).limit(limit).all()

    # 6. Metrics
    def get_metrics_summary(self) -> dict[str, Any]:
        run_counts = (
            self.db.query(WorkflowRun.status, func.count(WorkflowRun.id))
            .group_by(WorkflowRun.status)
            .all()
        )
        counts_by_status = {status.value: count for status, count in run_counts}

        total_retries = (
            self.db.query(func.coalesce(func.sum(WorkflowRun.retry_count), 0))
            .scalar()
        ) or 0

        pending_approvals = (
            self.db.query(func.count(WorkflowStepExecution.id))
            .filter(WorkflowStepExecution.status == WorkflowStepStatus.WAITING)
            .scalar()
        ) or 0

        # Calculate average duration for finished runs
        finished_runs = (
            self.db.query(WorkflowRun)
            .filter(
                WorkflowRun.started_at.isnot(None),
                WorkflowRun.ended_at.isnot(None),
            )
            .limit(100)
            .all()
        )
        durations = [
            (run.ended_at - run.started_at).total_seconds()
            for run in finished_runs
            if run.started_at and run.ended_at and run.ended_at >= run.started_at
        ]
        avg_duration = float(sum(durations) / len(durations)) if durations else 0.0

        total_runs = sum(counts_by_status.values())

        return {
            "runs_queued": counts_by_status.get(WorkflowRunStatus.QUEUED.value, 0),
            "runs_running": counts_by_status.get(WorkflowRunStatus.RUNNING.value, 0),
            "runs_waiting": counts_by_status.get(WorkflowRunStatus.WAITING.value, 0),
            "runs_succeeded": counts_by_status.get(WorkflowRunStatus.SUCCEEDED.value, 0),
            "runs_failed": counts_by_status.get(WorkflowRunStatus.FAILED.value, 0),
            "runs_cancelled": counts_by_status.get(WorkflowRunStatus.CANCELLED.value, 0),
            "total_runs": total_runs,
            "average_duration_seconds": round(avg_duration, 2),
            "total_retries": int(total_retries),
            "pending_approvals": int(pending_approvals),
        }
