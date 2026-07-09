"""create cms foundation tables"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "202607091000"
down_revision = "202607051600"
branch_labels = None
depends_on = None

content_type_enum = postgresql.ENUM(
    "live_tv",
    "movie",
    "tv_show",
    "season",
    "episode",
    "podcast",
    "radio",
    "article",
    "breaking_news",
    "short",
    "kids",
    "education",
    "community_post",
    name="gntv_content_type",
    create_type=False,
)

workflow_state_enum = postgresql.ENUM(
    "draft",
    "review",
    "fact_check",
    "editorial_approval",
    "scheduled",
    "published",
    "archived",
    name="gntv_workflow_state",
    create_type=False,
)


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'gntv_content_type') THEN
                CREATE TYPE gntv_content_type AS ENUM (
                    'live_tv', 'movie', 'tv_show', 'season', 'episode',
                    'podcast', 'radio', 'article', 'breaking_news',
                    'short', 'kids', 'education', 'community_post'
                );
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'gntv_workflow_state') THEN
                CREATE TYPE gntv_workflow_state AS ENUM (
                    'draft', 'review', 'fact_check', 'editorial_approval',
                    'scheduled', 'published', 'archived'
                );
            END IF;
        END
        $$;
        """
    )

    op.create_table(
        "cms_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("content_type", content_type_enum, nullable=False),
        sa.Column("parent_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("duration", sa.Interval(), nullable=True),
        sa.Column("publish_state", workflow_state_enum, server_default="draft", nullable=False),
        sa.Column("scheduled_publish_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_premium", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("age_rating", sa.String(length=10), server_default="G", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["parent_asset_id"], ["cms_assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_cms_assets_type_state", "cms_assets", ["content_type", "publish_state"], unique=False)
    op.create_index("idx_cms_assets_parent", "cms_assets", ["parent_asset_id"], unique=False)

    op.create_table(
        "cms_asset_translations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("summary", sa.String(length=500), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String(length=50)), server_default="{}", nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("subtitles_url", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["cms_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "language_code", name="uq_asset_language"),
    )
    op.create_index("idx_cms_translations_lookup", "cms_asset_translations", ["asset_id", "language_code"], unique=False)
    op.create_index("idx_cms_translations_tags", "cms_asset_translations", ["tags"], unique=False, postgresql_using="gin")

    op.create_table(
        "cms_media_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=True),
        sa.Column("file_type", sa.String(length=50), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("resolution", sa.String(length=20), nullable=True),
        sa.Column("bitrate", sa.Integer(), nullable=True),
        sa.Column("codec", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["cms_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_cms_media_asset", "cms_media_files", ["asset_id"], unique=False)

    op.create_table(
        "cms_workflow_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("old_state", workflow_state_enum, nullable=True),
        sa.Column("new_state", workflow_state_enum, nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["cms_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_workflow_asset_logs", "cms_workflow_logs", ["asset_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_workflow_asset_logs", table_name="cms_workflow_logs")
    op.drop_table("cms_workflow_logs")
    op.drop_index("idx_cms_media_asset", table_name="cms_media_files")
    op.drop_table("cms_media_files")
    op.drop_index("idx_cms_translations_tags", table_name="cms_asset_translations")
    op.drop_index("idx_cms_translations_lookup", table_name="cms_asset_translations")
    op.drop_table("cms_asset_translations")
    op.drop_index("idx_cms_assets_parent", table_name="cms_assets")
    op.drop_index("idx_cms_assets_type_state", table_name="cms_assets")
    op.drop_table("cms_assets")
    workflow_state_enum.drop(op.get_bind(), checkfirst=True)
    content_type_enum.drop(op.get_bind(), checkfirst=True)
