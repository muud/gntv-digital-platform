"""Module 6 Sprint 6.4 Multi-DRM, Geo-control & Watermarking.

Revision ID: 202608061800
Revises: 202608041200
Create Date: 2026-08-06 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision = "202608061800"
down_revision = "202608041200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "drm_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False, server_default="alibaba_kms"),
        sa.Column("max_resolution", sa.String(length=20), nullable=False, server_default="1080p"),
        sa.Column("hdcp_enforcement", sa.String(length=20), nullable=False, server_default="hdcp_v2_2"),
        sa.Column("allow_persistent_license", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("license_duration_seconds", sa.Integer(), nullable=False, server_default="86400"),
        sa.Column("rental_duration_seconds", sa.Integer(), nullable=False, server_default="172800"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "geo_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("country_allow_list", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("country_deny_list", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("block_vpn", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("block_proxy", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fail_closed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "drm_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key_id", sa.Uuid(), nullable=False),
        sa.Column("policy_id", sa.Uuid(), nullable=True),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("live_channel_id", sa.Uuid(), nullable=True),
        sa.Column("encrypted_key_envelope", sa.Text(), nullable=False),
        sa.Column("algorithm", sa.String(length=50), nullable=False, server_default="AES-128-CTR"),
        sa.Column("key_rotation_interval_seconds", sa.Integer(), nullable=True, server_default="86400"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["policy_id"], ["drm_policies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["live_channel_id"], ["live_channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_id"),
    )
    op.create_index("idx_drm_keys_asset", "drm_keys", ["asset_id"])
    op.create_index("idx_drm_keys_channel", "drm_keys", ["live_channel_id"])

    with op.batch_alter_table("live_channels") as batch:
        batch.add_column(sa.Column("drm_policy_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("geo_policy_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_live_channels_drm_policy", "drm_policies", ["drm_policy_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_live_channels_geo_policy", "geo_policies", ["geo_policy_id"], ["id"], ondelete="SET NULL")

    with op.batch_alter_table("recordings") as batch:
        batch.add_column(sa.Column("drm_policy_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("geo_policy_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_recordings_drm_policy", "drm_policies", ["drm_policy_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_recordings_geo_policy", "geo_policies", ["geo_policy_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("recordings") as batch:
        batch.drop_constraint("fk_recordings_geo_policy", type_="foreignkey")
        batch.drop_constraint("fk_recordings_drm_policy", type_="foreignkey")
        batch.drop_column("geo_policy_id")
        batch.drop_column("drm_policy_id")

    with op.batch_alter_table("live_channels") as batch:
        batch.drop_constraint("fk_live_channels_geo_policy", type_="foreignkey")
        batch.drop_constraint("fk_live_channels_drm_policy", type_="foreignkey")
        batch.drop_column("geo_policy_id")
        batch.drop_column("drm_policy_id")

    op.drop_index("idx_drm_keys_channel", table_name="drm_keys")
    op.drop_index("idx_drm_keys_asset", table_name="drm_keys")
    op.drop_table("drm_keys")
    op.drop_table("geo_policies")
    op.drop_table("drm_policies")
