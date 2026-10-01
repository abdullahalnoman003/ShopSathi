"""handover_events and notifications

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

REASONS = "'complaint', 'refund', 'abusive_language', 'low_confidence', 'off_topic', 'not_in_shop_data', 'human_requested'"


def upgrade() -> None:
    op.create_table(
        "handover_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(f"reason IN ({REASONS})", name="ck_handover_events_reason"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_handover_events_shop_created", "handover_events", ["shop_id", "created_at"])
    op.create_index(op.f("ix_handover_events_chat_id"), "handover_events", ["chat_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("type IN ('chat_flagged')", name="ck_notifications_type"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_shop_read_created", "notifications", ["shop_id", "read_at", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_shop_read_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index(op.f("ix_handover_events_chat_id"), table_name="handover_events")
    op.drop_index("ix_handover_events_shop_created", table_name="handover_events")
    op.drop_table("handover_events")
