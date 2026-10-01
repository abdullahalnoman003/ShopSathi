"""platform admin action log

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("detail", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_admin_actions_shop_id", "admin_actions", ["shop_id"])
    op.create_index("ix_admin_actions_created", "admin_actions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_admin_actions_created", table_name="admin_actions")
    op.drop_index("ix_admin_actions_shop_id", table_name="admin_actions")
    op.drop_table("admin_actions")
