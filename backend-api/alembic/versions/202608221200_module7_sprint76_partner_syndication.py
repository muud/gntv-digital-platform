"""Module 7 Sprint 7.6 partner syndication and secure embed SDK.

Revision ID: 202608221200
Revises: 202608191200
Create Date: 2026-08-22 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608221200"
down_revision: Union[str, None] = "202608191200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


partner_status_enum = sa.Enum("active", "suspended", "pending", name="partner_status_enum")
partner_domain_status_enum = sa.Enum("active", "disabled", name="partner_domain_status_enum")
partner_entitlement_status_enum = sa.Enum("active", "revoked", name="partner_entitlement_status_enum")
partner_content_type_enum = sa.Enum("vod", "live_channel", name="partner_content_type_enum")
partner_credential_status_enum = sa.Enum("active", "revoked", name="partner_credential_status_enum")
partner_embed_event_type_enum = sa.Enum(
    "authorize",
    "playback_start",
    "playback_complete",
    "playback_error",
    name="partner_embed_event_type_enum",
)


def upgrade() -> None:
    op.create_table(
        "partners",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("status", partner_status_enum, nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("audit_metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_partners_slug"), "partners", ["slug"], unique=True)
    op.create_index("ix_partners_status_created", "partners", ["status", "created_at"], unique=False)

    op.create_table(
        "partner_domains",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("domain_pattern", sa.String(length=255), nullable=False),
        sa.Column("origin_pattern", sa.String(length=255), nullable=True),
        sa.Column("status", partner_domain_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("partner_id", "domain_pattern", name="uq_partner_domain_pattern"),
    )
    op.create_index("ix_partner_domains_partner_status", "partner_domains", ["partner_id", "status"], unique=False)

    op.create_table(
        "partner_entitlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("content_type", partner_content_type_enum, nullable=False),
        sa.Column("content_id", sa.String(length=255), nullable=False),
        sa.Column("scopes_json", sa.JSON(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", partner_entitlement_status_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("partner_id", "content_type", "content_id", name="uq_partner_content_entitlement"),
    )
    op.create_index(
        "ix_partner_entitlements_content",
        "partner_entitlements",
        ["content_type", "content_id", "status"],
        unique=False,
    )

    op.create_table(
        "partner_api_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("key_prefix", sa.String(length=32), nullable=False),
        sa.Column("secret_hash", sa.String(length=128), nullable=False),
        sa.Column("status", partner_credential_status_enum, nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_partner_api_credentials_key_prefix"), "partner_api_credentials", ["key_prefix"], unique=False)
    op.create_index(
        "ix_partner_credentials_partner_status",
        "partner_api_credentials",
        ["partner_id", "status"],
        unique=False,
    )

    op.create_table(
        "partner_branding",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("logo_url", sa.String(length=500), nullable=True),
        sa.Column("accent_color", sa.String(length=32), nullable=False, server_default="#ff8a00"),
        sa.Column("theme_json", sa.JSON(), nullable=True),
        sa.Column("show_gntv_attribution", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("partner_id"),
    )

    op.create_table(
        "partner_embed_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("content_type", partner_content_type_enum, nullable=False),
        sa.Column("content_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", partner_embed_event_type_enum, nullable=False),
        sa.Column("playback_session_id", sa.String(length=128), nullable=True),
        sa.Column("viewer_session_id_hash", sa.String(length=128), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("origin", sa.String(length=500), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_partner_embed_events_created_at"), "partner_embed_events", ["created_at"], unique=False)
    op.create_index(
        "ix_partner_embed_events_partner_created",
        "partner_embed_events",
        ["partner_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_partner_embed_events_content_created",
        "partner_embed_events",
        ["content_type", "content_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_partner_embed_events_content_created", table_name="partner_embed_events")
    op.drop_index("ix_partner_embed_events_partner_created", table_name="partner_embed_events")
    op.drop_index(op.f("ix_partner_embed_events_created_at"), table_name="partner_embed_events")
    op.drop_table("partner_embed_events")
    op.drop_table("partner_branding")
    op.drop_index("ix_partner_credentials_partner_status", table_name="partner_api_credentials")
    op.drop_index(op.f("ix_partner_api_credentials_key_prefix"), table_name="partner_api_credentials")
    op.drop_table("partner_api_credentials")
    op.drop_index("ix_partner_entitlements_content", table_name="partner_entitlements")
    op.drop_table("partner_entitlements")
    op.drop_index("ix_partner_domains_partner_status", table_name="partner_domains")
    op.drop_table("partner_domains")
    op.drop_index("ix_partners_status_created", table_name="partners")
    op.drop_index(op.f("ix_partners_slug"), table_name="partners")
    op.drop_table("partners")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS partner_embed_event_type_enum")
        op.execute("DROP TYPE IF EXISTS partner_credential_status_enum")
        op.execute("DROP TYPE IF EXISTS partner_content_type_enum")
        op.execute("DROP TYPE IF EXISTS partner_entitlement_status_enum")
        op.execute("DROP TYPE IF EXISTS partner_domain_status_enum")
        op.execute("DROP TYPE IF EXISTS partner_status_enum")
