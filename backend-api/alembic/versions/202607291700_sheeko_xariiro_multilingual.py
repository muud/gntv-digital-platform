"""Sheeko Xariiro five-language voice workflow.

Revision ID: 202607291700
Revises: 202607241900
"""

from alembic import op
import sqlalchemy as sa


revision = "202607291700"
down_revision = "202607241900"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sheeko_xariiro_episodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("episode_title", sa.String(240), nullable=False),
        sa.Column("slug", sa.String(240), nullable=False),
        sa.Column("original_script", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "sheeko_xariiro_language_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("language_code", sa.String(2), nullable=False),
        sa.Column("iso_639_3", sa.String(3), nullable=False),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("character_assignments", sa.JSON(), nullable=False),
        sa.Column("athero_voice_id", sa.String(128)),
        sa.Column("narrator_voice_id", sa.String(128)),
        sa.Column("character_voices", sa.JSON(), nullable=False),
        sa.Column("pronunciation_notes", sa.Text(), nullable=False),
        sa.Column("generated_audio_url", sa.String(1000)),
        sa.Column("subtitle_url", sa.String(1000)),
        sa.Column("translation_review_status", sa.String(24), nullable=False),
        sa.Column("voice_review_status", sa.String(24), nullable=False),
        sa.Column("final_approval_status", sa.String(24), nullable=False),
        sa.Column("reviewed_by", sa.Integer()),
        sa.Column("approved_by", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["episode_id"], ["sheeko_xariiro_episodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "episode_id", "language_code", name="uq_sheeko_episode_language"
        ),
    )
    op.create_index(
        "idx_sheeko_language_review",
        "sheeko_xariiro_language_versions",
        ["language_code", "final_approval_status"],
    )
    op.create_table(
        "sheeko_xariiro_audio_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("language_version_id", sa.Uuid(), nullable=False),
        sa.Column("scene_number", sa.Integer(), nullable=False),
        sa.Column("character_name", sa.String(120), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("provider", sa.String(64)),
        sa.Column("voice_id", sa.String(128)),
        sa.Column("model_id", sa.String(128)),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("media_url", sa.String(1000), nullable=False),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["language_version_id"],
            ["sheeko_xariiro_language_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sheeko_xariiro_voice_presets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("preset_name", sa.String(80), nullable=False),
        sa.Column("character_name", sa.String(120), nullable=False),
        sa.Column("language_code", sa.String(2), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("voice_id", sa.String(128), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "preset_name",
            "language_code",
            name="uq_sheeko_voice_preset_language",
        ),
    )
    op.create_table(
        "sheeko_xariiro_generation_audits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("language_code", sa.String(2), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["episode_id"], ["sheeko_xariiro_episodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("sheeko_xariiro_generation_audits")
    op.drop_table("sheeko_xariiro_voice_presets")
    op.drop_table("sheeko_xariiro_audio_assets")
    op.drop_index(
        "idx_sheeko_language_review",
        table_name="sheeko_xariiro_language_versions",
    )
    op.drop_table("sheeko_xariiro_language_versions")
    op.drop_table("sheeko_xariiro_episodes")
