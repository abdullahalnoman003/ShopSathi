"""orders and chats.pending_order

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-07
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chats", sa.Column("pending_order", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("size", sa.String(length=50), nullable=True),
        sa.Column("colour", sa.String(length=50), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("customer_name", sa.String(length=200), nullable=False),
        sa.Column("customer_phone", sa.String(length=20), nullable=False),
        sa.Column("customer_address", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("is_test", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'confirmed', 'cancelled')", name="ck_orders_status"),
        sa.CheckConstraint("quantity > 0", name="ck_orders_quantity_positive"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_shop_status_created", "orders", ["shop_id", "status", "created_at"])
    op.create_index(op.f("ix_orders_chat_id"), "orders", ["chat_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_orders_chat_id"), table_name="orders")
    op.drop_index("ix_orders_shop_status_created", table_name="orders")
    op.drop_table("orders")
    op.drop_column("chats", "pending_order")
