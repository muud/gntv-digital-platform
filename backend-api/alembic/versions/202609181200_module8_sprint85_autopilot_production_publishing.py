"""Module 8 Sprint 8.5 Autopilot production and publishing orchestration.

Revision ID: 202609181200
Revises: 202609132100
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202609181200"
down_revision: str | None = "202609132100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "autopilot_productions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("brand", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("program_name", sa.String(160)),
        sa.Column("language", sa.String(40), nullable=False, server_default="English"),
        sa.Column("audience", sa.String(160)),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("priority", sa.String(), nullable=False, server_default="normal"),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("assigned_editor_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("workflow_run_id", sa.Uuid()),
        sa.Column("correlation_id", sa.String(160), nullable=False),
        sa.Column("causation_id", sa.String(160)),
        sa.Column("idempotency_key", sa.String(160)),
        sa.Column("target_publish_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
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
        sa.UniqueConstraint("slug", name="uq_autopilot_production_slug"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_autopilot_production_idempotency"
        ),
    )
    op.create_index(
        "ix_autopilot_productions_status", "autopilot_productions", ["status"]
    )
    op.create_index(
        "ix_autopilot_productions_brand", "autopilot_productions", ["brand"]
    )
    op.create_index(
        "ix_autopilot_productions_correlation",
        "autopilot_productions",
        ["correlation_id"],
    )

    op.create_table(
        "autopilot_briefs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "production_id",
            sa.Uuid(),
            sa.ForeignKey("autopilot_productions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("working_title", sa.String(240), nullable=False),
        sa.Column("editorial_goal", sa.Text()),
        sa.Column("target_audience", sa.String(240)),
        sa.Column("key_questions", sa.JSON(), nullable=False),
        sa.Column("required_facts", sa.JSON(), nullable=False),
        sa.Column("required_sources", sa.JSON(), nullable=False),
        sa.Column("tone", sa.String(80)),
        sa.Column("language", sa.String(40), nullable=False, server_default="English"),
        sa.Column("estimated_duration", sa.String(80)),
        sa.Column("presenter", sa.String(160)),
        sa.Column("guests", sa.JSON(), nullable=False),
        sa.Column("location", sa.String(160)),
        sa.Column("production_notes", sa.Text()),
        sa.Column("restrictions", sa.JSON(), nullable=False),
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
        sa.UniqueConstraint("production_id", name="uq_autopilot_brief"),
    )

    op.create_table(
        "autopilot_research_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("production_id", sa.Uuid(), sa.ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("agent_run_id", sa.Uuid(), sa.ForeignKey("agent_runs.id")),
        sa.Column("summary", sa.Text()),
        sa.Column("key_facts", sa.JSON(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("unresolved_questions", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("editorial_notes", sa.Text()),
        sa.Column("generated_material_json", sa.JSON()),
        sa.Column("editor_material_json", sa.JSON()),
        sa.Column("verified_material_json", sa.JSON()),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("production_id", "idempotency_key", name="uq_autopilot_research_idem"),
    )

    op.create_table(
        "autopilot_script_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("production_id", sa.Uuid(), sa.ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(40), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("presenter_notes", sa.Text()),
        sa.Column("graphics_notes", sa.Text()),
        sa.Column("lower_third_notes", sa.Text()),
        sa.Column("source_references", sa.JSON(), nullable=False),
        sa.Column("generated_by_agent_run_id", sa.Uuid(), sa.ForeignKey("agent_runs.id")),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("production_id", "version", name="uq_autopilot_script_version"),
    )

    op.create_table(
        "autopilot_production_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("production_id", sa.Uuid(), sa.ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("presenter", sa.String(160)),
        sa.Column("guests", sa.JSON(), nullable=False),
        sa.Column("studio_location", sa.String(200)),
        sa.Column("camera_requirements", sa.JSON(), nullable=False),
        sa.Column("audio_requirements", sa.JSON(), nullable=False),
        sa.Column("graphics", sa.JSON(), nullable=False),
        sa.Column("lower_thirds", sa.JSON(), nullable=False),
        sa.Column("thumbnails", sa.JSON(), nullable=False),
        sa.Column("b_roll", sa.JSON(), nullable=False),
        sa.Column("teleprompter", sa.Text()),
        sa.Column("music", sa.JSON(), nullable=False),
        sa.Column("subtitles", sa.JSON(), nullable=False),
        sa.Column("language_tracks", sa.JSON(), nullable=False),
        sa.Column("estimated_duration", sa.String(80)),
        sa.Column("recording_date", sa.DateTime(timezone=True)),
        sa.Column("edit_deadline", sa.DateTime(timezone=True)),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("production_id", name="uq_autopilot_plan"),
    )

    op.create_table(
        "autopilot_assets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("production_id", sa.Uuid(), sa.ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_type", sa.String(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("storage_reference", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(120)),
        sa.Column("language", sa.String(40)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("checksum", sa.String(128)),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "autopilot_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("production_id", sa.Uuid(), sa.ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("approval_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("requested_by_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("decided_by_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("decision_reason", sa.String(1000)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "autopilot_publishing_destinations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("account_reference", sa.String(200)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("default_visibility", sa.String(), nullable=False, server_default="private"),
        sa.Column("language", sa.String(40)),
        sa.Column("audience", sa.String(160)),
        sa.Column("publishing_policy", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", "platform", name="uq_autopilot_destination"),
    )

    op.create_table(
        "autopilot_publishing_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("production_id", sa.Uuid(), sa.ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("destination_id", sa.Uuid(), sa.ForeignKey("autopilot_publishing_destinations.id"), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("hashtags", sa.JSON(), nullable=False),
        sa.Column("thumbnail_asset_id", sa.Uuid(), sa.ForeignKey("autopilot_assets.id")),
        sa.Column("language", sa.String(40), nullable=False),
        sa.Column("visibility", sa.String(), nullable=False, server_default="private"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("captions", sa.JSON(), nullable=False),
        sa.Column("audience_classification", sa.String(160)),
        sa.Column("platform_metadata_json", sa.JSON()),
        sa.Column("kids_metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("production_id", "destination_id", name="uq_autopilot_publish_plan_dest"),
    )

    op.create_table(
        "autopilot_publishing_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("production_id", sa.Uuid(), sa.ForeignKey("autopilot_productions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("publishing_plan_id", sa.Uuid(), sa.ForeignKey("autopilot_publishing_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("destination_id", sa.Uuid(), sa.ForeignKey("autopilot_publishing_destinations.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("provider_reference", sa.String(240)),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("safe_error_summary", sa.String(1000)),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("idempotency_key", name="uq_autopilot_attempt_idem"),
    )
    op.create_index("ix_autopilot_attempt_status", "autopilot_publishing_attempts", ["status"])

    op.create_table(
        "autopilot_audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("production_id", sa.Uuid(), sa.ForeignKey("autopilot_productions.id", ondelete="CASCADE")),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("correlation_id", sa.String(160)),
        sa.Column("causation_id", sa.String(160)),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_autopilot_audit_production", "autopilot_audit_logs", ["production_id"])


def downgrade() -> None:
    op.drop_index("ix_autopilot_audit_production", table_name="autopilot_audit_logs")
    op.drop_table("autopilot_audit_logs")
    op.drop_index("ix_autopilot_attempt_status", table_name="autopilot_publishing_attempts")
    op.drop_table("autopilot_publishing_attempts")
    op.drop_table("autopilot_publishing_plans")
    op.drop_table("autopilot_publishing_destinations")
    op.drop_table("autopilot_approvals")
    op.drop_table("autopilot_assets")
    op.drop_table("autopilot_production_plans")
    op.drop_table("autopilot_script_versions")
    op.drop_table("autopilot_research_tasks")
    op.drop_table("autopilot_briefs")
    op.drop_index("ix_autopilot_productions_correlation", table_name="autopilot_productions")
    op.drop_index("ix_autopilot_productions_brand", table_name="autopilot_productions")
    op.drop_index("ix_autopilot_productions_status", table_name="autopilot_productions")
    op.drop_table("autopilot_productions")
