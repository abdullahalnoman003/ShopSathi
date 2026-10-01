"""shop policies and delivery areas

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shop_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("delivery_time", sa.Text(), server_default="", nullable=False),
        sa.Column("return_rules", sa.Text(), server_default="", nullable=False),
        sa.Column("payment_options", sa.Text(), server_default="", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shop_id"),
    )
    op.create_table(
        "delivery_areas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("area_name", sa.String(length=100), nullable=False),
        sa.Column("charge", sa.Numeric(10, 2), nullable=False),
        sa.CheckConstraint("charge >= 0", name="ck_delivery_areas_charge_non_negative"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_delivery_areas_shop_id"), "delivery_areas", ["shop_id"])
    op.create_index(
        "uq_delivery_areas_shop_area", "delivery_areas", ["shop_id", sa.text("lower(area_name)")], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_delivery_areas_shop_area", table_name="delivery_areas")
    op.drop_index(op.f("ix_delivery_areas_shop_id"), table_name="delivery_areas")
    op.drop_table("delivery_areas")
    op.drop_table("shop_policies")
