"""Unify CMS on cms_content and the approved ContentStatus workflow.

Revision ID: 202607111200
Revises: 202607101100
Create Date: 2026-07-11 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202607111200"
down_revision = "202607101100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The duplicate asset graph was never routed. Remove it and keep media files
    # as reusable resources attached to the canonical cms_content graph.
    op.execute("UPDATE cms_content SET featured_image_asset_id = NULL")
    op.drop_table("cms_content_media_assets")
    op.drop_constraint("cms_content_featured_image_asset_id_fkey", "cms_content", type_="foreignkey")
    op.drop_table("cms_workflow_logs")
    op.drop_table("cms_asset_translations")
    op.drop_table("cms_media_files")
    op.drop_table("cms_assets")
    op.execute("DROP TYPE IF EXISTS gntv_workflow_state")

    op.create_table(
        "cms_media_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=True),
        sa.Column("file_type", sa.String(length=50), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("resolution", sa.String(length=20), nullable=True),
        sa.Column("bitrate", sa.Integer(), nullable=True),
        sa.Column("codec", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key(
        "cms_content_featured_image_asset_id_fkey",
        "cms_content",
        "cms_media_files",
        ["featured_image_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "cms_content_media_assets",
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("media_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["cms_content.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_asset_id"], ["cms_media_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("content_id", "media_asset_id"),
    )


def downgrade() -> None:
    raise RuntimeError("CMS Module 1 unification is intentionally irreversible")
