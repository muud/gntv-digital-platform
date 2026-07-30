"""Module 5 streaming, distribution, and geo-fencing foundation.

Revision ID: 202607211200
Revises: 202607131200
"""

from alembic import op

from app.core.database import Base
from app.models import audit, auth_extra, user  # noqa: F401
from app.modules.catalog import models as catalog_models  # noqa: F401
from app.modules.cms import models as cms_models  # noqa: F401
from app.modules.distribution import models as distribution_models  # noqa: F401
from app.modules.streaming import models as streaming_models  # noqa: F401

revision = "202607211200"
down_revision = "202607131200"
branch_labels = None
depends_on = None

MODULE5_TABLE_NAMES = (
    "live_channels",
    "live_events",
    "stream_keys",
    "streams",
    "recordings",
    "playback_sessions",
    "transcoding_jobs",
    "manifests",
    "thumbnails",
    "distribution_targets",
    "geofencing_policies",
)

MODULE5_TABLES = [Base.metadata.tables[name] for name in MODULE5_TABLE_NAMES]

def upgrade() -> None:
    bind = op.get_bind()
    for table in MODULE5_TABLES:
        table.create(bind, checkfirst=True)
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_live_channels_current_event",
            "live_channels",
            "live_events",
            ["current_event_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint(
            "fk_live_channels_current_event",
            "live_channels",
            type_="foreignkey",
        )
    for table in reversed(MODULE5_TABLES):
        table.drop(bind, checkfirst=True)
