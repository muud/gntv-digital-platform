"""Module 7 Sprint 7.3 Global Multi-CDN and Edge Acceleration tables.

Revision ID: 202608161200
Revises: 202608160000
Create Date: 2026-08-16 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608161200"
down_revision: Union[str, None] = "202608131200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. cdn_origins table
    op.create_table(
        "cdn_origins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("origin_hostname", sa.String(length=255), nullable=False),
        sa.Column(
            "origin_type",
            sa.Enum("primary", "secondary", "backup", name="cdn_origin_type_enum"),
            nullable=False,
            server_default="primary",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("health_check_path", sa.String(length=255), nullable=False, server_default="/health"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_cdn_origins_active_type", "cdn_origins", ["is_active", "origin_type"], unique=False)
    op.create_index(op.f("ix_cdn_origins_name"), "cdn_origins", ["name"], unique=True)

    # 2. cdn_endpoints table
    op.create_table(
        "cdn_endpoints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("origin_id", sa.Uuid(), nullable=False),
        sa.Column(
            "provider_type",
            sa.Enum("alibaba_dcdn", "fastly", "cloudfront", "generic_cdn", name="cdn_provider_type_enum"),
            nullable=False,
            server_default="alibaba_dcdn",
        ),
        sa.Column("edge_hostname", sa.String(length=255), nullable=False),
        sa.Column("signing_key_ref", sa.String(length=100), nullable=False, server_default="PLAYBACK_SIGNING_SECRET"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "health_status",
            sa.Enum("HEALTHY", "DEGRADED", "UNHEALTHY", name="cdn_health_status_enum"),
            nullable=False,
            server_default="HEALTHY",
        ),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_reason", sa.Text(), nullable=True),
        sa.Column("cache_policy_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["origin_id"], ["cdn_origins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("edge_hostname"),
    )
    op.create_index(op.f("ix_cdn_endpoints_edge_hostname"), "cdn_endpoints", ["edge_hostname"], unique=True)
    op.create_index(op.f("ix_cdn_endpoints_origin_id"), "cdn_endpoints", ["origin_id"], unique=False)
    op.create_index("ix_cdn_endpoints_routing", "cdn_endpoints", ["is_enabled", "health_status", "priority"], unique=False)

    # 3. cdn_health_checks table
    op.create_table(
        "cdn_health_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("HEALTHY", "DEGRADED", "UNHEALTHY", name="cdn_health_check_status_enum"),
            nullable=False,
        ),
        sa.Column("response_latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["endpoint_id"], ["cdn_endpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cdn_health_checks_checked_at"), "cdn_health_checks", ["checked_at"], unique=False)
    op.create_index(op.f("ix_cdn_health_checks_endpoint_id"), "cdn_health_checks", ["endpoint_id"], unique=False)

    # 4. cdn_routing_events table
    op.create_table(
        "cdn_routing_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.String(length=255), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=True),
        sa.Column("routing_reason", sa.String(length=100), nullable=False),
        sa.Column("client_ip", sa.String(length=45), nullable=True),
        sa.Column("decision_metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["endpoint_id"], ["cdn_endpoints.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cdn_routing_events_asset_id"), "cdn_routing_events", ["asset_id"], unique=False)
    op.create_index(op.f("ix_cdn_routing_events_created_at"), "cdn_routing_events", ["created_at"], unique=False)
    op.create_index(op.f("ix_cdn_routing_events_endpoint_id"), "cdn_routing_events", ["endpoint_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_cdn_routing_events_endpoint_id"), table_name="cdn_routing_events")
    op.drop_index(op.f("ix_cdn_routing_events_created_at"), table_name="cdn_routing_events")
    op.drop_index(op.f("ix_cdn_routing_events_asset_id"), table_name="cdn_routing_events")
    op.drop_table("cdn_routing_events")

    op.drop_index(op.f("ix_cdn_health_checks_endpoint_id"), table_name="cdn_health_checks")
    op.drop_index(op.f("ix_cdn_health_checks_checked_at"), table_name="cdn_health_checks")
    op.drop_table("cdn_health_checks")

    op.drop_index("ix_cdn_endpoints_routing", table_name="cdn_endpoints")
    op.drop_index(op.f("ix_cdn_endpoints_origin_id"), table_name="cdn_endpoints")
    op.drop_index(op.f("ix_cdn_endpoints_edge_hostname"), table_name="cdn_endpoints")
    op.drop_table("cdn_endpoints")

    op.drop_index(op.f("ix_cdn_origins_name"), table_name="cdn_origins")
    op.drop_index("ix_cdn_origins_active_type", table_name="cdn_origins")
    op.drop_table("cdn_origins")

    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS cdn_health_check_status_enum")
        op.execute("DROP TYPE IF EXISTS cdn_health_status_enum")
        op.execute("DROP TYPE IF EXISTS cdn_provider_type_enum")
        op.execute("DROP TYPE IF EXISTS cdn_origin_type_enum")
