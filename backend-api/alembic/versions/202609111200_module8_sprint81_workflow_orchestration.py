"""Module 8 Sprint 8.1 Workflow Orchestration & Job Execution Platform.

Revision ID: 202609111200
Revises: 202609081200
Create Date: 2026-09-11 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202609111200"
down_revision: Union[str, None] = "202609081200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

workflow_status_enum = sa.Enum(
    "draft",
    "active",
    "paused",
    "archived",
    name="workflow_status_enum",
)

workflow_run_status_enum = sa.Enum(
    "queued",
    "running",
    "waiting",
    "succeeded",
    "failed",
    "cancelled",
    "partially_succeeded",
    name="workflow_run_status_enum",
)

workflow_step_status_enum = sa.Enum(
    "pending",
    "running",
    "waiting",
    "succeeded",
    "failed",
    "skipped",
    "cancelled",
    name="workflow_step_status_enum",
)

workflow_step_type_enum = sa.Enum(
    "HTTP_INTERNAL",
    "CONTENT_VALIDATE",
    "CONTENT_PUBLISH_REQUEST",
    "DISTRIBUTION_REQUEST",
    "REPORT_GENERATION",
    "NOTIFICATION_EVENT",
    "MANUAL_APPROVAL",
    "DELAY",
    "CONDITIONAL",
    name="workflow_step_type_enum",
)

workflow_trigger_type_enum = sa.Enum(
    "manual",
    "scheduled",
    "internal_event",
    name="workflow_trigger_type_enum",
)

workflow_audit_action_enum = sa.Enum(
    "workflow_created",
    "workflow_updated",
    "workflow_activated",
    "workflow_paused",
    "run_queued",
    "run_started",
    "step_started",
    "step_succeeded",
    "step_failed",
    "approval_requested",
    "step_approved",
    "step_rejected",
    "run_succeeded",
    "run_failed",
    "run_cancelled",
    name="workflow_audit_action_enum",
)


def upgrade() -> None:
    # 1. Workflows definition table
    op.create_table(
        "workflows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("workflow_type", sa.String(length=80), nullable=False, server_default="standard"),
        sa.Column("status", workflow_status_enum, nullable=False, server_default="draft"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("retry_policy_json", sa.JSON(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_workflow_name_version"),
    )
    op.create_index("ix_workflows_status", "workflows", ["status"], unique=False)
    op.create_index("ix_workflows_name_version", "workflows", ["name", "version"], unique=False)

    # 2. Workflow step definitions
    op.create_table(
        "workflow_step_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("step_type", workflow_step_type_enum, nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("retry_delay_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("backoff_multiplier", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", "step_order", name="uq_workflow_step_order"),
    )
    op.create_index("ix_workflow_steps_workflow", "workflow_step_definitions", ["workflow_id", "step_order"], unique=False)

    # 3. Workflow runs
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", workflow_run_status_enum, nullable=False, server_default="queued"),
        sa.Column("trigger_type", workflow_trigger_type_enum, nullable=False, server_default="manual"),
        sa.Column("trigger_source", sa.String(length=120), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("current_step_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_metadata_json", sa.JSON(), nullable=True),
        sa.Column("output_metadata_json", sa.JSON(), nullable=True),
        sa.Column("error_summary", sa.String(length=1000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", "idempotency_key", name="uq_workflow_run_idempotency"),
    )
    op.create_index("ix_workflow_runs_workflow_status", "workflow_runs", ["workflow_id", "status"], unique=False)
    op.create_index("ix_workflow_runs_status_created", "workflow_runs", ["status", "created_at"], unique=False)

    # 4. Workflow step executions
    op.create_table(
        "workflow_step_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_definition_id", sa.Uuid(), nullable=True),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(length=160), nullable=False),
        sa.Column("step_type", workflow_step_type_enum, nullable=False),
        sa.Column("status", workflow_step_status_enum, nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("retry_delay_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("backoff_multiplier", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retryable_failure", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("input_json", sa.JSON(), nullable=True),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("error_details_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_definition_id"], ["workflow_step_definitions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "step_order", name="uq_run_step_order"),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_run_step_idempotency"),
    )
    op.create_index("ix_workflow_step_executions_run", "workflow_step_executions", ["run_id", "status"], unique=False)

    # 5. Workflow triggers
    op.create_table(
        "workflow_triggers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("trigger_type", workflow_trigger_type_enum, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("event_pattern", sa.String(length=120), nullable=True),
        sa.Column("schedule_cron", sa.String(length=60), nullable=True),
        sa.Column("schedule_timezone", sa.String(length=40), nullable=False, server_default="UTC"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_triggers_workflow", "workflow_triggers", ["workflow_id", "is_enabled"], unique=False)

    # 6. Workflow schedules
    op.create_table(
        "workflow_schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_type", sa.String(length=32), nullable=False, server_default="recurring"),
        sa.Column("cron_expression", sa.String(length=80), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=40), nullable=False, server_default="UTC"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_schedules_next_run", "workflow_schedules", ["is_enabled", "next_run_at"], unique=False)

    # 7. Workflow audit logs
    op.create_table(
        "workflow_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("step_execution_id", sa.Uuid(), nullable=True),
        sa.Column("action", workflow_audit_action_enum, nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["step_execution_id"], ["workflow_step_executions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_audit_logs_workflow_created", "workflow_audit_logs", ["workflow_id", "created_at"], unique=False)
    op.create_index("ix_workflow_audit_logs_run_created", "workflow_audit_logs", ["run_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("workflow_audit_logs")
    op.drop_table("workflow_schedules")
    op.drop_table("workflow_triggers")
    op.drop_table("workflow_step_executions")
    op.drop_table("workflow_runs")
    op.drop_table("workflow_step_definitions")
    op.drop_table("workflows")

    workflow_audit_action_enum.drop(op.get_bind(), checkfirst=True)
    workflow_trigger_type_enum.drop(op.get_bind(), checkfirst=True)
    workflow_step_type_enum.drop(op.get_bind(), checkfirst=True)
    workflow_step_status_enum.drop(op.get_bind(), checkfirst=True)
    workflow_run_status_enum.drop(op.get_bind(), checkfirst=True)
    workflow_status_enum.drop(op.get_bind(), checkfirst=True)
