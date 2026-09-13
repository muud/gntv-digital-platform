"""Module 8 Sprint 8.2 event bus, secure webhooks and automation triggers.

Revision ID: 202609121200
Revises: 202609111200
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202609121200"
down_revision: str | None = "202609111200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

event_status = sa.Enum(
    "received",
    "pending",
    "processing",
    "processed",
    "partially_processed",
    "failed",
    "dead_lettered",
    "ignored",
    name="event_processing_status_enum",
)
webhook_status = sa.Enum(
    "received",
    "verified",
    "rejected",
    "processed",
    "duplicate",
    name="webhook_delivery_status_enum",
)
outbound_status = sa.Enum(
    "pending",
    "delivering",
    "delivered",
    "failed",
    "retry_scheduled",
    "dead_lettered",
    name="outbound_delivery_status_enum",
)
dead_letter_status = sa.Enum(
    "pending", "retried", "dismissed", name="dead_letter_status_enum"
)
audit_action = sa.Enum(
    "event_received",
    "event_dispatched",
    "event_processed",
    "event_failed",
    "event_dead_lettered",
    "webhook_received",
    "webhook_verified",
    "webhook_rejected",
    "webhook_mapped",
    "webhook_duplicate",
    "outbound_delivery_started",
    "outbound_delivery_succeeded",
    "outbound_delivery_failed",
    "outbound_delivery_dead_lettered",
    "dead_letter_retried",
    "dead_letter_dismissed",
    "workflow_triggered_by_event",
    name="event_audit_action_enum",
)


def upgrade() -> None:
    op.add_column(
        "workflow_runs", sa.Column("correlation_id", sa.String(160), nullable=True)
    )
    op.add_column(
        "workflow_runs", sa.Column("causation_id", sa.String(160), nullable=True)
    )
    op.add_column(
        "workflow_step_executions",
        sa.Column("correlation_id", sa.String(160), nullable=True),
    )
    op.add_column(
        "workflow_step_executions",
        sa.Column("causation_id", sa.String(160), nullable=True),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("tenant_id", sa.String(120)),
        sa.Column("aggregate_type", sa.String(80)),
        sa.Column("aggregate_id", sa.String(120)),
        sa.Column("correlation_id", sa.String(120), nullable=False),
        sa.Column("causation_id", sa.String(120)),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("payload_json", sa.JSON()),
        sa.Column("status", event_status, nullable=False),
        sa.Column("error_details_json", sa.JSON()),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "event_type", "idempotency_key", name="uq_event_type_idempotency"
        ),
    )
    op.create_index("ix_events_type_status", "events", ["event_type", "status"])
    op.create_index("ix_events_correlation", "events", ["correlation_id"])
    op.create_index("ix_events_created", "events", ["created_at"])
    op.create_table(
        "webhook_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("provider_type", sa.String(60), nullable=False),
        sa.Column("secret_hash", sa.String(128), nullable=False),
        sa.Column("secret_salt", sa.String(64), nullable=False),
        sa.Column("header_name", sa.String(80), nullable=False),
        sa.Column("timestamp_header", sa.String(80)),
        sa.Column("timestamp_tolerance_seconds", sa.Integer(), nullable=False),
        sa.Column("payload_size_limit_bytes", sa.Integer(), nullable=False),
        sa.Column("event_type_mapping_json", sa.JSON()),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_key", name="uq_webhook_source_key"),
    )
    op.create_index("ix_webhook_sources_enabled", "webhook_sources", ["is_enabled"])
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("webhook_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_event_id", sa.String(160)),
        sa.Column("delivery_fingerprint", sa.String(128), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=False),
        sa.Column("mapped_event_type", sa.String(120)),
        sa.Column("status", webhook_status, nullable=False),
        sa.Column(
            "linked_event_id",
            sa.Uuid(),
            sa.ForeignKey("events.id", ondelete="SET NULL"),
        ),
        sa.Column("safe_payload_json", sa.JSON()),
        sa.Column("rejection_reason", sa.String(500)),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_id", "delivery_fingerprint", name="uq_webhook_delivery_fingerprint"
        ),
        sa.UniqueConstraint(
            "source_id", "external_event_id", name="uq_webhook_delivery_external_event"
        ),
    )
    op.create_index(
        "ix_webhook_deliveries_source_status",
        "webhook_deliveries",
        ["source_id", "status"],
    )
    op.create_index(
        "ix_webhook_deliveries_received", "webhook_deliveries", ["received_at"]
    )
    op.create_table(
        "outbound_webhook_subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("endpoint_url", sa.String(500), nullable=False),
        sa.Column("event_patterns_json", sa.JSON(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("secret_hash", sa.String(128), nullable=False),
        sa.Column("secret_salt", sa.String(64), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_outbound_webhook_subs_enabled",
        "outbound_webhook_subscriptions",
        ["is_enabled"],
    )
    op.create_table(
        "outbound_webhook_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "subscription_id",
            sa.Uuid(),
            sa.ForeignKey("outbound_webhook_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.Uuid(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", outbound_status, nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("response_status_code", sa.Integer()),
        sa.Column("response_body_truncated", sa.String(500)),
        sa.Column("error_message", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_outbound_deliveries_sub_status",
        "outbound_webhook_deliveries",
        ["subscription_id", "status"],
    )
    op.create_index(
        "ix_outbound_deliveries_event", "outbound_webhook_deliveries", ["event_id"]
    )
    op.create_table(
        "event_dead_letters",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="CASCADE")
        ),
        sa.Column(
            "outbound_delivery_id",
            sa.Uuid(),
            sa.ForeignKey("outbound_webhook_deliveries.id", ondelete="CASCADE"),
        ),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("status", dead_letter_status, nullable=False),
        sa.Column(
            "dismissed_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("dismissed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_event_dead_letters_status", "event_dead_letters", ["status"])
    op.create_table(
        "event_audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("action", audit_action, nullable=False),
        sa.Column(
            "event_id", sa.Uuid(), sa.ForeignKey("events.id", ondelete="SET NULL")
        ),
        sa.Column(
            "webhook_source_id",
            sa.Uuid(),
            sa.ForeignKey("webhook_sources.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "webhook_delivery_id",
            sa.Uuid(),
            sa.ForeignKey("webhook_deliveries.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "workflow_run_id",
            sa.Uuid(),
            sa.ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_event_audit_logs_event", "event_audit_logs", ["event_id"])
    op.create_index(
        "ix_event_audit_logs_action_created",
        "event_audit_logs",
        ["action", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_audit_logs_action_created", table_name="event_audit_logs")
    op.drop_index("ix_event_audit_logs_event", table_name="event_audit_logs")
    op.drop_table("event_audit_logs")
    op.drop_index("ix_event_dead_letters_status", table_name="event_dead_letters")
    op.drop_table("event_dead_letters")
    op.drop_index(
        "ix_outbound_deliveries_event", table_name="outbound_webhook_deliveries"
    )
    op.drop_index(
        "ix_outbound_deliveries_sub_status", table_name="outbound_webhook_deliveries"
    )
    op.drop_table("outbound_webhook_deliveries")
    op.drop_index(
        "ix_outbound_webhook_subs_enabled", table_name="outbound_webhook_subscriptions"
    )
    op.drop_table("outbound_webhook_subscriptions")
    op.drop_index("ix_webhook_deliveries_received", table_name="webhook_deliveries")
    op.drop_index(
        "ix_webhook_deliveries_source_status", table_name="webhook_deliveries"
    )
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_webhook_sources_enabled", table_name="webhook_sources")
    op.drop_table("webhook_sources")
    op.drop_index("ix_events_created", table_name="events")
    op.drop_index("ix_events_correlation", table_name="events")
    op.drop_index("ix_events_type_status", table_name="events")
    op.drop_table("events")
    op.drop_column("workflow_step_executions", "causation_id")
    op.drop_column("workflow_step_executions", "correlation_id")
    op.drop_column("workflow_runs", "causation_id")
    op.drop_column("workflow_runs", "correlation_id")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for enum in (
            audit_action,
            dead_letter_status,
            outbound_status,
            webhook_status,
            event_status,
        ):
            enum.drop(bind, checkfirst=True)
