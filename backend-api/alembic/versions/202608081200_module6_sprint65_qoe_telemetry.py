"""Module 6 Sprint 6.5 QoE Telemetry & Observability.

Revision ID: 202608081200
Revises: 202608061800
Create Date: 2026-08-08 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "202608081200"
down_revision: Union[str, None] = "202608061800"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qoe_events_raw",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("playback_session_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("client_timestamp_ms", sa.BigInteger(), nullable=False),
        sa.Column("server_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bitrate_bps", sa.Integer(), nullable=True),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["playback_session_id"], ["playback_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_qoe_raw_session_time",
        "qoe_events_raw",
        ["playback_session_id", "client_timestamp_ms"],
    )

    op.create_table(
        "qoe_session_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("playback_session_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("live_channel_id", sa.Uuid(), nullable=True),
        sa.Column("recording_id", sa.Uuid(), nullable=True),
        sa.Column("startup_latency_ms", sa.Integer(), nullable=True),
        sa.Column("total_rebuffer_duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rebuffer_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rebuffer_ratio", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("average_bitrate_bps", sa.Integer(), nullable=True),
        sa.Column("total_watch_duration_ms", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("completion_ratio", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("device_category", sa.String(length=50), nullable=False, server_default="web"),
        sa.Column("network_type", sa.String(length=50), nullable=False, server_default="unknown"),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("has_error", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["playback_session_id"], ["playback_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["live_channel_id"], ["live_channels.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recording_id"], ["recordings.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("playback_session_id", name="uq_qoe_session_metric_session"),
    )
    op.create_index(
        "idx_qoe_session_target",
        "qoe_session_metrics",
        ["live_channel_id", "recording_id", "created_at"],
    )

    op.create_table(
        "qoe_aggregates_hourly",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("device_category", sa.String(length=50), nullable=False, server_default="all"),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("total_sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("p50_startup_latency_ms", sa.Integer(), nullable=True),
        sa.Column("p95_startup_latency_ms", sa.Integer(), nullable=True),
        sa.Column("avg_rebuffer_ratio", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_bitrate_bps", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_qoe_agg_window_target",
        "qoe_aggregates_hourly",
        ["window_start", "target_id", "device_category"],
    )


def downgrade() -> None:
    op.drop_index("idx_qoe_agg_window_target", table_name="qoe_aggregates_hourly")
    op.drop_table("qoe_aggregates_hourly")

    op.drop_index("idx_qoe_session_target", table_name="qoe_session_metrics")
    op.drop_table("qoe_session_metrics")

    op.drop_index("idx_qoe_raw_session_time", table_name="qoe_events_raw")
    op.drop_table("qoe_events_raw")
