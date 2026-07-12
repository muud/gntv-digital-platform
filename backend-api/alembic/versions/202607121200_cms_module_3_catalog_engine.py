"""CMS Module 3 premium streaming catalog engine.

Revision ID: 202607121200
Revises: 202607111400
"""

from alembic import op
from app.modules.catalog import models  # noqa: F401
from app.models import audit, auth_extra, user  # noqa: F401
from app.modules.cms import models as cms_models  # noqa: F401
from app.core.database import Base

revision = "202607121200"
down_revision = "202607111400"
branch_labels = None
depends_on = None
CATALOG_TABLES = [
    t for t in Base.metadata.sorted_tables if t.name.startswith("catalog_")
]


def upgrade() -> None:
    bind = op.get_bind()
    for table in CATALOG_TABLES:
        table.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(CATALOG_TABLES):
        table.drop(bind, checkfirst=True)
