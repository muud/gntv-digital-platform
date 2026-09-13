"""Module 8 Sprint 8.3 durable workers, scheduler and background job execution.

Revision ID: 202609131200
Revises: 202609121200
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202609131200"
down_revision: str | None = "202609121200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

job_status = sa.Enum(
    "queued",
    "scheduled",
    "claimed",
    "running",
    "waiting_retry",
    "succeeded",
    "failed",
    "cancelled",
    "dead_lettered",
    name="job_status_enum",
)
job_attempt_status = sa.Enum(
    "running",
    "succeeded",
    "failed",
    "timed_out",
    "cancelled",
    name="job_attempt_status_enum",
)
worker_status = sa.Enum(
    "online",
    "draining",
    "offline",
    "unhealthy",
    "dead",
    name="worker_status_enum",
)
schedule_recurrence = sa.Enum(
    "one_time",
    "interval",
    "cron",
    name="schedule_recurrence_type_enum",
)
schedule_misfire = sa.Enum(
    "skip",
    "run_once",
    "catch_up_limited",
    name="schedule_misfire_policy_enum",
)
job_dead_letter_status = sa.Enum(
    "open",
    "retried",
    "requeued",
    "dismissed",
    name="job_dead_letter_status_enum",
)
job_audit_action = sa.Enum(
    "job_enqueued",
    "job_claimed",
    "job_started",
    "job_succeeded",
    "job_failed",
    "job_retry_scheduled",
    "job_cancelled",
    "job_dead_lettered",
    "job_retried",
    "worker_started",
    "worker_heartbeat",
    "worker_draining",
    "worker_offline",
    "schedule_created",
    "schedule_updated",
    "schedule_triggered",
    "schedule_misfired",
    "schedule_enabled",
    "schedule_disabled",
    "dlq_requeued",
    "dlq_dismissed",
    "job_queued",
    name="job_audit_action_enum",
)


def upgrade() -> None:
    # 1. jobs table
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("queue_name", sa.String(80), nullable=False, server_default="default"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", job_status, nullable=False, server_default="queued"),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=True),
        sa.Column("correlation_id", sa.String(160), nullable=False),
        sa.Column("causation_id", sa.String(160), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("retry_delay", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("worker_id", sa.String(120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_details_json", sa.JSON(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("schedule_id", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("job_type", "idempotency_key", name="uq_jobs_type_idempotency"),
    )
    op.create_index("ix_jobs_job_type", "jobs", ["job_type"])
    op.create_index("ix_jobs_queue_name", "jobs", ["queue_name"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_priority", "jobs", ["priority"])
    op.create_index("ix_jobs_correlation_id", "jobs", ["correlation_id"])
    op.create_index("ix_jobs_available_at", "jobs", ["available_at"])
    op.create_index("ix_jobs_worker_id", "jobs", ["worker_id"])
    op.create_index("ix_jobs_lease_expires_at", "jobs", ["lease_expires_at"])
    op.create_index(
        "ix_jobs_claim_poll",
        "jobs",
        ["queue_name", "status", "priority", "available_at"],
    )
    op.create_index(
        "ix_jobs_idempotency",
        "jobs",
        ["job_type", "idempotency_key"],
    )

    # 2. job_attempts table
    op.create_table(
        "job_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(120), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", job_attempt_status, nullable=False, server_default="running"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_job_attempts_job_id", "job_attempts", ["job_id"])
    op.create_index("ix_job_attempts_worker_id", "job_attempts", ["worker_id"])

    # 3. workers table
    op.create_table(
        "workers",
        sa.Column("worker_id", sa.String(120), primary_key=True, nullable=False),
        sa.Column("hostname", sa.String(160), nullable=True),
        sa.Column("queues_json", sa.JSON(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", worker_status, nullable=False, server_default="online"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("active_job_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_job_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_job_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.String(60), nullable=False, server_default="1.0.0"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_workers_status", "workers", ["status"])
    op.create_index("ix_workers_last_heartbeat_at", "workers", ["last_heartbeat_at"])

    # 4. job_schedules table
    op.create_table(
        "job_schedules",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("queue_name", sa.String(80), nullable=False, server_default="default"),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("recurrence_type", schedule_recurrence, nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("cron_expression", sa.String(80), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("misfire_policy", schedule_misfire, nullable=False, server_default="run_once"),
        sa.Column("max_concurrent_runs", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("catch_up_limit", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("active_run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_by", sa.String(120), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_job_schedules_name"),
    )
    op.create_index("ix_job_schedules_is_enabled", "job_schedules", ["is_enabled"])
    op.create_index("ix_job_schedules_next_run_at", "job_schedules", ["next_run_at"])
    op.create_index("ix_job_schedules_job_type", "job_schedules", ["job_type"])
    if op.get_bind().dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_jobs_schedule_id",
            "jobs",
            "job_schedules",
            ["schedule_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "job_schedule_executions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("schedule_id", sa.Uuid(), sa.ForeignKey("job_schedules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False, server_default="enqueued"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("schedule_id", "scheduled_for", name="uq_job_schedule_execution_occurrence"),
    )
    op.create_index("ix_job_schedule_executions_schedule", "job_schedule_executions", ["schedule_id"])

    # 5. job_dead_letters table
    op.create_table(
        "job_dead_letters",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", job_dead_letter_status, nullable=False, server_default="open"),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("error_details_json", sa.JSON(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_job_dead_letters_job_id", "job_dead_letters", ["job_id"])
    op.create_index("ix_job_dead_letters_status", "job_dead_letters", ["status"])

    # 6. job_audit_logs table
    op.create_table(
        "job_audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("action", job_audit_action, nullable=False),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("worker_id", sa.String(120), nullable=True),
        sa.Column(
            "schedule_id",
            sa.Uuid(),
            sa.ForeignKey("job_schedules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_job_audit_logs_action", "job_audit_logs", ["action"])
    op.create_index("ix_job_audit_logs_job_id", "job_audit_logs", ["job_id"])
    op.create_index("ix_job_audit_logs_schedule_id", "job_audit_logs", ["schedule_id"])
    op.create_index("ix_job_audit_logs_created_at", "job_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("job_audit_logs")
    op.drop_table("job_dead_letters")
    op.drop_table("job_schedule_executions")
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("fk_jobs_schedule_id", "jobs", type_="foreignkey")
    op.drop_table("job_schedules")
    op.drop_table("workers")
    op.drop_table("job_attempts")
    op.drop_table("jobs")

    job_audit_action.drop(op.get_bind(), checkfirst=True)
    job_dead_letter_status.drop(op.get_bind(), checkfirst=True)
    schedule_misfire.drop(op.get_bind(), checkfirst=True)
    schedule_recurrence.drop(op.get_bind(), checkfirst=True)
    worker_status.drop(op.get_bind(), checkfirst=True)
    job_attempt_status.drop(op.get_bind(), checkfirst=True)
    job_status.drop(op.get_bind(), checkfirst=True)
