"""Module 6 Sprint 6.6 Smart TV, Mobile & Accessibility Player Preferences.

Revision ID: 202608091200
Revises: 202608081200
Create Date: 2026-08-09 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608091200"
down_revision: Union[str, None] = "202608081200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_playback_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("preferred_subtitle_lang", sa.String(length=10), nullable=False, server_default="none"),
        sa.Column("preferred_audio_lang", sa.String(length=10), nullable=False, server_default="default"),
        sa.Column("caption_font_size", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("caption_bg_opacity", sa.Float(), nullable=False, server_default="0.75"),
        sa.Column("tv_mode_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_playback_preferences_user"),
    )
    op.create_index(
        "idx_user_pref_user",
        "user_playback_preferences",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_user_pref_user", table_name="user_playback_preferences")
    op.drop_table("user_playback_preferences")
