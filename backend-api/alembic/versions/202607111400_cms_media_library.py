"""CMS Module 2 Media Library.

Revision ID: 202607111400
Revises: 202607111300
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "202607111400"
down_revision = "202607111300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    asset_type = postgresql.ENUM("image", "video", "audio", "poster", "thumbnail", "hero", "channel_logo", "subtitle", "caption", "transcript", "trailer", "preview", "attachment", name="gntv_media_asset_type", create_type=False)
    upload_status = postgresql.ENUM("pending", "uploading", "uploaded", "failed", name="gntv_media_upload_status", create_type=False)
    processing_status = postgresql.ENUM("pending", "processing", "ready", "failed", name="gntv_media_processing_status", create_type=False)
    url_strategy = postgresql.ENUM("public", "signed", name="gntv_media_url_strategy", create_type=False)
    asset_type.create(op.get_bind(), checkfirst=True)
    upload_status.create(op.get_bind(), checkfirst=True)
    processing_status.create(op.get_bind(), checkfirst=True)
    url_strategy.create(op.get_bind(), checkfirst=True)
    columns = [
        sa.Column("asset_type", asset_type, nullable=True), sa.Column("original_filename", sa.String(512), nullable=True),
        sa.Column("storage_filename", sa.String(512), nullable=True), sa.Column("mime_type", sa.String(255), nullable=True),
        sa.Column("width", sa.Integer()), sa.Column("height", sa.Integer()), sa.Column("duration_seconds", sa.Numeric(12, 3)),
        sa.Column("storage_provider", sa.String(20), nullable=True), sa.Column("storage_key", sa.String(1024), nullable=True),
        sa.Column("url_strategy", url_strategy, nullable=True), sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("upload_status", upload_status, nullable=True), sa.Column("processing_status", processing_status, nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=True), sa.Column("copyright_holder", sa.String(255)),
        sa.Column("copyright_notice", sa.Text()), sa.Column("license_starts_at", sa.Date()), sa.Column("license_ends_at", sa.Date()),
        sa.Column("created_by", sa.Integer(), nullable=True), sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True)), sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=True),
    ]
    for column in columns:
        op.add_column("cms_media_files", column)
    op.execute("""UPDATE cms_media_files SET asset_type = CASE WHEN file_type LIKE 'video%' THEN 'video'::gntv_media_asset_type WHEN file_type LIKE 'audio%' THEN 'audio'::gntv_media_asset_type ELSE 'attachment'::gntv_media_asset_type END, original_filename = id::text, storage_filename = id::text, mime_type = 'application/octet-stream', storage_provider = 'legacy', storage_key = id::text, url_strategy = 'public', checksum = repeat('0', 64), upload_status = 'uploaded', processing_status = 'ready', owner_id = (SELECT id FROM users ORDER BY id LIMIT 1), created_by = (SELECT id FROM users ORDER BY id LIMIT 1), updated_by = (SELECT id FROM users ORDER BY id LIMIT 1), updated_at = created_at""")
    for name in ("asset_type", "original_filename", "storage_filename", "mime_type", "storage_provider", "storage_key", "url_strategy", "checksum", "upload_status", "processing_status", "owner_id", "created_by", "updated_by", "updated_at", "metadata"):
        op.alter_column("cms_media_files", name, nullable=False)
    op.create_unique_constraint("uq_cms_media_storage_key", "cms_media_files", ["storage_key"])
    op.create_foreign_key("fk_cms_media_owner", "cms_media_files", "users", ["owner_id"], ["id"])
    op.create_foreign_key("fk_cms_media_created_by", "cms_media_files", "users", ["created_by"], ["id"])
    op.create_foreign_key("fk_cms_media_updated_by", "cms_media_files", "users", ["updated_by"], ["id"])
    op.create_index("idx_cms_media_search", "cms_media_files", ["asset_type", "mime_type", "created_at"])
    op.create_index("idx_cms_media_status", "cms_media_files", ["upload_status", "processing_status", "deleted_at"])
    op.create_index("idx_cms_media_owner", "cms_media_files", ["owner_id"])
    op.create_index("idx_cms_media_checksum", "cms_media_files", ["checksum"])


def downgrade() -> None:
    raise RuntimeError("CMS Module 2 migration is intentionally irreversible")
