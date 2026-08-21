"""Module 7 Sprint 7.4 CDN observability and traffic optimization.

Revision ID: 202608191200
Revises: 202608161200
Create Date: 2026-08-19 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "202608191200"
down_revision: Union[str, None] = "202608161200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


granularity_enum = sa.Enum("raw", "hourly", "daily", name="cdn_metric_granularity_enum")


def existing_provider_enum() -> sa.Enum:
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.ENUM(
            "alibaba_dcdn",
            "fastly",
            "cloudfront",
            "generic_cdn",
            name="cdn_provider_type_enum",
            create_type=False,
        )
    return sa.Enum("alibaba_dcdn", "fastly", "cloudfront", "generic_cdn", name="cdn_provider_type_enum")


def existing_health_enum() -> sa.Enum:
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.ENUM("HEALTHY", "DEGRADED", "UNHEALTHY", name="cdn_health_status_enum", create_type=False)
    return sa.Enum("HEALTHY", "DEGRADED", "UNHEALTHY", name="cdn_health_status_enum")


def upgrade() -> None:
    provider_enum = existing_provider_enum()
    health_enum = existing_health_enum()
    op.create_table(
        "cdn_endpoint_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=False),
        sa.Column("provider_type", provider_enum, nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=False, server_default="global"),
        sa.Column("granularity", granularity_enum, nullable=False, server_default="raw"),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bandwidth_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_miss_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("origin_fetch_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("p95_latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("http_4xx_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("http_5xx_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("health_status", health_enum, nullable=False, server_default="HEALTHY"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["endpoint_id"], ["cdn_endpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cdn_endpoint_metrics_endpoint_id"), "cdn_endpoint_metrics", ["endpoint_id"], unique=False)
    op.create_index(op.f("ix_cdn_endpoint_metrics_window_start"), "cdn_endpoint_metrics", ["window_start"], unique=False)
    op.create_index(
        "ix_cdn_endpoint_metrics_endpoint_window",
        "cdn_endpoint_metrics",
        ["endpoint_id", "granularity", "window_start"],
        unique=False,
    )
    op.create_index(
        "ix_cdn_endpoint_metrics_provider_region",
        "cdn_endpoint_metrics",
        ["provider_type", "region_code", "window_start"],
        unique=False,
    )

    op.create_table(
        "cdn_provider_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_type", provider_enum, nullable=False),
        sa.Column("region_code", sa.String(length=32), nullable=False, server_default="global"),
        sa.Column("granularity", granularity_enum, nullable=False, server_default="hourly"),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bandwidth_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_miss_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("origin_fetch_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("p95_latency_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("http_4xx_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("http_5xx_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("health_status", health_enum, nullable=False, server_default="HEALTHY"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cdn_provider_metrics_window_start"), "cdn_provider_metrics", ["window_start"], unique=False)
    op.create_index(
        "ix_cdn_provider_metrics_provider_window",
        "cdn_provider_metrics",
        ["provider_type", "granularity", "window_start"],
        unique=False,
    )
    op.create_index(
        "ix_cdn_provider_metrics_region_window",
        "cdn_provider_metrics",
        ["region_code", "granularity", "window_start"],
        unique=False,
    )

    op.create_table(
        "cdn_failover_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("from_endpoint_id", sa.Uuid(), nullable=True),
        sa.Column("to_endpoint_id", sa.Uuid(), nullable=True),
        sa.Column("provider_type", provider_enum, nullable=True),
        sa.Column("region_code", sa.String(length=32), nullable=False, server_default="global"),
        sa.Column("asset_id", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("decision_metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["from_endpoint_id"], ["cdn_endpoints.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["to_endpoint_id"], ["cdn_endpoints.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cdn_failover_events_asset_id"), "cdn_failover_events", ["asset_id"], unique=False)
    op.create_index(op.f("ix_cdn_failover_events_created_at"), "cdn_failover_events", ["created_at"], unique=False)
    op.create_index(
        op.f("ix_cdn_failover_events_from_endpoint_id"),
        "cdn_failover_events",
        ["from_endpoint_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cdn_failover_events_to_endpoint_id"),
        "cdn_failover_events",
        ["to_endpoint_id"],
        unique=False,
    )

    op.create_table(
        "cdn_traffic_allocation_overrides",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=True),
        sa.Column("provider_type", provider_enum, nullable=True),
        sa.Column("region_code", sa.String(length=32), nullable=False, server_default="global"),
        sa.Column("allocation_percent", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["endpoint_id"], ["cdn_endpoints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cdn_traffic_overrides_active_region",
        "cdn_traffic_allocation_overrides",
        ["is_active", "region_code", "starts_at", "ends_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cdn_traffic_allocation_overrides_created_by_user_id"),
        "cdn_traffic_allocation_overrides",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cdn_traffic_allocation_overrides_endpoint_id"),
        "cdn_traffic_allocation_overrides",
        ["endpoint_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_cdn_traffic_allocation_overrides_endpoint_id"), table_name="cdn_traffic_allocation_overrides")
    op.drop_index(
        op.f("ix_cdn_traffic_allocation_overrides_created_by_user_id"),
        table_name="cdn_traffic_allocation_overrides",
    )
    op.drop_index("ix_cdn_traffic_overrides_active_region", table_name="cdn_traffic_allocation_overrides")
    op.drop_table("cdn_traffic_allocation_overrides")

    op.drop_index(op.f("ix_cdn_failover_events_to_endpoint_id"), table_name="cdn_failover_events")
    op.drop_index(op.f("ix_cdn_failover_events_from_endpoint_id"), table_name="cdn_failover_events")
    op.drop_index(op.f("ix_cdn_failover_events_created_at"), table_name="cdn_failover_events")
    op.drop_index(op.f("ix_cdn_failover_events_asset_id"), table_name="cdn_failover_events")
    op.drop_table("cdn_failover_events")

    op.drop_index("ix_cdn_provider_metrics_region_window", table_name="cdn_provider_metrics")
    op.drop_index("ix_cdn_provider_metrics_provider_window", table_name="cdn_provider_metrics")
    op.drop_index(op.f("ix_cdn_provider_metrics_window_start"), table_name="cdn_provider_metrics")
    op.drop_table("cdn_provider_metrics")

    op.drop_index("ix_cdn_endpoint_metrics_provider_region", table_name="cdn_endpoint_metrics")
    op.drop_index("ix_cdn_endpoint_metrics_endpoint_window", table_name="cdn_endpoint_metrics")
    op.drop_index(op.f("ix_cdn_endpoint_metrics_window_start"), table_name="cdn_endpoint_metrics")
    op.drop_index(op.f("ix_cdn_endpoint_metrics_endpoint_id"), table_name="cdn_endpoint_metrics")
    op.drop_table("cdn_endpoint_metrics")

    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS cdn_metric_granularity_enum")
