"""Module 7 Sprint 7.7 partner billing and settlement.

Revision ID: 202609041200
Revises: 202608221200
Create Date: 2026-09-04 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202609041200"
down_revision: Union[str, None] = "202608221200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


partner_revenue_share_rule_type_enum = sa.Enum(
    "fixed_percentage",
    "tiered_percentage",
    name="partner_revenue_share_rule_type_enum",
)
partner_usage_event_type_enum = sa.Enum(
    "playback_start",
    "playback_complete",
    "ad_impression",
    "ad_complete",
    "ad_revenue",
    "adjustment",
    name="partner_usage_event_type_enum",
)
partner_settlement_status_enum = sa.Enum(
    "draft",
    "finalized",
    "paid",
    "disputed",
    "void",
    name="partner_settlement_status_enum",
)
partner_financial_audit_action_enum = sa.Enum(
    "usage_recorded",
    "agreement_created",
    "settlement_generated",
    "settlement_status_changed",
    name="partner_financial_audit_action_enum",
)
partner_content_type_enum = postgresql.ENUM(
    "vod",
    "live_channel",
    name="partner_content_type_enum",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "partner_revenue_share_agreements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("rule_type", partner_revenue_share_rule_type_enum, nullable=False),
        sa.Column("fixed_partner_percentage", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("tiers_json", sa.JSON(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_partner_revshare_partner_active",
        "partner_revenue_share_agreements",
        ["partner_id", "is_active", "starts_at", "ends_at"],
        unique=False,
    )

    op.create_table(
        "partner_usage_metering",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("content_type", partner_content_type_enum, nullable=False),
        sa.Column("content_id", sa.String(length=255), nullable=False),
        sa.Column("usage_event_type", partner_usage_event_type_enum, nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "gross_revenue_amount",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default="0.000000",
        ),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("source_event_id", sa.String(length=160), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("partner_id", "idempotency_key", name="uq_partner_usage_idempotency"),
    )
    op.create_index(
        "ix_partner_usage_partner_period",
        "partner_usage_metering",
        ["partner_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_partner_usage_content_period",
        "partner_usage_metering",
        ["content_type", "content_id", "occurred_at"],
        unique=False,
    )

    op.create_table(
        "partner_settlement_statements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("agreement_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "gross_revenue_amount",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default="0.000000",
        ),
        sa.Column(
            "platform_share_amount",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default="0.000000",
        ),
        sa.Column(
            "partner_share_amount",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default="0.000000",
        ),
        sa.Column(
            "adjustment_amount",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default="0.000000",
        ),
        sa.Column(
            "net_settlement_amount",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default="0.000000",
        ),
        sa.Column("status", partner_settlement_status_enum, nullable=False),
        sa.Column("calculation_json", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("generated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agreement_id"], ["partner_revenue_share_agreements.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["generated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("partner_id", "idempotency_key", name="uq_partner_settlement_idempotency"),
        sa.UniqueConstraint(
            "partner_id",
            "period_start",
            "period_end",
            "currency",
            name="uq_partner_settlement_period",
        ),
    )
    op.create_index(
        "ix_partner_settlement_status_period",
        "partner_settlement_statements",
        ["status", "period_start", "period_end"],
        unique=False,
    )

    op.create_table(
        "partner_financial_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("statement_id", sa.Uuid(), nullable=True),
        sa.Column("action", partner_financial_audit_action_enum, nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["statement_id"], ["partner_settlement_statements.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_partner_financial_audit_partner_created",
        "partner_financial_audit_logs",
        ["partner_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_partner_financial_audit_partner_created", table_name="partner_financial_audit_logs")
    op.drop_table("partner_financial_audit_logs")
    op.drop_index("ix_partner_settlement_status_period", table_name="partner_settlement_statements")
    op.drop_table("partner_settlement_statements")
    op.drop_index("ix_partner_usage_content_period", table_name="partner_usage_metering")
    op.drop_index("ix_partner_usage_partner_period", table_name="partner_usage_metering")
    op.drop_table("partner_usage_metering")
    op.drop_index("ix_partner_revshare_partner_active", table_name="partner_revenue_share_agreements")
    op.drop_table("partner_revenue_share_agreements")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS partner_financial_audit_action_enum")
        op.execute("DROP TYPE IF EXISTS partner_settlement_status_enum")
        op.execute("DROP TYPE IF EXISTS partner_usage_event_type_enum")
        op.execute("DROP TYPE IF EXISTS partner_revenue_share_rule_type_enum")
