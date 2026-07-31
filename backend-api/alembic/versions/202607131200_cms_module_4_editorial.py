"""CMS Module 4 editorial workflow and publishing.

Revision ID: 202607131200
Revises: 202607121200
"""

from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.database import Base
from app.models import audit, auth_extra, user  # noqa: F401
from app.modules.cms import models as cms_models  # noqa: F401
from app.modules.editorial import models  # noqa: F401

revision = "202607131200"
down_revision = "202607121200"
branch_labels = None
depends_on = None
EDITORIAL_TABLES = [table for table in Base.metadata.sorted_tables if table.name.startswith("editorial_")]


def upgrade() -> None:
    bind = op.get_bind()
    for table in EDITORIAL_TABLES:
        table.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(EDITORIAL_TABLES):
        table.drop(bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        for enum_name in [
            "gntv_notification_channel",
            "gntv_editorial_comment_kind",
            "gntv_assignment_role",
            "gntv_editorial_priority",
            "gntv_editorial_state",
        ]:
            postgresql.ENUM(name=enum_name).drop(bind, checkfirst=True)
