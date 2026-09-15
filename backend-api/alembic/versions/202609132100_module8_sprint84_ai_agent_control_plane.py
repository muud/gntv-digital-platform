"""Module 8 Sprint 8.4 secure AI agent control plane.

Revision ID: 202609132100
Revises: 202609131200
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202609132100"
down_revision: str | None = "202609131200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

agent_status = sa.Enum(
    "draft", "active", "paused", "archived", name="agent_status_enum"
)
agent_type = sa.Enum(
    "RESEARCH_AGENT",
    "SCRIPT_WRITER_AGENT",
    "CONTENT_SUMMARIZER_AGENT",
    "CONTENT_CLASSIFIER_AGENT",
    "EDITORIAL_ASSISTANT_AGENT",
    "PRODUCTION_PLANNER_AGENT",
    "DISTRIBUTION_PLANNER_AGENT",
    "MONITORING_AGENT",
    name="agent_type_enum",
)
run_status = sa.Enum(
    "queued",
    "awaiting_approval",
    "running",
    "waiting_for_tool",
    "waiting_for_human",
    "succeeded",
    "failed",
    "cancelled",
    "blocked",
    "partially_succeeded",
    name="agent_run_status_enum",
)
tool_status = sa.Enum(
    "requested",
    "awaiting_approval",
    "approved",
    "running",
    "succeeded",
    "failed",
    "denied",
    "cancelled",
    name="agent_tool_call_status_enum",
)
approval_status = sa.Enum(
    "pending",
    "approved",
    "rejected",
    "expired",
    "cancelled",
    name="agent_approval_status_enum",
)
approval_mode = sa.Enum(
    "none",
    "before_run",
    "selected_tools",
    "external_side_effects",
    "before_publishing",
    "before_workflow",
    name="agent_approval_mode_enum",
)
audit_action = sa.Enum(
    "agent_created",
    "agent_updated",
    "agent_activated",
    "agent_paused",
    "agent_archived",
    "agent_run_created",
    "agent_run_queued",
    "agent_run_started",
    "agent_run_completed",
    "agent_run_failed",
    "agent_run_cancelled",
    "agent_run_blocked",
    "tool_requested",
    "tool_denied",
    "tool_approved",
    "tool_executed",
    "approval_requested",
    "approval_approved",
    "approval_rejected",
    "model_policy_changed",
    "tool_policy_changed",
    "approval_policy_changed",
    name="agent_audit_action_enum",
)


def upgrade() -> None:
    op.create_table(
        "agent_model_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False, server_default="mock"),
        sa.Column(
            "model_name",
            sa.String(120),
            nullable=False,
            server_default="deterministic-v1",
        ),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "max_output_tokens", sa.Integer(), nullable=False, server_default="1024"
        ),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("fallback_policy", sa.JSON()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("name", name="uq_agent_model_policy_name"),
    )
    op.create_table(
        "agent_tool_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("allowed_tools", sa.JSON(), nullable=False),
        sa.Column("denied_tools", sa.JSON(), nullable=False),
        sa.Column("max_tool_calls", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("requires_approval_for", sa.JSON(), nullable=False),
        sa.Column("allowed_workflow_ids", sa.JSON(), nullable=False),
        sa.Column("allowed_job_types", sa.JSON(), nullable=False),
        sa.Column("allowed_event_namespaces", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("name", name="uq_agent_tool_policy_name"),
    )
    op.create_table(
        "agent_approval_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "approval_mode", approval_mode, nullable=False, server_default="none"
        ),
        sa.Column("tools_requiring_approval", sa.JSON(), nullable=False),
        sa.Column(
            "side_effects_require_approval",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "workflow_execution_requires_approval",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "publishing_requires_approval",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("name", name="uq_agent_approval_policy_name"),
    )
    op.create_table(
        "agent_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("status", agent_status, nullable=False, server_default="draft"),
        sa.Column("agent_type", agent_type, nullable=False),
        sa.Column("system_instructions", sa.Text(), nullable=False),
        sa.Column(
            "instruction_version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "model_policy_id",
            sa.Uuid(),
            sa.ForeignKey("agent_model_policies.id"),
            nullable=False,
        ),
        sa.Column(
            "tool_policy_id",
            sa.Uuid(),
            sa.ForeignKey("agent_tool_policies.id"),
            nullable=False,
        ),
        sa.Column(
            "approval_policy_id",
            sa.Uuid(),
            sa.ForeignKey("agent_approval_policies.id"),
            nullable=False,
        ),
        sa.Column(
            "default_queue_name", sa.String(80), nullable=False, server_default="agents"
        ),
        sa.Column(
            "default_timeout_seconds", sa.Integer(), nullable=False, server_default="60"
        ),
        sa.Column(
            "max_runtime_seconds", sa.Integer(), nullable=False, server_default="300"
        ),
        sa.Column("max_tool_calls", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("max_iterations", sa.Integer(), nullable=False, server_default="10"),
        sa.Column(
            "max_input_tokens", sa.Integer(), nullable=False, server_default="4096"
        ),
        sa.Column(
            "max_output_tokens", sa.Integer(), nullable=False, server_default="2048"
        ),
        sa.Column(
            "max_total_tokens", sa.Integer(), nullable=False, server_default="6144"
        ),
        sa.Column("max_cost_units", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "concurrency_limit", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("paused_at", sa.DateTime(timezone=True)),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("slug", name="uq_agent_definition_slug"),
    )
    op.create_index("ix_agent_definitions_status", "agent_definitions", ["status"])
    op.create_table(
        "agent_instruction_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey("agent_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("system_instructions", sa.Text(), nullable=False),
        sa.Column("change_summary", sa.String(500)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("agent_id", "version", name="uq_agent_instruction_version"),
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "agent_id", sa.Uuid(), sa.ForeignKey("agent_definitions.id"), nullable=False
        ),
        sa.Column("instruction_version", sa.Integer(), nullable=False),
        sa.Column("status", run_status, nullable=False, server_default="queued"),
        sa.Column(
            "trigger_type", sa.String(60), nullable=False, server_default="manual"
        ),
        sa.Column("trigger_source", sa.String(120)),
        sa.Column("input_json", sa.JSON()),
        sa.Column("sanitized_context_json", sa.JSON()),
        sa.Column("output_json", sa.JSON()),
        sa.Column("safe_error_summary", sa.String(1000)),
        sa.Column("correlation_id", sa.String(160), nullable=False),
        sa.Column("causation_id", sa.String(160)),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column(
            "requested_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "approved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column(
            "workflow_run_id",
            sa.Uuid(),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "current_iteration", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("runtime_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "cancellation_requested",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "agent_id", "idempotency_key", name="uq_agent_run_idempotency"
        ),
    )
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_correlation", "agent_runs", ["correlation_id"])
    op.create_table(
        "agent_tool_calls",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "agent_run_id",
            sa.Uuid(),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("status", tool_status, nullable=False, server_default="requested"),
        sa.Column("sanitized_arguments_json", sa.JSON()),
        sa.Column("sanitized_result_json", sa.JSON()),
        sa.Column("safe_error_summary", sa.String(1000)),
        sa.Column(
            "requires_approval", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "approved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_agent_tool_calls_run", "agent_tool_calls", ["agent_run_id"])
    op.create_table(
        "agent_approval_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "agent_run_id",
            sa.Uuid(),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tool_call_id",
            sa.Uuid(),
            sa.ForeignKey("agent_tool_calls.id", ondelete="CASCADE"),
            unique=True,
        ),
        sa.Column("approval_type", sa.String(80), nullable=False),
        sa.Column("status", approval_status, nullable=False, server_default="pending"),
        sa.Column(
            "requested_by", sa.String(120), nullable=False, server_default="agent"
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "decided_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_reason", sa.String(1000)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_agent_approvals_status", "agent_approval_requests", ["status"])
    op.create_table(
        "agent_audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("action", audit_action, nullable=False),
        sa.Column(
            "agent_id",
            sa.Uuid(),
            sa.ForeignKey("agent_definitions.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "agent_run_id",
            sa.Uuid(),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "tool_call_id",
            sa.Uuid(),
            sa.ForeignKey("agent_tool_calls.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "approval_request_id",
            sa.Uuid(),
            sa.ForeignKey("agent_approval_requests.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("correlation_id", sa.String(160)),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_agent_audit_created", "agent_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("agent_audit_logs")
    op.drop_table("agent_approval_requests")
    op.drop_table("agent_tool_calls")
    op.drop_table("agent_runs")
    op.drop_table("agent_instruction_versions")
    op.drop_table("agent_definitions")
    op.drop_table("agent_approval_policies")
    op.drop_table("agent_tool_policies")
    op.drop_table("agent_model_policies")
    for enum in (
        audit_action,
        approval_status,
        tool_status,
        run_status,
        agent_type,
        agent_status,
        approval_mode,
    ):
        enum.drop(op.get_bind(), checkfirst=True)
