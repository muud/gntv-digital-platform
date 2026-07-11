"""create audit_logs table"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "202607051600"
down_revision = "202607051500"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_audit_user_event_created", "audit_logs", ["user_id", "event_type", "created_at"], unique=False)

def downgrade():
    op.drop_index("ix_audit_user_event_created", table_name="audit_logs")
    op.drop_table("audit_logs")
