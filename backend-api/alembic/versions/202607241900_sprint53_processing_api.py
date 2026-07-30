"""Persist Sprint 5.3 processing task metadata.

Revision ID: 202607241900
Revises: 202607211200
"""

from alembic import op
import sqlalchemy as sa


revision = "202607241900"
down_revision = "202607211200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("transcoding_jobs")}
    if "input_source" in columns:
        return
    with op.batch_alter_table("transcoding_jobs") as batch:
        batch.add_column(sa.Column("input_source", sa.String(length=2048), nullable=True))
        batch.add_column(sa.Column("output_prefix", sa.String(length=512), nullable=True))
        batch.add_column(
            sa.Column("renditions", sa.JSON(), nullable=False, server_default=sa.text("'[]'"))
        )
        batch.drop_constraint("ck_transcoding_job_has_source", type_="check")
        batch.create_check_constraint(
            "ck_transcoding_job_has_source",
            "stream_id IS NOT NULL OR recording_id IS NOT NULL OR input_source IS NOT NULL",
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("transcoding_jobs")}
    if "input_source" not in columns:
        return
    with op.batch_alter_table("transcoding_jobs") as batch:
        batch.drop_constraint("ck_transcoding_job_has_source", type_="check")
        batch.create_check_constraint(
            "ck_transcoding_job_has_source",
            "stream_id IS NOT NULL OR recording_id IS NOT NULL",
        )
        batch.drop_column("renditions")
        batch.drop_column("output_prefix")
        batch.drop_column("input_source")
