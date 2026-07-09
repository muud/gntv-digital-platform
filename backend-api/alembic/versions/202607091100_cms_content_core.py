"""create cms content core tables"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "202607091100"
down_revision = "202607091000"
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
content_status_enum = postgresql.ENUM(
    "draft",
    "review",
    "fact_check",
    "approved",
    "scheduled",
    "published",
    "archived",
    name="gntv_content_status",
    create_type=False,
)
content_visibility_enum = postgresql.ENUM(
    "public",
    "private",
    "unlisted",
    "members",
    name="gntv_content_visibility",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'gntv_content_status') THEN
                CREATE TYPE gntv_content_status AS ENUM (
                    'draft', 'review', 'fact_check', 'approved',
                    'scheduled', 'published', 'archived'
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
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'gntv_content_visibility') THEN
                CREATE TYPE gntv_content_visibility AS ENUM (
                    'public', 'private', 'unlisted', 'members'
                );
            END IF;
        END
        $$;
        """
    )

    op.create_table(
        "cms_languages",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("native_name", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("idx_cms_languages_code", "cms_languages", ["code"], unique=False)

    op.create_table(
        "cms_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["cms_categories.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("idx_cms_categories_slug", "cms_categories", ["slug"], unique=False)

    op.create_table(
        "cms_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("idx_cms_tags_slug", "cms_tags", ["slug"], unique=False)

    op.create_table(
        "cms_genres",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("idx_cms_genres_slug", "cms_genres", ["slug"], unique=False)

    op.create_table(
        "cms_regions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("idx_cms_regions_code", "cms_regions", ["code"], unique=False)

    op.create_table(
        "cms_content",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("content_type", content_type_enum, nullable=False),
        sa.Column("language_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", content_status_enum, server_default="draft", nullable=False),
        sa.Column("visibility", content_visibility_enum, server_default="private", nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("editor_id", sa.Integer(), nullable=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("featured_image_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("seo", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["category_id"], ["cms_categories.id"]),
        sa.ForeignKeyConstraint(["editor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["featured_image_asset_id"], ["cms_media_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["language_id"], ["cms_languages.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_cms_content_slug"),
    )
    op.create_index("idx_cms_content_category", "cms_content", ["category_id"], unique=False)
    op.create_index("idx_cms_content_language_status", "cms_content", ["language_id", "status"], unique=False)
    op.create_index("idx_cms_content_status_visibility", "cms_content", ["status", "visibility"], unique=False)

    op.create_table(
        "cms_content_tags",
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["cms_content.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["cms_tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("content_id", "tag_id"),
    )
    op.create_table(
        "cms_content_genres",
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("genre_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["cms_content.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["genre_id"], ["cms_genres.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("content_id", "genre_id"),
    )
    op.create_table(
        "cms_content_regions",
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("region_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["cms_content.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["region_id"], ["cms_regions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("content_id", "region_id"),
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
    op.drop_table("cms_content_media_assets")
    op.drop_table("cms_content_regions")
    op.drop_table("cms_content_genres")
    op.drop_table("cms_content_tags")
    op.drop_index("idx_cms_content_status_visibility", table_name="cms_content")
    op.drop_index("idx_cms_content_language_status", table_name="cms_content")
    op.drop_index("idx_cms_content_category", table_name="cms_content")
    op.drop_table("cms_content")
    op.drop_index("idx_cms_regions_code", table_name="cms_regions")
    op.drop_table("cms_regions")
    op.drop_index("idx_cms_genres_slug", table_name="cms_genres")
    op.drop_table("cms_genres")
    op.drop_index("idx_cms_tags_slug", table_name="cms_tags")
    op.drop_table("cms_tags")
    op.drop_index("idx_cms_categories_slug", table_name="cms_categories")
    op.drop_table("cms_categories")
    op.drop_index("idx_cms_languages_code", table_name="cms_languages")
    op.drop_table("cms_languages")
    content_visibility_enum.drop(op.get_bind(), checkfirst=True)
    content_status_enum.drop(op.get_bind(), checkfirst=True)
