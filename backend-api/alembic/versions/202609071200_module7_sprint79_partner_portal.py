"""Module 7 Sprint 7.9 partner portal events.

Revision ID: 202609071200
Revises: 202609051200
Create Date: 2026-09-07 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202609071200"
down_revision: Union[str, None] = "202609051200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


partner_portal_event_type_enum = sa.Enum(
    "settlement_finalized",
    "payout_approved",
    "payout_processing",
    "payout_paid",
    "payout_failed",
    "reconciliation_exception",
    name="partner_portal_event_type_enum",
)


def upgrade() -> None:
    op.create_table(
        "partner_portal_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("partner_id", "user_id", name="uq_partner_portal_user"),
    )
    op.create_index("ix_partner_portal_users_user", "partner_portal_users", ["user_id"], unique=False)

    op.create_table(
        "partner_portal_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", partner_portal_event_type_enum, nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=True),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=False, server_default="info"),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("visible_to_partner", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_partner_portal_events_partner_created",
        "partner_portal_events",
        ["partner_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_partner_portal_events_partner_type",
        "partner_portal_events",
        ["partner_id", "event_type", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_partner_portal_events_partner_type", table_name="partner_portal_events")
    op.drop_index("ix_partner_portal_events_partner_created", table_name="partner_portal_events")
    op.drop_table("partner_portal_events")
    op.drop_index("ix_partner_portal_users_user", table_name="partner_portal_users")
    op.drop_table("partner_portal_users")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS partner_portal_event_type_enum")
