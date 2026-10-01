"""facebook_pages

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-09
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "facebook_pages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("page_id", sa.String(length=64), nullable=False),
        sa.Column("page_name", sa.String(length=200), nullable=False),
        sa.Column("encrypted_page_token", sa.Text(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shop_id"),
        sa.UniqueConstraint("page_id"),
    )


def downgrade() -> None:
    op.drop_table("facebook_pages")
