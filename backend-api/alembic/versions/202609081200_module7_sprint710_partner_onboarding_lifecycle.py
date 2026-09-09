"""Module 7 Sprint 7.10 partner onboarding, access provisioning and lifecycle management.

Revision ID: 202609081200
Revises: 202609071200
Create Date: 2026-09-08 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202609081200"
down_revision: Union[str, None] = "202609071200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

partner_lifecycle_status_enum = sa.Enum(
    "prospect",
    "invited",
    "onboarding",
    "pending_review",
    "approved",
    "active",
    "suspended",
    "terminated",
    name="partner_lifecycle_status_enum",
)

partner_organization_type_enum = sa.Enum(
    "broadcaster",
    "media_network",
    "community_organization",
    "education",
    "business",
    "other",
    name="partner_organization_type_enum",
)

partner_payout_readiness_status_enum = sa.Enum(
    "not_started",
    "configured",
    "verified",
    "blocked",
    name="partner_payout_readiness_status_enum",
)

partner_onboarding_checklist_key_enum = sa.Enum(
    "organization_profile_complete",
    "business_contact_verified",
    "technical_contact_verified",
    "domains_reviewed",
    "syndication_entitlements_approved",
    "api_embed_access_approved",
    "revenue_share_agreement_configured",
    "payout_account_configured",
    "payout_account_verified",
    "portal_access_provisioned",
    name="partner_onboarding_checklist_key_enum",
)

partner_invitation_status_enum = sa.Enum(
    "pending",
    "accepted",
    "revoked",
    "expired",
    name="partner_invitation_status_enum",
)

partner_lifecycle_audit_action_enum = sa.Enum(
    "invitation_created",
    "invitation_accepted",
    "onboarding_submitted",
    "onboarding_returned",
    "partner_approved",
    "partner_activated",
    "partner_suspended",
    "partner_reactivated",
    "partner_terminated",
    "access_provisioned",
    "access_revoked",
    "profile_updated",
    name="partner_lifecycle_audit_action_enum",
)


def upgrade() -> None:
    # 0. Add lifecycle columns to partners table if missing
    with op.batch_alter_table("partners") as batch_op:
        batch_op.add_column(
            sa.Column(
                "lifecycle_status",
                partner_lifecycle_status_enum,
                nullable=False,
                server_default="prospect",
            )
        )
        batch_op.add_column(
            sa.Column("lifecycle_updated_at", sa.DateTime(timezone=True), nullable=True)
        )

    # 1. Partner Onboarding Profiles (1:1 with partners)
    op.create_table(
        "partner_onboarding_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("legal_organization_name", sa.String(length=240), nullable=True),
        sa.Column("display_name", sa.String(length=160), nullable=True),
        sa.Column("organization_type", partner_organization_type_enum, nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("primary_business_contact_json", sa.JSON(), nullable=True),
        sa.Column("finance_contact_json", sa.JSON(), nullable=True),
        sa.Column("technical_contact_json", sa.JSON(), nullable=True),
        sa.Column("approved_domains_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("requested_domains_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("requested_capabilities_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("requested_api_embed_access", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("settlement_currency", sa.String(length=3), nullable=True),
        sa.Column("payout_readiness_status", partner_payout_readiness_status_enum, nullable=False, server_default="not_started"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("review_notes", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("partner_id", name="uq_partner_onboarding_profile"),
    )
    op.create_index(
        "ix_partner_onboarding_profiles_partner",
        "partner_onboarding_profiles",
        ["partner_id"],
        unique=False,
    )

    # 2. Partner Onboarding Checklist Items
    op.create_table(
        "partner_onboarding_checklist_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("item_key", partner_onboarding_checklist_key_enum, nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("derived_from", sa.String(length=120), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("partner_id", "item_key", name="uq_partner_onboarding_checklist_item"),
    )
    op.create_index(
        "ix_partner_onboarding_checklist_partner_complete",
        "partner_onboarding_checklist_items",
        ["partner_id", "is_complete"],
        unique=False,
    )

    # 3. Partner Invitations
    op.create_table(
        "partner_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("target_email", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("status", partner_invitation_status_enum, nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("accepted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_partner_invitation_token_hash"),
    )
    op.create_index(
        "ix_partner_invitations_partner_status",
        "partner_invitations",
        ["partner_id", "status", "expires_at"],
        unique=False,
    )

    # 4. Partner Lifecycle Append-Only Audit Logs
    op.create_table(
        "partner_lifecycle_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("action", partner_lifecycle_audit_action_enum, nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("invitation_id", sa.Uuid(), nullable=True),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invitation_id"], ["partner_invitations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_partner_lifecycle_audit_partner_created",
        "partner_lifecycle_audit_logs",
        ["partner_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_partner_lifecycle_audit_partner_created", table_name="partner_lifecycle_audit_logs")
    op.drop_table("partner_lifecycle_audit_logs")

    op.drop_index("ix_partner_invitations_partner_status", table_name="partner_invitations")
    op.drop_table("partner_invitations")

    op.drop_index("ix_partner_onboarding_checklist_partner_complete", table_name="partner_onboarding_checklist_items")
    op.drop_table("partner_onboarding_checklist_items")

    op.drop_index("ix_partner_onboarding_profiles_partner", table_name="partner_onboarding_profiles")
    op.drop_table("partner_onboarding_profiles")

    with op.batch_alter_table("partners") as batch_op:
        batch_op.drop_column("lifecycle_updated_at")
        batch_op.drop_column("lifecycle_status")
