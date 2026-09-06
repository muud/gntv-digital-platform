"""Module 7 Sprint 7.8 partner payout orchestration.

Revision ID: 202609051200
Revises: 202609041200
Create Date: 2026-09-05 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202609051200"
down_revision: Union[str, None] = "202609041200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


partner_payout_account_status_enum = sa.Enum("enabled", "disabled", name="partner_payout_account_status_enum")
partner_payout_verification_status_enum = sa.Enum(
    "unverified",
    "pending",
    "verified",
    "failed",
    name="partner_payout_verification_status_enum",
)
partner_payout_provider_type_enum = sa.Enum("mock", "external_reference", name="partner_payout_provider_type_enum")
partner_payout_status_enum = sa.Enum(
    "pending",
    "approved",
    "processing",
    "paid",
    "failed",
    "cancelled",
    "reversed",
    name="partner_payout_status_enum",
)
partner_payout_reconciliation_outcome_enum = sa.Enum(
    "matched",
    "duplicate_provider_transaction",
    "amount_mismatch",
    "currency_mismatch",
    "unknown_transaction",
    "failed_or_returned",
    name="partner_payout_reconciliation_outcome_enum",
)
partner_payout_audit_action_enum = sa.Enum(
    "payout_account_created",
    "payout_account_updated",
    "payout_created",
    "payout_approved",
    "payout_executed",
    "payout_failed",
    "payout_cancelled",
    "payout_reversed",
    "payout_reconciled",
    name="partner_payout_audit_action_enum",
)


def upgrade() -> None:
    op.create_table(
        "partner_payout_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("provider_type", partner_payout_provider_type_enum, nullable=False),
        sa.Column("destination_label", sa.String(length=160), nullable=False),
        sa.Column("destination_reference", sa.String(length=255), nullable=False),
        sa.Column("encrypted_provider_metadata", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", partner_payout_account_status_enum, nullable=False),
        sa.Column("verification_status", partner_payout_verification_status_enum, nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("partner_id", "idempotency_key", name="uq_partner_payout_account_idempotency"),
    )
    op.create_index(
        "ix_partner_payout_accounts_partner_status",
        "partner_payout_accounts",
        ["partner_id", "status", "verification_status"],
        unique=False,
    )

    op.create_table(
        "partner_payouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("settlement_id", sa.Uuid(), nullable=False),
        sa.Column("payout_account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", partner_payout_status_enum, nullable=False),
        sa.Column("provider_type", partner_payout_provider_type_enum, nullable=False),
        sa.Column("provider_payout_id", sa.String(length=160), nullable=True),
        sa.Column("provider_transaction_id", sa.String(length=160), nullable=True),
        sa.Column("provider_execution_key", sa.String(length=160), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payout_account_id"], ["partner_payout_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["settlement_id"], ["partner_settlement_statements.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("partner_id", "idempotency_key", name="uq_partner_payout_idempotency"),
        sa.UniqueConstraint("provider_type", "provider_transaction_id", name="uq_partner_payout_provider_transaction"),
        sa.UniqueConstraint("settlement_id", name="uq_partner_payout_settlement"),
    )
    op.create_index(
        "ix_partner_payouts_partner_status",
        "partner_payouts",
        ["partner_id", "status", "created_at"],
        unique=False,
    )

    op.create_table(
        "partner_payout_reconciliations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("payout_id", sa.Uuid(), nullable=True),
        sa.Column("provider_type", partner_payout_provider_type_enum, nullable=False),
        sa.Column("provider_transaction_id", sa.String(length=160), nullable=False),
        sa.Column("reported_amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("reported_currency", sa.String(length=3), nullable=False),
        sa.Column("provider_status", sa.String(length=80), nullable=False),
        sa.Column("outcome", partner_payout_reconciliation_outcome_enum, nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("reconciled_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payout_id"], ["partner_payouts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reconciled_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("partner_id", "idempotency_key", name="uq_partner_reconciliation_idempotency"),
    )
    op.create_index(
        "ix_partner_reconciliation_provider_txn",
        "partner_payout_reconciliations",
        ["provider_type", "provider_transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_partner_reconciliation_partner_created",
        "partner_payout_reconciliations",
        ["partner_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "partner_payout_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("payout_account_id", sa.Uuid(), nullable=True),
        sa.Column("payout_id", sa.Uuid(), nullable=True),
        sa.Column("reconciliation_id", sa.Uuid(), nullable=True),
        sa.Column("action", partner_payout_audit_action_enum, nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("provider_reference", sa.String(length=160), nullable=True),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payout_account_id"], ["partner_payout_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payout_id"], ["partner_payouts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reconciliation_id"], ["partner_payout_reconciliations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_partner_payout_audit_partner_created",
        "partner_payout_audit_logs",
        ["partner_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_partner_payout_audit_partner_created", table_name="partner_payout_audit_logs")
    op.drop_table("partner_payout_audit_logs")
    op.drop_index("ix_partner_reconciliation_partner_created", table_name="partner_payout_reconciliations")
    op.drop_index("ix_partner_reconciliation_provider_txn", table_name="partner_payout_reconciliations")
    op.drop_table("partner_payout_reconciliations")
    op.drop_index("ix_partner_payouts_partner_status", table_name="partner_payouts")
    op.drop_table("partner_payouts")
    op.drop_index("ix_partner_payout_accounts_partner_status", table_name="partner_payout_accounts")
    op.drop_table("partner_payout_accounts")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS partner_payout_audit_action_enum")
        op.execute("DROP TYPE IF EXISTS partner_payout_reconciliation_outcome_enum")
        op.execute("DROP TYPE IF EXISTS partner_payout_status_enum")
        op.execute("DROP TYPE IF EXISTS partner_payout_provider_type_enum")
        op.execute("DROP TYPE IF EXISTS partner_payout_verification_status_enum")
        op.execute("DROP TYPE IF EXISTS partner_payout_account_status_enum")
