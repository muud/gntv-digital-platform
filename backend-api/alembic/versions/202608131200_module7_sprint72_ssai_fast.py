"""Module 7 Sprint 7.2 SSAI and FAST Channel Packaging tables.

Revision ID: 202608131200
Revises: 202608121200
Create Date: 2026-08-13 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608131200"
down_revision: Union[str, None] = "202608121200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


campaign_status = sa.Enum("draft", "active", "paused", "archived", name="gntv_ad_campaign_status")
creative_type = sa.Enum("video", "audio", name="gntv_ad_creative_type")
break_type = sa.Enum("preroll", "midroll", "postroll", name="gntv_ad_break_type")
impression_event_type = sa.Enum(
    "impression",
    "start",
    "firstQuartile",
    "midpoint",
    "thirdQuartile",
    "complete",
    "error",
    name="gntv_ad_impression_event_type",
)
tracking_event_type = sa.Enum(
    "impression",
    "start",
    "firstQuartile",
    "midpoint",
    "thirdQuartile",
    "complete",
    "error",
    name="gntv_ad_tracking_event_type",
)
tracking_status = sa.Enum("accepted", "duplicate", "rejected", name="gntv_ad_tracking_event_status")


def upgrade() -> None:
    op.create_table(
        "ad_campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", campaign_status, nullable=False, server_default="active"),
        sa.Column("vast_tag_url", sa.String(length=1024), nullable=True),
        sa.Column("vmap_tag_url", sa.String(length=1024), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("end_at IS NULL OR start_at IS NULL OR end_at >= start_at", name="ck_ad_campaign_time_order"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ad_campaigns_owner_status", "ad_campaigns", ["owner_user_id", "status"])

    op.create_table(
        "ad_creatives",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("creative_type", creative_type, nullable=False, server_default="video"),
        sa.Column("media_url", sa.String(length=2048), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False, server_default="video/mp2t"),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("tracking_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("duration_seconds > 0", name="ck_ad_creatives_duration"),
        sa.ForeignKeyConstraint(["campaign_id"], ["ad_campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ad_creatives_campaign", "ad_creatives", ["campaign_id"])

    op.create_table(
        "ad_breaks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("target_id", sa.String(length=160), nullable=False),
        sa.Column("break_type", break_type, nullable=False, server_default="midroll"),
        sa.Column("time_offset_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("scte35_event_id", sa.String(length=120), nullable=True),
        sa.Column("scte35_cue", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("time_offset_seconds >= 0", name="ck_ad_break_offset"),
        sa.CheckConstraint("duration_seconds > 0", name="ck_ad_break_duration"),
        sa.ForeignKeyConstraint(["campaign_id"], ["ad_campaigns.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ad_breaks_target_offset", "ad_breaks", ["target_id", "time_offset_seconds"])
    op.create_index("idx_ad_breaks_campaign", "ad_breaks", ["campaign_id"])

    op.create_table(
        "ad_impressions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("creative_id", sa.Uuid(), nullable=True),
        sa.Column("break_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", impression_event_type, nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["break_id"], ["ad_breaks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["campaign_id"], ["ad_campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["creative_id"], ["ad_creatives.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_ad_impressions_idempotency"),
    )
    op.create_index("idx_ad_impressions_campaign_event", "ad_impressions", ["campaign_id", "event_type"])
    op.create_index("idx_ad_impressions_session", "ad_impressions", ["session_id"])

    op.create_table(
        "ad_tracking_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("impression_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", tracking_event_type, nullable=False),
        sa.Column("tracking_url", sa.String(length=2048), nullable=True),
        sa.Column("signature", sa.String(length=128), nullable=False),
        sa.Column("status", tracking_status, nullable=False, server_default="accepted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["impression_id"], ["ad_impressions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ad_tracking_events_impression", "ad_tracking_events", ["impression_id"])
    op.create_index("idx_ad_tracking_events_type_status", "ad_tracking_events", ["event_type", "status"])


def downgrade() -> None:
    op.drop_index("idx_ad_tracking_events_type_status", table_name="ad_tracking_events")
    op.drop_index("idx_ad_tracking_events_impression", table_name="ad_tracking_events")
    op.drop_table("ad_tracking_events")
    op.drop_index("idx_ad_impressions_session", table_name="ad_impressions")
    op.drop_index("idx_ad_impressions_campaign_event", table_name="ad_impressions")
    op.drop_table("ad_impressions")
    op.drop_index("idx_ad_breaks_campaign", table_name="ad_breaks")
    op.drop_index("idx_ad_breaks_target_offset", table_name="ad_breaks")
    op.drop_table("ad_breaks")
    op.drop_index("idx_ad_creatives_campaign", table_name="ad_creatives")
    op.drop_table("ad_creatives")
    op.drop_index("idx_ad_campaigns_owner_status", table_name="ad_campaigns")
    op.drop_table("ad_campaigns")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS gntv_ad_tracking_event_status")
        op.execute("DROP TYPE IF EXISTS gntv_ad_tracking_event_type")
        op.execute("DROP TYPE IF EXISTS gntv_ad_impression_event_type")
        op.execute("DROP TYPE IF EXISTS gntv_ad_break_type")
        op.execute("DROP TYPE IF EXISTS gntv_ad_creative_type")
        op.execute("DROP TYPE IF EXISTS gntv_ad_campaign_status")
