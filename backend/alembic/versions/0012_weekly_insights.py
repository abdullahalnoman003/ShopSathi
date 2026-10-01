"""weekly AI chat insights

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-20
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weekly_insights",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shop_id", sa.Integer(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("top_questions", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("missing_products", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("shop_id", "week_start", name="uq_weekly_insights_shop_week"),
    )
    op.create_index("ix_weekly_insights_shop_id", "weekly_insights", ["shop_id"])


def downgrade() -> None:
    op.drop_index("ix_weekly_insights_shop_id", table_name="weekly_insights")
    op.drop_table("weekly_insights")
