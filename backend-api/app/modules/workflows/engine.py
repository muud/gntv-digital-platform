"""Workflow Execution Engine for Module 8 Sprint 8.1.

Executes workflow steps deterministically, manages retry policies,
enforces security boundaries (no arbitrary shell or Python execution),
sanitizes sensitive data, and handles manual approval steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re
from typing import Any
from uuid import UUID

from app.modules.workflows.models import (
    WorkflowAuditAction,
    WorkflowAuditLog,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowStatus,
    WorkflowStepStatus,
    WorkflowStepType,
)
from app.modules.workflows.repository import WorkflowRepository


class WorkflowExecutionError(Exception):
    """Base error for workflow step execution failures."""

    def __init__(self, message: str, retryable: bool = False, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.details = details or {}


class NonRetryableStepError(WorkflowExecutionError):
    """Error indicating a permanent failure that should not be retried."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, retryable=False, details=details)


class RetryableStepError(WorkflowExecutionError):
    """Error indicating a transient failure suitable for retry."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, retryable=True, details=details)


SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|secret|token|api_key|private_key|auth|bearer|credential|card|cvv|account_number|iban)",
    re.IGNORECASE,
)


def sanitize_metadata(data: Any) -> Any:
    """Recursively sanitize metadata to guarantee no secrets or credentials are saved."""
    if isinstance(data, dict):
        cleaned: dict[str, Any] = {}
        for k, v in data.items():
            if SENSITIVE_KEY_PATTERN.search(str(k)):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = sanitize_metadata(v)
        return cleaned
    elif isinstance(data, list):
        return [sanitize_metadata(item) for item in data]
    return data


@dataclass
class StepContext:
    run_id: UUID
    step_id: UUID
    step_order: int
    step_type: WorkflowStepType
    config: dict[str, Any]
    input_data: dict[str, Any]
    previous_outputs: dict[int, dict[str, Any]]


class StepHandler:
    """Registry of safe, sandboxed internal step handlers."""

    @staticmethod
    def execute(step_type: WorkflowStepType, context: StepContext) -> tuple[WorkflowStepStatus, dict[str, Any]]:
        """Dispatch to the appropriate safe handler. Strictly disallows shell or eval commands."""
        match step_type:
            case WorkflowStepType.HTTP_INTERNAL:
                return StepHandler._handle_http_internal(context)
            case WorkflowStepType.CONTENT_VALIDATE:
                return StepHandler._handle_content_validate(context)
            case WorkflowStepType.CONTENT_PUBLISH_REQUEST:
                return StepHandler._handle_content_publish_request(context)
            case WorkflowStepType.DISTRIBUTION_REQUEST:
                return StepHandler._handle_distribution_request(context)
            case WorkflowStepType.REPORT_GENERATION:
                return StepHandler._handle_report_generation(context)
            case WorkflowStepType.NOTIFICATION_EVENT:
                return StepHandler._handle_notification_event(context)
            case WorkflowStepType.MANUAL_APPROVAL:
                return StepHandler._handle_manual_approval(context)
            case WorkflowStepType.DELAY:
                return StepHandler._handle_delay(context)
            case WorkflowStepType.CONDITIONAL:
                return StepHandler._handle_conditional(context)
            case _:
                raise NonRetryableStepError(f"Unsupported workflow step type: {step_type}")

    @staticmethod
    def _handle_http_internal(context: StepContext) -> tuple[WorkflowStepStatus, dict[str, Any]]:
        endpoint = context.config.get("endpoint", "")
        method = context.config.get("method", "GET").upper()

        # Security check: Internal endpoints only (loopback / internal routes)
        if not endpoint.startswith("/api/v1/"):
            raise NonRetryableStepError(
                "HTTP_INTERNAL step restricted to internal /api/v1/ service paths only",
                details={"provided_endpoint": endpoint},
            )

        # Disallow arbitrary external URLs or protocols
        if any(endpoint.startswith(p) for p in ["http://", "https://", "ftp://", "file://"]):
            raise NonRetryableStepError("External URLs are prohibited in HTTP_INTERNAL steps")

        return WorkflowStepStatus.SUCCEEDED, {
            "status_code": 200,
            "endpoint": endpoint,
            "method": method,
            "simulated": True,
            "acknowledged_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _handle_content_validate(context: StepContext) -> tuple[WorkflowStepStatus, dict[str, Any]]:
        content_id = context.input_data.get("content_id") or context.config.get("content_id")
        content_type = context.input_data.get("content_type") or context.config.get("content_type", "vod")

        if not content_id:
            raise NonRetryableStepError("content_id is required for CONTENT_VALIDATE step")

        # Simulate metadata validation check
        simulate_failure = context.config.get("simulate_failure", False)
        if simulate_failure:
            is_retryable = context.config.get("simulate_retryable", False)
            if is_retryable:
                raise RetryableStepError("Simulated transient validation failure")
            raise NonRetryableStepError(f"Content validation failed for ID: {content_id}")

        return WorkflowStepStatus.SUCCEEDED, {
            "content_id": str(content_id),
            "content_type": content_type,
            "validation_passed": True,
            "format": "HLS/DASH",
            "checked_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _handle_content_publish_request(context: StepContext) -> tuple[WorkflowStepStatus, dict[str, Any]]:
        content_id = context.input_data.get("content_id") or context.config.get("content_id")
        channels = context.config.get("channels", ["default"])

        if not content_id:
            raise NonRetryableStepError("content_id is required for CONTENT_PUBLISH_REQUEST step")

        return WorkflowStepStatus.SUCCEEDED, {
            "content_id": str(content_id),
            "channels": channels,
            "publication_status": "published",
            "published_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _handle_distribution_request(context: StepContext) -> tuple[WorkflowStepStatus, dict[str, Any]]:
        destinations = context.config.get("destinations", ["default_distribution_target"])
        return WorkflowStepStatus.SUCCEEDED, {
            "destinations": destinations,
            "sync_enqueued": True,
            "job_count": len(destinations),
            "enqueued_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _handle_report_generation(context: StepContext) -> tuple[WorkflowStepStatus, dict[str, Any]]:
        report_type = context.config.get("report_type", "usage_summary")
        return WorkflowStepStatus.SUCCEEDED, {
            "report_type": report_type,
            "status": "completed",
            "row_count": 42,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _handle_notification_event(context: StepContext) -> tuple[WorkflowStepStatus, dict[str, Any]]:
        event_name = context.config.get("event_name", "workflow_progress")
        recipient = context.config.get("recipient", "operations_team")
        return WorkflowStepStatus.SUCCEEDED, {
            "event_name": event_name,
            "recipient": recipient,
            "dispatched": True,
            "dispatched_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _handle_manual_approval(context: StepContext) -> tuple[WorkflowStepStatus, dict[str, Any]]:
        # Manual approval halts execution and transitions step and run to WAITING
        return WorkflowStepStatus.WAITING, {
            "prompt": context.config.get("prompt", "Operator approval required to proceed."),
            "required_role": context.config.get("required_role", "operator"),
            "waiting_since": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _handle_delay(context: StepContext) -> tuple[WorkflowStepStatus, dict[str, Any]]:
        delay_seconds = int(context.config.get("delay_seconds", 0))
        return WorkflowStepStatus.SUCCEEDED, {
            "delay_seconds": delay_seconds,
            "elapsed": True,
            "resumed_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _handle_conditional(context: StepContext) -> tuple[WorkflowStepStatus, dict[str, Any]]:
        field_name = context.config.get("field")
        expected_value = context.config.get("value")
        op = context.config.get("operator", "==")

        actual_value = context.input_data.get(field_name) if field_name else None
        if actual_value is None and field_name:
            # Check previous step outputs
            for prev in context.previous_outputs.values():
                if field_name in prev:
                    actual_value = prev[field_name]
                    break

        condition_met = False
        if op == "==":
            condition_met = actual_value == expected_value
        elif op == "!=":
            condition_met = actual_value != expected_value
        elif op == "exists":
            condition_met = actual_value is not None
        elif op == "in" and isinstance(expected_value, list):
            condition_met = actual_value in expected_value

        return WorkflowStepStatus.SUCCEEDED, {
            "field": field_name,
            "operator": op,
            "condition_met": condition_met,
            "evaluated_at": datetime.now(UTC).isoformat(),
        }


class WorkflowEngine:
    """Service-layer engine orchestrating workflow step transitions, retries, and manual approvals."""

    def __init__(self, repo: WorkflowRepository) -> None:
        self.repo = repo

    def execute_run(self, run_id: UUID) -> WorkflowRun:
        """Advance a workflow run until completion, failure, or wait-for-approval."""
        run = self.repo.get_workflow_run(run_id)
        if run is None:
            raise ValueError(f"Workflow run {run_id} not found")

        # Validate workflow status
        workflow = run.workflow
        if workflow.status != WorkflowStatus.ACTIVE:
            raise ValueError(f"Cannot execute workflow in '{workflow.status.value}' state")

        if not workflow.is_enabled:
            raise ValueError("Workflow is disabled")

        if run.status in {WorkflowRunStatus.SUCCEEDED, WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED}:
            return run

        now = datetime.now(UTC)
        if run.status == WorkflowRunStatus.QUEUED:
            run.status = WorkflowRunStatus.RUNNING
            run.started_at = now
            self.repo.update_workflow_run(
                run,
                WorkflowAuditLog(
                    workflow_id=run.workflow_id,
                    run_id=run.id,
                    action=WorkflowAuditAction.RUN_STARTED,
                    actor_user_id=run.actor_user_id,
                    metadata_json={"started_at": now.isoformat()},
                ),
            )

        # Load ordered step executions
        steps = sorted(run.step_executions, key=lambda s: s.step_order)
        previous_outputs: dict[int, dict[str, Any]] = {}
        for s in steps:
            if s.output_json:
                previous_outputs[s.step_order] = s.output_json

        for step in steps:
            # Skip already completed steps
            if step.status == WorkflowStepStatus.SUCCEEDED or step.status == WorkflowStepStatus.SKIPPED:
                continue

            if step.status == WorkflowStepStatus.CANCELLED:
                run.status = WorkflowRunStatus.CANCELLED
                run.ended_at = datetime.now(UTC)
                self.repo.update_workflow_run(run)
                return run

            # If step is waiting for manual approval, halt
            if step.status == WorkflowStepStatus.WAITING:
                run.status = WorkflowRunStatus.WAITING
                self.repo.update_workflow_run(run)
                return run

            # Execute step
            run.current_step_order = step.step_order
            step.status = WorkflowStepStatus.RUNNING
            step.started_at = datetime.now(UTC)
            self.repo.update_step_execution(
                step,
                WorkflowAuditLog(
                    workflow_id=run.workflow_id,
                    run_id=run.id,
                    step_execution_id=step.id,
                    action=WorkflowAuditAction.STEP_STARTED,
                    actor_user_id=run.actor_user_id,
                    metadata_json={"step_order": step.step_order, "step_name": step.step_name},
                ),
            )

            context = StepContext(
                run_id=run.id,
                step_id=step.id,
                step_order=step.step_order,
                step_type=step.step_type,
                config=step.input_json or {},
                input_data=run.input_metadata_json or {},
                previous_outputs=previous_outputs,
            )

            try:
                status, output = StepHandler.execute(step.step_type, context)
                step.status = status
                step.output_json = sanitize_metadata(output)
                step.completed_at = datetime.now(UTC)
                previous_outputs[step.step_order] = step.output_json

                if status == WorkflowStepStatus.WAITING:
                    run.status = WorkflowRunStatus.WAITING
                    self.repo.update_step_execution(
                        step,
                        WorkflowAuditLog(
                            workflow_id=run.workflow_id,
                            run_id=run.id,
                            step_execution_id=step.id,
                            action=WorkflowAuditAction.APPROVAL_REQUESTED,
                            actor_user_id=run.actor_user_id,
                            metadata_json={"step_order": step.step_order, "step_name": step.step_name},
                        ),
                    )
                    self.repo.update_workflow_run(run)
                    return run

                self.repo.update_step_execution(
                    step,
                    WorkflowAuditLog(
                        workflow_id=run.workflow_id,
                        run_id=run.id,
                        step_execution_id=step.id,
                        action=WorkflowAuditAction.STEP_SUCCEEDED,
                        actor_user_id=run.actor_user_id,
                        metadata_json={"step_order": step.step_order, "step_name": step.step_name},
                    ),
                )

            except WorkflowExecutionError as err:
                is_retryable = err.retryable
                step.retry_count += 1
                run.retry_count += 1
                step.error_details_json = sanitize_metadata(
                    {"error": err.message, "retryable": is_retryable, "details": err.details}
                )
                step.retryable_failure = is_retryable

                if is_retryable and step.retry_count <= step.max_retries:
                    # Retry policy backoff
                    delay = step.retry_delay_seconds * (step.backoff_multiplier ** (step.retry_count - 1))
                    step.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay)
                    self.repo.update_step_execution(
                        step,
                        WorkflowAuditLog(
                            workflow_id=run.workflow_id,
                            run_id=run.id,
                            step_execution_id=step.id,
                            action=WorkflowAuditAction.STEP_FAILED,
                            actor_user_id=run.actor_user_id,
                            metadata_json={
                                "retry_count": step.retry_count,
                                "max_retries": step.max_retries,
                                "retry_scheduled": True,
                                "retry_delay_seconds": delay,
                                "next_retry_at": step.next_retry_at.isoformat(),
                                "error": err.message,
                            },
                        ),
                    )
                    # Re-attempt step up to max_retries
                    return self.execute_run(run_id)
                else:
                    # Permanent failure or max retries exceeded
                    step.status = WorkflowStepStatus.FAILED
                    step.completed_at = datetime.now(UTC)
                    run.error_summary = f"Step {step.step_order} ({step.step_name}) failed: {err.message}"

                    self.repo.update_step_execution(
                        step,
                        WorkflowAuditLog(
                            workflow_id=run.workflow_id,
                            run_id=run.id,
                            step_execution_id=step.id,
                            action=WorkflowAuditAction.STEP_FAILED,
                            actor_user_id=run.actor_user_id,
                            metadata_json={"error": err.message, "max_retries_exceeded": True},
                        ),
                    )
                    if step.is_required:
                        run.status = WorkflowRunStatus.FAILED
                        run.ended_at = datetime.now(UTC)
                        self.repo.update_workflow_run(
                            run,
                            WorkflowAuditLog(
                                workflow_id=run.workflow_id,
                                run_id=run.id,
                                action=WorkflowAuditAction.RUN_FAILED,
                                actor_user_id=run.actor_user_id,
                                metadata_json={"error": run.error_summary},
                            ),
                        )
                        return run
                    continue

            except Exception as exc:
                step.status = WorkflowStepStatus.FAILED
                step.completed_at = datetime.now(UTC)
                step.error_details_json = sanitize_metadata({"error": str(exc), "unexpected": True})
                run.status = WorkflowRunStatus.FAILED
                run.ended_at = datetime.now(UTC)
                run.error_summary = f"Unexpected failure at step {step.step_order}: {exc}"

                self.repo.update_step_execution(step)
                self.repo.update_workflow_run(
                    run,
                    WorkflowAuditLog(
                        workflow_id=run.workflow_id,
                        run_id=run.id,
                        action=WorkflowAuditAction.RUN_FAILED,
                        actor_user_id=run.actor_user_id,
                        metadata_json={"error": run.error_summary},
                    ),
                )
                return run

        # All steps succeeded
        has_optional_failures = any(
            step.status == WorkflowStepStatus.FAILED and not step.is_required for step in steps
        )
        run.status = (
            WorkflowRunStatus.PARTIALLY_SUCCEEDED if has_optional_failures else WorkflowRunStatus.SUCCEEDED
        )
        run.ended_at = datetime.now(UTC)
        run.output_metadata_json = sanitize_metadata(previous_outputs)
        self.repo.update_workflow_run(
            run,
            WorkflowAuditLog(
                workflow_id=run.workflow_id,
                run_id=run.id,
                action=WorkflowAuditAction.RUN_SUCCEEDED,
                actor_user_id=run.actor_user_id,
                metadata_json={"completed_steps": len(steps), "status": run.status.value},
            ),
        )
        return run

    def resume_run_after_approval(
        self,
        run_id: UUID,
        step_id: UUID,
        approved: bool,
        notes: str | None = None,
        actor_user_id: int | None = None,
    ) -> WorkflowRun:
        """Operator approval or rejection handler for a waiting manual approval step."""
        run = self.repo.get_workflow_run(run_id)
        if run is None:
            raise ValueError(f"Workflow run {run_id} not found")

        step = self.repo.get_step_execution(step_id)
        if step is None or step.run_id != run_id:
            raise ValueError(f"Step execution {step_id} not found for run {run_id}")

        if step.status != WorkflowStepStatus.WAITING:
            raise ValueError(f"Step is not waiting for approval (current status: {step.status.value})")

        now = datetime.now(UTC)
        if approved:
            step.status = WorkflowStepStatus.SUCCEEDED
            step.completed_at = now
            step.output_json = sanitize_metadata({
                "approved": True,
                "approved_by_user_id": actor_user_id,
                "notes": notes,
                "approved_at": now.isoformat(),
            })
            self.repo.update_step_execution(
                step,
                WorkflowAuditLog(
                    workflow_id=run.workflow_id,
                    run_id=run.id,
                    step_execution_id=step.id,
                    action=WorkflowAuditAction.STEP_APPROVED,
                    actor_user_id=actor_user_id,
                    metadata_json={"notes": notes},
                ),
            )
            # Resume run execution
            run.status = WorkflowRunStatus.RUNNING
            self.repo.update_workflow_run(run)
            return self.execute_run(run_id)
        else:
            step.status = WorkflowStepStatus.FAILED
            step.completed_at = now
            step.error_details_json = sanitize_metadata({
                "rejected": True,
                "rejected_by_user_id": actor_user_id,
                "notes": notes,
                "rejected_at": now.isoformat(),
            })
            run.status = WorkflowRunStatus.FAILED
            run.ended_at = now
            run.error_summary = f"Step {step.step_order} ({step.step_name}) rejected by operator: {notes or 'No notes provided'}"

            self.repo.update_step_execution(
                step,
                WorkflowAuditLog(
                    workflow_id=run.workflow_id,
                    run_id=run.id,
                    step_execution_id=step.id,
                    action=WorkflowAuditAction.STEP_REJECTED,
                    actor_user_id=actor_user_id,
                    metadata_json={"notes": notes},
                ),
            )
            self.repo.update_workflow_run(
                run,
                WorkflowAuditLog(
                    workflow_id=run.workflow_id,
                    run_id=run.id,
                    action=WorkflowAuditAction.RUN_FAILED,
                    actor_user_id=actor_user_id,
                    metadata_json={"rejection": True, "notes": notes},
                ),
            )
            return run

    def cancel_run(
        self,
        run_id: UUID,
        reason: str | None = None,
        actor_user_id: int | None = None,
    ) -> WorkflowRun:
        """Cancel an in-progress or waiting workflow run."""
        run = self.repo.get_workflow_run(run_id)
        if run is None:
            raise ValueError(f"Workflow run {run_id} not found")

        if run.status in {WorkflowRunStatus.SUCCEEDED, WorkflowRunStatus.FAILED, WorkflowRunStatus.CANCELLED}:
            return run

        now = datetime.now(UTC)
        run.status = WorkflowRunStatus.CANCELLED
        run.ended_at = now
        run.error_summary = f"Cancelled by operator: {reason or 'No reason provided'}"

        for step in run.step_executions:
            if step.status in {WorkflowStepStatus.PENDING, WorkflowStepStatus.RUNNING, WorkflowStepStatus.WAITING}:
                step.status = WorkflowStepStatus.CANCELLED
                step.completed_at = now
                self.repo.update_step_execution(step)

        self.repo.update_workflow_run(
            run,
            WorkflowAuditLog(
                workflow_id=run.workflow_id,
                run_id=run.id,
                action=WorkflowAuditAction.RUN_CANCELLED,
                actor_user_id=actor_user_id,
                metadata_json={"reason": reason},
            ),
        )
        return run
