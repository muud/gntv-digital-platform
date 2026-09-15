"""Application service for agent definitions, runs, approvals, policies and metrics."""

from __future__ import annotations

from datetime import UTC, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.modules.agents.models import (
    AgentDefinition as Agent,
    AgentApprovalRequest,
    AgentAuditAction,
    AgentAuditLog,
    AgentInstructionVersion,
    AgentRun,
    AgentRunStatus,
    AgentStatus,
    AgentToolCall,
    ToolCallStatus as AgentToolCallStatus,
    ApprovalMode,
    ApprovalPolicy,
    ApprovalStatus,
    ModelPolicy,
    ToolPolicy,
    utc_now,
)
from app.modules.agents.providers import provider_registry
from app.modules.agents.schemas import (
    AgentCreate,
    AgentRunCreate,
    AgentUpdate,
    ApprovalPolicyCreate,
    ModelPolicyCreate,
    ToolPolicyCreate,
)
from app.modules.agents.tools import tool_registry
from app.modules.events.schemas import EventPublishRequest
from app.modules.events.security import sanitize_payload
from app.modules.events.service import EventService
from app.modules.jobs.queue import DatabaseJobQueue


TERMINAL_RUN_STATES = {
    AgentRunStatus.SUCCEEDED,
    AgentRunStatus.FAILED,
    AgentRunStatus.CANCELLED,
    AgentRunStatus.BLOCKED,
    AgentRunStatus.PARTIALLY_SUCCEEDED,
}


def _safe_error(value: object) -> str:
    sanitized = sanitize_payload({"error": str(value)})["error"]
    return str(sanitized).replace("\n", " ")[:500]


class AgentControlService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.queue = DatabaseJobQueue()

    def _audit(
        self,
        action: str,
        *,
        agent: Agent | None = None,
        run: AgentRun | None = None,
        actor_user_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        emit: bool = True,
    ) -> AgentAuditLog:
        clean = sanitize_payload(metadata or {})
        log = AgentAuditLog(
            action=action,
            agent_id=agent.id if agent else (run.agent_id if run else None),
            agent_run_id=run.id if run else None,
            actor_user_id=actor_user_id,
            correlation_id=run.correlation_id if run else None,
            metadata_json=clean,
        )
        self.db.add(log)
        self.db.flush()
        if emit:
            event_type = {
                "agent_created": "agent.created",
                "agent_updated": "agent.updated",
                "agent_activated": "agent.activated",
                "agent_paused": "agent.paused",
                "agent_archived": "agent.archived",
                "agent_run_created": "agent.run.queued",
                "agent_run_started": "agent.run.started",
                "agent_run_completed": "agent.run.succeeded",
                "agent_run_failed": "agent.run.failed",
                "agent_run_cancelled": "agent.run.cancelled",
                "agent_run_blocked": "agent.run.blocked",
                "tool_requested": "agent.tool.requested",
                "tool_denied": "agent.tool.denied",
                "tool_approved": "agent.tool.approved",
                "tool_executed": "agent.tool.succeeded",
                "tool_failed": "agent.tool.failed",
                "approval_requested": "agent.approval.requested",
                "approval_approved": "agent.approval.approved",
                "approval_rejected": "agent.approval.rejected",
            }.get(action)
            if event_type:
                EventService().publish_event(
                    self.db,
                    EventPublishRequest(
                        event_type=event_type,
                        source="ai_agent_control_plane",
                        aggregate_type="agent_run" if run else "agent",
                        aggregate_id=str(run.id if run else agent.id if agent else ""),
                        correlation_id=run.correlation_id if run else uuid4().hex,
                        causation_id=run.causation_id if run else None,
                        idempotency_key=f"agent-audit:{log.id}",
                        payload=clean,
                    ),
                    actor_user_id=actor_user_id,
                )
        return log

    def create_model_policy(
        self, payload: ModelPolicyCreate, actor_user_id: int | None = None
    ) -> ModelPolicy:
        provider = provider_registry.resolve(payload.provider)
        if not provider.validate_model(payload.model_name):
            raise ValueError("Model is not approved for the selected provider")
        policy = ModelPolicy(**payload.model_dump())
        self.db.add(policy)
        self.db.flush()
        self._audit(
            "model_policy_changed",
            actor_user_id=actor_user_id,
            metadata={"policy_id": str(policy.id), "provider": policy.provider},
        )
        return policy

    def create_tool_policy(
        self, payload: ToolPolicyCreate, actor_user_id: int | None = None
    ) -> ToolPolicy:
        known = set(tool_registry.names())
        supplied = (
            set(payload.allowed_tools)
            | set(payload.denied_tools)
            | set(payload.requires_approval_for)
        )
        unknown = supplied - known
        if unknown:
            raise ValueError(f"Unknown tools: {', '.join(sorted(unknown))}")
        policy = ToolPolicy(**payload.model_dump())
        self.db.add(policy)
        self.db.flush()
        self._audit(
            "tool_policy_changed",
            actor_user_id=actor_user_id,
            metadata={"policy_id": str(policy.id)},
        )
        return policy

    def create_approval_policy(
        self, payload: ApprovalPolicyCreate, actor_user_id: int | None = None
    ) -> ApprovalPolicy:
        unknown = set(payload.tools_requiring_approval) - set(tool_registry.names())
        if unknown:
            raise ValueError(f"Unknown tools: {', '.join(sorted(unknown))}")
        policy = ApprovalPolicy(**payload.model_dump())
        self.db.add(policy)
        self.db.flush()
        self._audit(
            "approval_policy_changed",
            actor_user_id=actor_user_id,
            metadata={"policy_id": str(policy.id)},
        )
        return policy

    def list_policies(
        self, model: type[ModelPolicy] | type[ToolPolicy] | type[ApprovalPolicy]
    ) -> list[Any]:
        return list(self.db.scalars(select(model).order_by(model.created_at.desc())))

    def create_agent(
        self, payload: AgentCreate, actor_user_id: int | None = None
    ) -> Agent:
        model = self.db.get(ModelPolicy, payload.model_policy_id)
        tools = self.db.get(ToolPolicy, payload.tool_policy_id)
        approval = self.db.get(ApprovalPolicy, payload.approval_policy_id)
        if (
            not model
            or not model.enabled
            or not tools
            or not tools.enabled
            or not approval
            or not approval.enabled
        ):
            raise ValueError("Agent policies must exist and be enabled")
        provider_registry.resolve(model.provider)
        values = payload.model_dump()
        agent = Agent(
            **values,
            status=AgentStatus.DRAFT,
            instruction_version=1,
            created_by_user_id=actor_user_id,
        )
        self.db.add(agent)
        self.db.flush()
        self.db.add(
            AgentInstructionVersion(
                agent_id=agent.id,
                version=1,
                system_instructions=payload.system_instructions,
                change_summary="Initial instructions",
                created_by_user_id=actor_user_id,
                is_active=False,
            )
        )
        self.db.flush()
        self._audit(
            "agent_created",
            agent=agent,
            actor_user_id=actor_user_id,
            metadata={"slug": agent.slug, "type": agent.agent_type.value},
        )
        return agent

    def get_agent(self, agent_id: UUID) -> Agent:
        agent = self.db.scalar(
            select(Agent)
            .options(
                selectinload(Agent.model_policy),
                selectinload(Agent.tool_policy),
                selectinload(Agent.approval_policy),
                selectinload(Agent.instruction_versions),
            )
            .where(Agent.id == agent_id)
        )
        if not agent:
            raise ValueError("Agent not found")
        return agent

    def list_agents(
        self, status: AgentStatus | None = None, offset: int = 0, limit: int = 100
    ) -> list[Agent]:
        query = (
            select(Agent).order_by(Agent.created_at.desc()).offset(offset).limit(limit)
        )
        if status:
            query = query.where(Agent.status == status)
        return list(self.db.scalars(query))

    def update_agent(
        self, agent_id: UUID, payload: AgentUpdate, actor_user_id: int | None = None
    ) -> Agent:
        agent = self.get_agent(agent_id)
        values = payload.model_dump(exclude_unset=True)
        instructions = values.pop("system_instructions", None)
        summary = values.pop("instruction_change_summary", None)
        for policy_field, policy_type in (
            ("model_policy_id", ModelPolicy),
            ("tool_policy_id", ToolPolicy),
            ("approval_policy_id", ApprovalPolicy),
        ):
            if policy_field in values:
                policy = self.db.get(policy_type, values[policy_field])
                if not policy or not bool(getattr(policy, "enabled", False)):
                    raise ValueError(f"{policy_field} must reference an enabled policy")
        for key, value in values.items():
            setattr(
                agent, key, sanitize_payload(value) if key == "metadata_json" else value
            )
        if instructions is not None:
            next_version = (
                max([v.version for v in agent.instruction_versions] or [0]) + 1
            )
            self.db.add(
                AgentInstructionVersion(
                    agent_id=agent.id,
                    version=next_version,
                    system_instructions=instructions,
                    change_summary=summary or "Draft instruction update",
                    created_by_user_id=actor_user_id,
                )
            )
        agent.updated_at = utc_now()
        self.db.flush()
        self._audit(
            "agent_updated",
            agent=agent,
            actor_user_id=actor_user_id,
            metadata={
                "changed": sorted(values),
                "instruction_draft_created": instructions is not None,
            },
        )
        return agent

    def activate_instruction_version(
        self, agent_id: UUID, version: int, actor_user_id: int | None = None
    ) -> Agent:
        agent = self.get_agent(agent_id)
        candidate = self.db.scalar(
            select(AgentInstructionVersion).where(
                AgentInstructionVersion.agent_id == agent.id,
                AgentInstructionVersion.version == version,
            )
        )
        if not candidate:
            raise ValueError("Instruction version not found")
        for row in agent.instruction_versions:
            row.is_active = False
        candidate.is_active = True
        candidate.activated_at = utc_now()
        agent.instruction_version = version
        agent.system_instructions = candidate.system_instructions
        agent.updated_at = utc_now()
        self.db.flush()
        self._audit(
            "agent_updated",
            agent=agent,
            actor_user_id=actor_user_id,
            metadata={"instruction_version": version},
        )
        return agent

    def set_status(
        self, agent_id: UUID, target: AgentStatus, actor_user_id: int | None = None
    ) -> Agent:
        agent = self.get_agent(agent_id)
        now = utc_now()
        transitions = {
            AgentStatus.DRAFT: {AgentStatus.ACTIVE, AgentStatus.ARCHIVED},
            AgentStatus.ACTIVE: {AgentStatus.PAUSED, AgentStatus.ARCHIVED},
            AgentStatus.PAUSED: {AgentStatus.ACTIVE, AgentStatus.ARCHIVED},
            AgentStatus.ARCHIVED: set(),
        }
        if target not in transitions[agent.status]:
            raise ValueError(
                f"Cannot transition agent from {agent.status.value} to {target.value}"
            )
        if target == AgentStatus.ACTIVE:
            version = self.db.scalar(
                select(AgentInstructionVersion).where(
                    AgentInstructionVersion.agent_id == agent.id,
                    AgentInstructionVersion.version == agent.instruction_version,
                )
            )
            if not version:
                raise ValueError("Active instruction version is missing")
            version.is_active = True
            version.activated_at = version.activated_at or now
            agent.activated_at = now
        elif target == AgentStatus.PAUSED:
            agent.paused_at = now
        elif target == AgentStatus.ARCHIVED:
            agent.archived_at = now
        agent.status = target
        agent.updated_at = now
        self.db.flush()
        action = {
            AgentStatus.ACTIVE: "agent_activated",
            AgentStatus.PAUSED: "agent_paused",
            AgentStatus.ARCHIVED: "agent_archived",
        }[target]
        self._audit(
            action,
            agent=agent,
            actor_user_id=actor_user_id,
            metadata={"status": target.value},
        )
        return agent

    def _requires_run_approval(self, agent: Agent) -> bool:
        return (
            agent.approval_policy.enabled
            and agent.approval_policy.approval_mode == ApprovalMode.BEFORE_RUN
        )

    def create_run(
        self, agent_id: UUID, payload: AgentRunCreate, actor_user_id: int | None = None
    ) -> AgentRun:
        agent = self.get_agent(agent_id)
        if agent.status != AgentStatus.ACTIVE:
            raise ValueError("Only active agents may start runs")
        key = payload.idempotency_key or f"agent-run-{uuid4().hex}"
        existing = self.db.scalar(
            select(AgentRun).where(
                AgentRun.agent_id == agent.id, AgentRun.idempotency_key == key
            )
        )
        if existing:
            return existing
        correlation = payload.correlation_id or uuid4().hex
        status = (
            AgentRunStatus.AWAITING_APPROVAL
            if self._requires_run_approval(agent)
            else AgentRunStatus.QUEUED
        )
        run = AgentRun(
            agent_id=agent.id,
            instruction_version=agent.instruction_version,
            status=status,
            trigger_type=payload.trigger_type,
            trigger_source=payload.trigger_source,
            input_json=sanitize_payload(payload.input_json),
            sanitized_context_json=sanitize_payload(payload.context_json),
            correlation_id=correlation,
            causation_id=payload.causation_id,
            idempotency_key=key,
            requested_by_user_id=actor_user_id,
        )
        self.db.add(run)
        self.db.flush()
        self._audit(
            "agent_run_created",
            run=run,
            actor_user_id=actor_user_id,
            metadata={"status": status.value},
        )
        if status == AgentRunStatus.AWAITING_APPROVAL:
            approval = AgentApprovalRequest(
                agent_run_id=run.id,
                approval_type="run",
                requested_by="agent_control_plane",
                expires_at=utc_now() + timedelta(hours=24),
            )
            self.db.add(approval)
            self.db.flush()
            self._audit(
                "approval_requested",
                run=run,
                actor_user_id=actor_user_id,
                metadata={"approval_id": str(approval.id)},
            )
        else:
            self.enqueue_run(run, actor_user_id=actor_user_id)
        return run

    def enqueue_run(
        self, run: AgentRun, actor_user_id: int | None = None, suffix: str = "initial"
    ) -> AgentRun:
        job = self.queue.enqueue(
            self.db,
            job_type="AI_AGENT_RUN",
            payload={"agent_run_id": str(run.id)},
            queue_name="agents",
            idempotency_key=f"agent-run:{run.id}:{suffix}",
            correlation_id=run.correlation_id,
            causation_id=run.causation_id,
            timeout_seconds=run.agent.default_timeout_seconds,
            actor_user_id=actor_user_id,
        )
        run.job_id = job.id
        run.status = AgentRunStatus.QUEUED
        self.db.flush()
        return run

    def get_run(self, run_id: UUID) -> AgentRun:
        run = self.db.scalar(
            select(AgentRun)
            .options(
                selectinload(AgentRun.agent).selectinload(Agent.model_policy),
                selectinload(AgentRun.agent).selectinload(Agent.tool_policy),
                selectinload(AgentRun.agent).selectinload(Agent.approval_policy),
                selectinload(AgentRun.tool_calls),
                selectinload(AgentRun.approvals),
            )
            .where(AgentRun.id == run_id)
        )
        if not run:
            raise ValueError("Agent run not found")
        return run

    def list_runs(
        self,
        status: AgentRunStatus | None = None,
        agent_id: UUID | None = None,
        requested_by_user_id: int | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[AgentRun]:
        query = (
            select(AgentRun)
            .order_by(AgentRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if status:
            query = query.where(AgentRun.status == status)
        if agent_id:
            query = query.where(AgentRun.agent_id == agent_id)
        if requested_by_user_id is not None:
            query = query.where(AgentRun.requested_by_user_id == requested_by_user_id)
        return list(self.db.scalars(query))

    def cancel_run(self, run_id: UUID, actor_user_id: int | None = None) -> AgentRun:
        run = self.get_run(run_id)
        if run.status in TERMINAL_RUN_STATES:
            return run
        run.cancellation_requested = True
        if run.status != AgentRunStatus.RUNNING:
            run.status = AgentRunStatus.CANCELLED
            run.cancelled_at = utc_now()
            run.completed_at = utc_now()
        if run.job_id:
            try:
                self.queue.cancel(
                    self.db,
                    job_id=run.job_id,
                    reason="agent run cancellation",
                    actor_user_id=actor_user_id,
                )
            except ValueError:
                pass
        for approval in run.approvals:
            if approval.status == ApprovalStatus.PENDING:
                approval.status = ApprovalStatus.CANCELLED
                approval.decided_at = utc_now()
        self.db.flush()
        self._audit("agent_run_cancelled", run=run, actor_user_id=actor_user_id)
        return run

    def retry_run(self, run_id: UUID, actor_user_id: int | None = None) -> AgentRun:
        old = self.get_run(run_id)
        if old.status not in {
            AgentRunStatus.FAILED,
            AgentRunStatus.BLOCKED,
            AgentRunStatus.PARTIALLY_SUCCEEDED,
        }:
            raise ValueError("Only failed or blocked runs may be retried")
        return self.create_run(
            old.agent_id,
            AgentRunCreate(
                input_json=old.input_json or {},
                context_json=old.sanitized_context_json or {},
                trigger_type="retry",
                trigger_source="operator_api",
                idempotency_key=f"retry:{old.id}:{uuid4().hex}",
                correlation_id=old.correlation_id,
                causation_id=str(old.id),
            ),
            actor_user_id,
        )

    def list_approvals(
        self, status: ApprovalStatus | None = None
    ) -> list[AgentApprovalRequest]:
        now = utc_now()
        pending = list(
            self.db.scalars(
                select(AgentApprovalRequest).where(
                    AgentApprovalRequest.status == ApprovalStatus.PENDING
                )
            )
        )
        for item in pending:
            expiry = (
                item.expires_at.replace(tzinfo=UTC)
                if item.expires_at and item.expires_at.tzinfo is None
                else item.expires_at
            )
            if expiry and expiry <= now:
                item.status = ApprovalStatus.EXPIRED
                item.decided_at = now
        self.db.flush()
        query = select(AgentApprovalRequest).order_by(
            AgentApprovalRequest.requested_at.desc()
        )
        if status:
            query = query.where(AgentApprovalRequest.status == status)
        return list(self.db.scalars(query))

    def decide_approval(
        self,
        approval_id: UUID,
        approve: bool,
        actor_user_id: int,
        reason: str | None = None,
    ) -> AgentRun:
        approval = self.db.get(AgentApprovalRequest, approval_id)
        if not approval:
            raise ValueError("Approval request not found")
        now = utc_now()
        expiry = (
            approval.expires_at.replace(tzinfo=UTC)
            if approval.expires_at and approval.expires_at.tzinfo is None
            else approval.expires_at
        )
        if expiry and expiry <= now:
            approval.status = ApprovalStatus.EXPIRED
            approval.decided_at = now
            self.db.flush()
            raise ValueError("Approval request has expired")
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError("Approval request is no longer pending")
        run = self.get_run(approval.agent_run_id)
        approval.status = (
            ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
        )
        approval.decided_by_user_id = actor_user_id
        approval.decided_at = now
        approval.decision_reason = _safe_error(reason or "") or None
        if approval.tool_call:
            approval.tool_call.status = (
                AgentToolCallStatus.APPROVED if approve else AgentToolCallStatus.DENIED
            )
            approval.tool_call.approved_by_user_id = actor_user_id if approve else None
        if approve:
            run.approved_by_user_id = actor_user_id
            self._audit(
                "approval_approved",
                run=run,
                actor_user_id=actor_user_id,
                metadata={"approval_id": str(approval.id)},
            )
            if approval.tool_call:
                # Resume the exact approved call. Re-enqueueing the full run would
                # evaluate the tool request again and create an approval loop.
                self.db.flush()
                from app.modules.agents.engine import AgentExecutionEngine

                return AgentExecutionEngine(self.db).resume_approved_tool(
                    run.id, approval.tool_call.id
                )
            self.enqueue_run(run, actor_user_id, suffix=f"approval:{approval.id}")
        else:
            run.status = AgentRunStatus.BLOCKED
            run.safe_error_summary = "Human approval rejected"
            run.completed_at = now
            self._audit(
                "approval_rejected",
                run=run,
                actor_user_id=actor_user_id,
                metadata={"approval_id": str(approval.id)},
            )
            self._audit(
                "agent_run_blocked",
                run=run,
                actor_user_id=actor_user_id,
                metadata={"reason": "approval_rejected"},
            )
        self.db.flush()
        return run

    def metrics(self) -> dict[str, Any]:
        statuses: dict[AgentRunStatus, int] = {
            key: count
            for key, count in self.db.execute(
                select(AgentRun.status, func.count()).group_by(AgentRun.status)
            ).tuples()
        }
        agents: dict[AgentStatus, int] = {
            key: count
            for key, count in self.db.execute(
                select(Agent.status, func.count()).group_by(Agent.status)
            ).tuples()
        }
        tool_types: dict[str, int] = {
            key: count
            for key, count in self.db.execute(
                select(AgentToolCall.tool_name, func.count()).group_by(
                    AgentToolCall.tool_name
                )
            ).tuples()
        }
        avg_runtime = self.db.scalar(select(func.avg(AgentRun.runtime_seconds))) or 0
        totals = self.db.execute(
            select(
                func.coalesce(func.sum(AgentRun.total_tokens), 0),
                func.coalesce(func.sum(AgentRun.cost_units), 0),
            )
        ).one()
        oldest = self.db.scalar(
            select(func.min(AgentRun.created_at)).where(
                AgentRun.status == AgentRunStatus.QUEUED
            )
        )
        denied = (
            self.db.scalar(
                select(func.count())
                .select_from(AgentToolCall)
                .where(AgentToolCall.status == AgentToolCallStatus.DENIED)
            )
            or 0
        )
        return {
            "active_agents": agents.get(AgentStatus.ACTIVE, 0),
            "paused_agents": agents.get(AgentStatus.PAUSED, 0),
            "queued_runs": statuses.get(AgentRunStatus.QUEUED, 0),
            "running_runs": statuses.get(AgentRunStatus.RUNNING, 0),
            "awaiting_approval_runs": statuses.get(AgentRunStatus.AWAITING_APPROVAL, 0)
            + statuses.get(AgentRunStatus.WAITING_FOR_HUMAN, 0),
            "failed_runs": statuses.get(AgentRunStatus.FAILED, 0),
            "blocked_runs": statuses.get(AgentRunStatus.BLOCKED, 0),
            "succeeded_runs": statuses.get(AgentRunStatus.SUCCEEDED, 0),
            "average_runtime_seconds": float(avg_runtime),
            "tool_calls_by_type": tool_types,
            "denied_tool_calls": denied,
            "total_tokens": int(totals[0]),
            "cost_units": float(totals[1]),
            "oldest_queued_at": oldest,
        }

    # Stable names used by the API and execution engine.
    def audit(
        self,
        action: AgentAuditAction,
        *,
        agent: Agent | None = None,
        run: AgentRun | None = None,
        actor_user_id: int | None = None,
        tool_call_id: UUID | None = None,
        approval_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentAuditLog:
        row = self._audit(
            action.value,
            agent=agent,
            run=run,
            actor_user_id=actor_user_id,
            metadata=metadata,
        )
        row.tool_call_id = tool_call_id
        row.approval_request_id = approval_id
        self.db.flush()
        return row

    def agents(self) -> list[Agent]:
        return self.list_agents()

    def agent(self, agent_id: UUID) -> Agent:
        return self.get_agent(agent_id)

    def transition(
        self, agent_id: UUID, target: AgentStatus, actor_user_id: int | None = None
    ) -> Agent:
        return self.set_status(agent_id, target, actor_user_id)

    def create_instruction(
        self, agent_id: UUID, payload: Any, actor_user_id: int | None = None
    ) -> AgentInstructionVersion:
        agent = self.get_agent(agent_id)
        next_version = (
            max((row.version for row in agent.instruction_versions), default=0) + 1
        )
        row = AgentInstructionVersion(
            agent_id=agent.id,
            version=next_version,
            system_instructions=payload.system_instructions,
            change_summary=payload.change_summary,
            created_by_user_id=actor_user_id,
            is_active=False,
        )
        self.db.add(row)
        self.db.flush()
        self._audit(
            "agent_updated",
            agent=agent,
            actor_user_id=actor_user_id,
            metadata={"draft_instruction_version": next_version},
        )
        return row

    def activate_instruction(
        self, agent_id: UUID, version: int, actor_user_id: int | None = None
    ) -> Agent:
        return self.activate_instruction_version(agent_id, version, actor_user_id)

    def run(self, run_id: UUID) -> AgentRun:
        return self.get_run(run_id)

    def runs(self) -> list[AgentRun]:
        return self.list_runs()

    def cancel(self, run_id: UUID, actor_user_id: int | None = None) -> AgentRun:
        return self.cancel_run(run_id, actor_user_id)

    def retry(self, run_id: UUID, actor_user_id: int | None = None) -> AgentRun:
        return self.retry_run(run_id, actor_user_id)

    def approvals(self) -> list[AgentApprovalRequest]:
        return self.list_approvals()
