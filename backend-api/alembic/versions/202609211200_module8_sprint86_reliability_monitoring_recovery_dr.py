"""Module 8 Sprint 8.6 Reliability, Monitoring, Recovery & Disaster Recovery.

Revision ID: 202609211200
Revises: 202609181200
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202609211200"
down_revision: str | None = "202609181200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. System Health Snapshots
    op.create_table(
        "reliability_health_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("overall_status", sa.String(32), nullable=False),
        sa.Column("health_score", sa.Float(), nullable=False, server_default="100.0"),
        sa.Column("healthy_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("degraded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unhealthy_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unknown_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("correlation_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_reliability_snapshots_observed", "reliability_health_snapshots", ["observed_at"])
    op.create_index("ix_reliability_snapshots_status", "reliability_health_snapshots", ["overall_status"])

    # 2. Service Health Checks
    op.create_table(
        "reliability_service_health_checks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("reliability_health_snapshots.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("component", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_reliability_checks_comp_status",
        "reliability_service_health_checks",
        ["component", "status"],
    )
    op.create_index("ix_reliability_checks_observed", "reliability_service_health_checks", ["observed_at"])

    # 3. Reliability Incidents
    op.create_table(
        "reliability_incidents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("component", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("causation_id", sa.String(64), nullable=True),
        sa.Column("assigned_to_user_id", sa.Uuid(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("recovery_verification_summary", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_reliability_incidents_comp_state",
        "reliability_incidents",
        ["component", "state"],
    )
    op.create_index("ix_reliability_incidents_severity", "reliability_incidents", ["severity"])
    op.create_index("ix_reliability_incidents_correlation", "reliability_incidents", ["correlation_id"])
    op.create_index("ix_reliability_incidents_created", "reliability_incidents", ["created_at"])

    # 4. Incident Events (Audit Timeline)
    op.create_table(
        "reliability_incident_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "incident_id",
            sa.Uuid(),
            sa.ForeignKey("reliability_incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("from_state", sa.String(32), nullable=True),
        sa.Column("to_state", sa.String(32), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_reliability_inc_events_incident",
        "reliability_incident_events",
        ["incident_id", "created_at"],
    )

    # 5. Alert Rules
    op.create_table(
        "reliability_alert_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("rule_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("component", sa.String(64), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("window_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_reliability_alert_rules_type", "reliability_alert_rules", ["rule_type"])
    op.create_index("ix_reliability_alert_rules_comp", "reliability_alert_rules", ["component"])

    # 6. Alert Occurrences
    op.create_table(
        "reliability_alert_occurrences",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "rule_id",
            sa.Uuid(),
            sa.ForeignKey("reliability_alert_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("component", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("dedup_key", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "incident_id",
            sa.Uuid(),
            sa.ForeignKey("reliability_incidents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_reliability_alert_occ_dedup",
        "reliability_alert_occurrences",
        ["dedup_key", "triggered_at"],
    )
    op.create_index(
        "ix_reliability_alert_occ_incident",
        "reliability_alert_occurrences",
        ["incident_id"],
    )

    # 7. Recovery Runs
    op.create_table(
        "reliability_recovery_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "incident_id",
            sa.Uuid(),
            sa.ForeignKey("reliability_incidents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parameters_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("verification_status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("verification_details", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_reliability_recovery_incident", "reliability_recovery_runs", ["incident_id"])
    op.create_index("ix_reliability_recovery_status", "reliability_recovery_runs", ["status"])
    op.create_index("ix_reliability_recovery_action", "reliability_recovery_runs", ["action_type"])

    # 8. Recovery Steps
    op.create_table(
        "reliability_recovery_steps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "recovery_run_id",
            sa.Uuid(),
            sa.ForeignKey("reliability_recovery_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_reliability_recovery_steps_run",
        "reliability_recovery_steps",
        ["recovery_run_id", "step_order"],
    )

    # 9. Backup Records
    op.create_table(
        "reliability_backup_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("logical_identifier", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False, server_default="MOCK_LOCAL"),
        sa.Column("backup_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_result", sa.String(64), nullable=True),
        sa.Column("verification_details", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_reliability_backups_resource",
        "reliability_backup_records",
        ["resource_type", "logical_identifier"],
    )
    op.create_index("ix_reliability_backups_status", "reliability_backup_records", ["status"])
    op.create_index("ix_reliability_backups_started", "reliability_backup_records", ["started_at"])

    # 10. Disaster Recovery Plans
    op.create_table(
        "reliability_dr_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("plan_version", sa.String(32), unique=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rto_target_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("rpo_target_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("activation_criteria", sa.Text(), nullable=False),
        sa.Column("recovery_priorities_json", sa.JSON(), nullable=False),
        sa.Column("dependencies_json", sa.JSON(), nullable=False),
        sa.Column("verification_checklist_json", sa.JSON(), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("approved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_reliability_dr_plans_active", "reliability_dr_plans", ["is_active"])

    # 11. Resilience Policies
    op.create_table(
        "reliability_resilience_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("component", sa.String(64), nullable=True),
        sa.Column("max_automatic_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("recovery_cooldown_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("escalation_threshold_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("health_failure_threshold", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("incident_deduplication_window_seconds", sa.Integer(), nullable=False, server_default="600"),
        sa.Column("alert_cooldown_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("auto_recovery_permitted", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("human_approval_required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("audit_metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_reliability_policies_component",
        "reliability_resilience_policies",
        ["component", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_reliability_policies_component", table_name="reliability_resilience_policies")
    op.drop_table("reliability_resilience_policies")

    op.drop_index("ix_reliability_dr_plans_active", table_name="reliability_dr_plans")
    op.drop_table("reliability_dr_plans")

    op.drop_index("ix_reliability_backups_started", table_name="reliability_backup_records")
    op.drop_index("ix_reliability_backups_status", table_name="reliability_backup_records")
    op.drop_index("ix_reliability_backups_resource", table_name="reliability_backup_records")
    op.drop_table("reliability_backup_records")

    op.drop_index("ix_reliability_recovery_steps_run", table_name="reliability_recovery_steps")
    op.drop_table("reliability_recovery_steps")

    op.drop_index("ix_reliability_recovery_action", table_name="reliability_recovery_runs")
    op.drop_index("ix_reliability_recovery_status", table_name="reliability_recovery_runs")
    op.drop_index("ix_reliability_recovery_incident", table_name="reliability_recovery_runs")
    op.drop_table("reliability_recovery_runs")

    op.drop_index("ix_reliability_alert_occ_incident", table_name="reliability_alert_occurrences")
    op.drop_index("ix_reliability_alert_occ_dedup", table_name="reliability_alert_occurrences")
    op.drop_table("reliability_alert_occurrences")

    op.drop_index("ix_reliability_alert_rules_comp", table_name="reliability_alert_rules")
    op.drop_index("ix_reliability_alert_rules_type", table_name="reliability_alert_rules")
    op.drop_table("reliability_alert_rules")

    op.drop_index("ix_reliability_inc_events_incident", table_name="reliability_incident_events")
    op.drop_table("reliability_incident_events")

    op.drop_index("ix_reliability_incidents_created", table_name="reliability_incidents")
    op.drop_index("ix_reliability_incidents_correlation", table_name="reliability_incidents")
    op.drop_index("ix_reliability_incidents_severity", table_name="reliability_incidents")
    op.drop_index("ix_reliability_incidents_comp_state", table_name="reliability_incidents")
    op.drop_table("reliability_incidents")

    op.drop_index("ix_reliability_checks_observed", table_name="reliability_service_health_checks")
    op.drop_index("ix_reliability_checks_comp_status", table_name="reliability_service_health_checks")
    op.drop_table("reliability_service_health_checks")

    op.drop_index("ix_reliability_snapshots_status", table_name="reliability_health_snapshots")
    op.drop_index("ix_reliability_snapshots_observed", table_name="reliability_health_snapshots")
    op.drop_table("reliability_health_snapshots")
