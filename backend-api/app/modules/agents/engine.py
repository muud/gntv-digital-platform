"""Bounded deterministic execution engine for approved AI agents."""

from __future__ import annotations

from datetime import timedelta
from time import monotonic
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.agents.models import (
    AgentApprovalRequest,
    AgentAuditAction,
    AgentRun,
    AgentRunStatus,
    AgentStatus,
    AgentToolCall,
    ApprovalMode,
    ToolCallStatus,
    utc_now,
)
from app.modules.agents.providers import StructuredModelResponse, provider_registry
from app.modules.agents.service import AgentControlService, TERMINAL_RUN_STATES
from app.modules.agents.tools import tool_registry
from app.modules.events.security import sanitize_payload


GLOBAL_AGENT_EXECUTION_LIMIT = 10


class AgentExecutionEngine:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.service = AgentControlService(db)

    def execute(self, run_id: UUID) -> AgentRun:
        run = self.service.run(run_id)
        agent = run.agent
        if run.status in TERMINAL_RUN_STATES:
            return run
        if agent.status != AgentStatus.ACTIVE:
            return self._block(run, "Agent is not active")
        if run.status in {
            AgentRunStatus.AWAITING_APPROVAL,
            AgentRunStatus.WAITING_FOR_HUMAN,
        }:
            return run

        globally_running = (
            self.db.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(
                    AgentRun.status == AgentRunStatus.RUNNING,
                    AgentRun.id != run.id,
                )
            )
            or 0
        )
        agent_running = (
            self.db.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(
                    AgentRun.status == AgentRunStatus.RUNNING,
                    AgentRun.agent_id == agent.id,
                    AgentRun.id != run.id,
                )
            )
            or 0
        )
        if globally_running >= GLOBAL_AGENT_EXECUTION_LIMIT:
            return self._block(run, "Global agent execution limit reached")
        if agent_running >= agent.concurrency_limit:
            return self._block(run, "Per-agent concurrency limit reached")

        instruction = next(
            (
                row
                for row in agent.instruction_versions
                if row.version == run.instruction_version
            ),
            None,
        )
        if instruction is None:
            return self._fail(run, "Recorded instruction version is unavailable")
        if (
            not agent.model_policy.enabled
            or not agent.tool_policy.enabled
            or not agent.approval_policy.enabled
        ):
            return self._block(run, "Agent policy is disabled")

        try:
            provider = provider_registry.resolve(agent.model_policy.provider)
        except ValueError as exc:
            return self._fail(run, str(exc))
        if not provider.validate_model(agent.model_policy.model_name):
            return self._fail(run, "Model policy is invalid")

        run.status = AgentRunStatus.RUNNING
        run.started_at = run.started_at or utc_now()
        self.service.audit(AgentAuditAction.AGENT_RUN_STARTED, run=run)
        start = monotonic()

        while run.current_iteration < agent.max_iterations:
            if run.cancellation_requested:
                return self._cancel(run)
            elapsed = monotonic() - start
            if elapsed >= agent.max_runtime_seconds:
                return self._fail(run, "Maximum runtime exceeded")

            run.current_iteration += 1
            trusted_context = {
                "agent_id": str(agent.id),
                "run_id": str(run.id),
                "instruction_version": run.instruction_version,
                "allowed_tools": agent.tool_policy.allowed_tools,
                "last_tool_result": (run.output_json or {}).get("last_tool_result"),
            }
            untrusted_content = (run.sanitized_context_json or {}).get(
                "untrusted_content"
            )
            user_request = run.input_json or {}
            try:
                response = provider.generate_structured(
                    system=instruction.system_instructions,
                    trusted_context=trusted_context,
                    untrusted_content=untrusted_content,
                    user_request=user_request,
                )
            except Exception as exc:
                return self._fail(run, f"Invalid structured model response: {exc}")
            if not isinstance(response, StructuredModelResponse):
                return self._fail(run, "Provider returned an invalid response contract")

            usage = provider.estimate_usage(user_request, response.model_dump())
            run.input_tokens += usage.input_tokens
            run.output_tokens += usage.output_tokens
            run.total_tokens += usage.total_tokens
            run.cost_units += usage.cost_units
            if (
                run.input_tokens > agent.max_input_tokens
                or run.output_tokens
                > min(agent.max_output_tokens, agent.model_policy.max_output_tokens)
                or run.total_tokens > agent.max_total_tokens
                or run.cost_units > agent.max_cost_units
            ):
                return self._block(run, "Agent execution budget exceeded")

            if response.type == "final":
                run.output_json = sanitize_payload({"message": response.message})
                run.status = AgentRunStatus.SUCCEEDED
                run.completed_at = utc_now()
                run.runtime_seconds = monotonic() - start
                self.service.audit(AgentAuditAction.AGENT_RUN_COMPLETED, run=run)
                self.db.flush()
                return run
            if response.type == "approval_request":
                approval = AgentApprovalRequest(
                    agent_run_id=run.id,
                    approval_type="model_requested",
                    requested_by="agent",
                    expires_at=utc_now() + timedelta(hours=24),
                )
                self.db.add(approval)
                run.status = AgentRunStatus.WAITING_FOR_HUMAN
                self.db.flush()
                self.service.audit(
                    AgentAuditAction.APPROVAL_REQUESTED,
                    run=run,
                    approval_id=approval.id,
                )
                return run
            if not response.tool_name:
                return self._fail(run, "Tool request omitted tool_name")
            outcome = self._request_tool(
                run, response.tool_name, response.tool_arguments
            )
            if outcome.status == AgentRunStatus.WAITING_FOR_HUMAN:
                return outcome
            if outcome.status in TERMINAL_RUN_STATES:
                return outcome

        return self._block(run, "Maximum iterations exceeded")

    def _request_tool(
        self, run: AgentRun, tool_name: str, arguments: dict[str, object]
    ) -> AgentRun:
        agent = run.agent
        call = AgentToolCall(
            agent_run_id=run.id,
            tool_name=tool_name,
            sanitized_arguments_json=sanitize_payload(arguments),
        )
        self.db.add(call)
        self.db.flush()
        run.tool_call_count += 1
        self.service.audit(
            AgentAuditAction.TOOL_REQUESTED, run=run, tool_call_id=call.id
        )

        allowed = set(agent.tool_policy.allowed_tools)
        denied = set(agent.tool_policy.denied_tools)
        if (
            tool_name not in tool_registry.names()
            or tool_name not in allowed
            or tool_name in denied
            or not agent.tool_policy.enabled
        ):
            call.status = ToolCallStatus.DENIED
            call.safe_error_summary = "Tool denied by policy"
            call.completed_at = utc_now()
            self.service.audit(
                AgentAuditAction.TOOL_DENIED, run=run, tool_call_id=call.id
            )
            return self._block(run, "Tool denied by policy")
        limit = min(agent.max_tool_calls, agent.tool_policy.max_tool_calls)
        if run.tool_call_count > limit:
            call.status = ToolCallStatus.DENIED
            call.safe_error_summary = "Maximum tool calls exceeded"
            call.completed_at = utc_now()
            self.service.audit(
                AgentAuditAction.TOOL_DENIED, run=run, tool_call_id=call.id
            )
            return self._block(run, "Maximum tool calls exceeded")

        approval = agent.approval_policy
        requires_approval = (
            tool_name in agent.tool_policy.requires_approval_for
            or tool_name in approval.tools_requiring_approval
            or (
                approval.workflow_execution_requires_approval
                and tool_name == "REQUEST_WORKFLOW_RUN"
            )
            or (
                approval.side_effects_require_approval
                and tool_name
                in {
                    "REQUEST_WORKFLOW_RUN",
                    "ENQUEUE_APPROVED_JOB",
                    "EMIT_INTERNAL_EVENT",
                }
            )
            or approval.approval_mode == ApprovalMode.SELECTED_TOOLS
            and tool_name in approval.tools_requiring_approval
        )
        if requires_approval:
            call.status = ToolCallStatus.AWAITING_APPROVAL
            call.requires_approval = True
            request = AgentApprovalRequest(
                agent_run_id=run.id,
                tool_call_id=call.id,
                approval_type="tool",
                requested_by="agent",
                expires_at=utc_now() + timedelta(hours=24),
            )
            self.db.add(request)
            run.status = AgentRunStatus.WAITING_FOR_HUMAN
            self.db.flush()
            self.service.audit(
                AgentAuditAction.APPROVAL_REQUESTED,
                run=run,
                tool_call_id=call.id,
                approval_id=request.id,
            )
            return run
        return self._execute_tool(run, call)

    def _execute_tool(self, run: AgentRun, call: AgentToolCall) -> AgentRun:
        call.status = ToolCallStatus.RUNNING
        call.started_at = utc_now()
        run.status = AgentRunStatus.WAITING_FOR_TOOL
        policy = run.agent.tool_policy
        control = {
            "run_id": str(run.id),
            "idempotency_key": run.idempotency_key,
            "correlation_id": run.correlation_id,
            "causation_id": run.causation_id or str(run.id),
            "actor_user_id": run.requested_by_user_id,
            "allowed_workflow_ids": policy.allowed_workflow_ids,
            "allowed_job_types": policy.allowed_job_types,
            "allowed_event_namespaces": policy.allowed_event_namespaces,
        }
        try:
            result = tool_registry.execute(
                self.db, call.tool_name, call.sanitized_arguments_json or {}, control
            )
        except (ValueError, PermissionError) as exc:
            call.status = ToolCallStatus.DENIED
            call.safe_error_summary = str(exc)[:1000]
            call.completed_at = utc_now()
            self.service.audit(
                AgentAuditAction.TOOL_DENIED, run=run, tool_call_id=call.id
            )
            return self._block(run, str(exc))
        except Exception as exc:
            call.status = ToolCallStatus.FAILED
            call.safe_error_summary = str(exc)[:1000]
            call.completed_at = utc_now()
            self.service.audit(
                AgentAuditAction.AGENT_RUN_FAILED, run=run, tool_call_id=call.id
            )
            return self._fail(run, f"Tool failed: {exc}")
        call.status = ToolCallStatus.SUCCEEDED
        call.sanitized_result_json = sanitize_payload(result)
        call.completed_at = utc_now()
        run.output_json = {"last_tool_result": call.sanitized_result_json}
        run.status = AgentRunStatus.RUNNING
        self.service.audit(
            AgentAuditAction.TOOL_EXECUTED, run=run, tool_call_id=call.id
        )
        self.db.flush()
        return run

    def resume_approved_tool(self, run_id: UUID, tool_call_id: UUID) -> AgentRun:
        run = self.service.run(run_id)
        call = self.db.get(AgentToolCall, tool_call_id)
        if (
            call is None
            or call.agent_run_id != run.id
            or call.status != ToolCallStatus.APPROVED
        ):
            raise ValueError("Approved tool call not found")
        result = self._execute_tool(run, call)
        if result.status == AgentRunStatus.RUNNING:
            return self.execute(run.id)
        return result

    def _block(self, run: AgentRun, message: str) -> AgentRun:
        run.status = AgentRunStatus.BLOCKED
        run.safe_error_summary = str(message)[:1000]
        run.completed_at = utc_now()
        self.service.audit(
            AgentAuditAction.AGENT_RUN_BLOCKED,
            run=run,
            metadata={"reason": run.safe_error_summary},
        )
        self.db.flush()
        return run

    def _fail(self, run: AgentRun, message: str) -> AgentRun:
        run.status = AgentRunStatus.FAILED
        run.safe_error_summary = str(message)[:1000]
        run.failed_at = utc_now()
        run.completed_at = run.failed_at
        self.service.audit(
            AgentAuditAction.AGENT_RUN_FAILED,
            run=run,
            metadata={"reason": run.safe_error_summary},
        )
        self.db.flush()
        return run

    def _cancel(self, run: AgentRun) -> AgentRun:
        run.status = AgentRunStatus.CANCELLED
        run.cancelled_at = utc_now()
        run.completed_at = run.cancelled_at
        self.service.audit(AgentAuditAction.AGENT_RUN_CANCELLED, run=run)
        self.db.flush()
        return run
