"""products

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("sizes", postgresql.ARRAY(sa.String(length=50)), server_default="{}", nullable=False),
        sa.Column("colours", postgresql.ARRAY(sa.String(length=50)), server_default="{}", nullable=False),
        sa.Column("stock_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("photos", postgresql.ARRAY(sa.String(length=300)), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("price > 0", name="ck_products_price_positive"),
        sa.CheckConstraint("stock_count >= 0", name="ck_products_stock_non_negative"),
        sa.CheckConstraint("cardinality(photos) <= 5", name="ck_products_max_photos"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_shop_id"), "products", ["shop_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_products_shop_id"), table_name="products")
    op.drop_table("products")
