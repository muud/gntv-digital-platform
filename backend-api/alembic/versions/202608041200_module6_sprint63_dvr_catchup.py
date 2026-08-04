"""Module 6 Sprint 6.3 DVR and catch-up.

Revision ID: 202608041200
Revises: 202607291700
Create Date: 2026-08-04 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision = "202608041200"
down_revision = "202607291700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("live_channels") as batch:
        batch.add_column(
            sa.Column("dvr_window_seconds", sa.Integer(), nullable=False, server_default="7200")
        )
        batch.add_column(
            sa.Column("catchup_retention_days", sa.Integer(), nullable=False, server_default="7")
        )
        batch.add_column(
            sa.Column("dvr_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.create_check_constraint("ck_live_channels_dvr_window", "dvr_window_seconds >= 0")
        batch.create_check_constraint(
            "ck_live_channels_catchup_retention",
            "catchup_retention_days >= 0",
        )

    with op.batch_alter_table("recordings") as batch:
        batch.add_column(sa.Column("start_sequence_number", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("end_sequence_number", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("epg_event_id", sa.String(length=160), nullable=True))
        batch.create_check_constraint(
            "ck_recording_start_sequence",
            "start_sequence_number IS NULL OR start_sequence_number >= 0",
        )
        batch.create_check_constraint(
            "ck_recording_end_sequence",
            "end_sequence_number IS NULL OR end_sequence_number >= 0",
        )
        batch.create_check_constraint(
            "ck_recording_sequence_order",
            "end_sequence_number IS NULL OR start_sequence_number IS NULL "
            "OR end_sequence_number >= start_sequence_number",
        )
        batch.create_index("idx_recordings_epg_event", ["epg_event_id"])

    op.create_table(
        "dvr_segment_index",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("live_channel_id", sa.Uuid(), nullable=False),
        sa.Column("stream_id", sa.Uuid(), nullable=True),
        sa.Column("live_event_id", sa.Uuid(), nullable=True),
        sa.Column("recording_id", sa.Uuid(), nullable=True),
        sa.Column("rendition", sa.String(length=80), nullable=False, server_default="source"),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False),
        sa.Column("segment_uri", sa.String(length=2048), nullable=False),
        sa.Column("segment_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("segment_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("provider_event_id", sa.String(length=200), nullable=True),
        sa.Column("apsara_object_key", sa.String(length=1024), nullable=True),
        sa.Column("is_pruned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["live_channel_id"], ["live_channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stream_id"], ["streams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["live_event_id"], ["live_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recording_id"], ["recordings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "live_channel_id",
            "rendition",
            "sequence_number",
            name="uq_dvr_segment_channel_rendition_sequence",
        ),
        sa.CheckConstraint("sequence_number >= 0", name="ck_dvr_segment_sequence"),
        sa.CheckConstraint("duration_seconds > 0", name="ck_dvr_segment_duration"),
        sa.CheckConstraint("segment_end_at > segment_start_at", name="ck_dvr_segment_time_order"),
    )
    op.create_index(
        "idx_dvr_segment_channel_time",
        "dvr_segment_index",
        ["live_channel_id", "segment_start_at"],
    )
    op.create_index(
        "idx_dvr_segment_channel_live_event",
        "dvr_segment_index",
        ["live_channel_id", "live_event_id"],
    )
    op.create_index(
        "idx_dvr_segment_recording_sequence",
        "dvr_segment_index",
        ["recording_id", "sequence_number"],
    )
    op.create_index("idx_dvr_segment_provider_event", "dvr_segment_index", ["provider_event_id"])
    op.create_index(
        "idx_dvr_segment_prune",
        "dvr_segment_index",
        ["live_channel_id", "segment_end_at", "is_pruned"],
    )


def downgrade() -> None:
    op.drop_index("idx_dvr_segment_prune", table_name="dvr_segment_index")
    op.drop_index("idx_dvr_segment_provider_event", table_name="dvr_segment_index")
    op.drop_index("idx_dvr_segment_recording_sequence", table_name="dvr_segment_index")
    op.drop_index("idx_dvr_segment_channel_live_event", table_name="dvr_segment_index")
    op.drop_index("idx_dvr_segment_channel_time", table_name="dvr_segment_index")
    op.drop_table("dvr_segment_index")

    with op.batch_alter_table("recordings") as batch:
        batch.drop_index("idx_recordings_epg_event")
        batch.drop_constraint("ck_recording_sequence_order", type_="check")
        batch.drop_constraint("ck_recording_end_sequence", type_="check")
        batch.drop_constraint("ck_recording_start_sequence", type_="check")
        batch.drop_column("epg_event_id")
        batch.drop_column("end_sequence_number")
        batch.drop_column("start_sequence_number")

    with op.batch_alter_table("live_channels") as batch:
        batch.drop_constraint("ck_live_channels_catchup_retention", type_="check")
        batch.drop_constraint("ck_live_channels_dvr_window", type_="check")
        batch.drop_column("dvr_enabled")
        batch.drop_column("catchup_retention_days")
        batch.drop_column("dvr_window_seconds")
