"""Module 7 Sprint 7.1 live chat control plane.

Revision ID: 202608121200
Revises: 202608091200
Create Date: 2026-08-12 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202608121200"
down_revision: Union[str, None] = "202608091200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


room_status = sa.Enum("active", "read_only", "closed", name="gntv_chat_room_status")
message_status = sa.Enum("published", "flagged", "deleted", "blocked", name="gntv_chat_message_status")
match_type = sa.Enum("exact", "regex", "fuzzy", name="gntv_chat_rule_match_type")
moderation_action = sa.Enum("block", "flag", "mute", "ban", "delete", name="gntv_chat_moderation_action")
audit_action = sa.Enum("block", "flag", "mute", "ban", "delete", name="gntv_chat_audit_action")


def upgrade() -> None:
    op.create_table(
        "chat_rooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("live_channel_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("status", room_status, nullable=False, server_default="active"),
        sa.Column("slow_mode_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("slow_mode_seconds >= 0", name="ck_chat_rooms_slow_mode"),
        sa.ForeignKeyConstraint(["live_channel_id"], ["live_channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("live_channel_id", name="uq_chat_rooms_live_channel"),
    )
    op.create_index("idx_chat_rooms_channel_status", "chat_rooms", ["live_channel_id", "status"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("client_msg_id", sa.String(length=36), nullable=False),
        sa.Column("status", message_status, nullable=False, server_default="published"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["deleted_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "client_msg_id", name="uq_chat_messages_room_client_msg"),
    )
    op.create_index("idx_chat_messages_room_time", "chat_messages", ["room_id", "created_at"])
    op.create_index("idx_chat_messages_room_status", "chat_messages", ["room_id", "status"])
    op.create_index("idx_chat_messages_user_time", "chat_messages", ["user_id", "created_at"])

    op.create_table(
        "chat_moderation_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("pattern", sa.String(length=255), nullable=False),
        sa.Column("match_type", match_type, nullable=False, server_default="regex"),
        sa.Column("action", moderation_action, nullable=False, server_default="block"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "pattern", "match_type", name="uq_chat_rules_room_pattern"),
    )
    op.create_index("idx_chat_rules_room_active", "chat_moderation_rules", ["room_id", "is_active"])

    op.create_table(
        "chat_user_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("is_muted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("muted_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_id", "user_id", name="uq_chat_user_states_room_user"),
    )
    op.create_index("idx_chat_user_states_room_user", "chat_user_states", ["room_id", "user_id"])

    op.create_table(
        "chat_moderation_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("moderator_id", sa.Integer(), nullable=False),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("target_message_id", sa.Uuid(), nullable=True),
        sa.Column("action", audit_action, nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["moderator_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_message_id"], ["chat_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_chat_moderation_audit_room_time", "chat_moderation_audit", ["room_id", "created_at"])
    op.create_index("idx_chat_moderation_audit_target_user", "chat_moderation_audit", ["target_user_id"])


def downgrade() -> None:
    op.drop_index("idx_chat_moderation_audit_target_user", table_name="chat_moderation_audit")
    op.drop_index("idx_chat_moderation_audit_room_time", table_name="chat_moderation_audit")
    op.drop_table("chat_moderation_audit")
    op.drop_index("idx_chat_user_states_room_user", table_name="chat_user_states")
    op.drop_table("chat_user_states")
    op.drop_index("idx_chat_rules_room_active", table_name="chat_moderation_rules")
    op.drop_table("chat_moderation_rules")
    op.drop_index("idx_chat_messages_user_time", table_name="chat_messages")
    op.drop_index("idx_chat_messages_room_status", table_name="chat_messages")
    op.drop_index("idx_chat_messages_room_time", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("idx_chat_rooms_channel_status", table_name="chat_rooms")
    op.drop_table("chat_rooms")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS gntv_chat_audit_action")
        op.execute("DROP TYPE IF EXISTS gntv_chat_moderation_action")
        op.execute("DROP TYPE IF EXISTS gntv_chat_rule_match_type")
        op.execute("DROP TYPE IF EXISTS gntv_chat_message_status")
        op.execute("DROP TYPE IF EXISTS gntv_chat_room_status")
