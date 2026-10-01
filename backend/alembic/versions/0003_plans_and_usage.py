"""plans, simulated payments, message usage, shops.plan_id

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-02
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    plans = op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("monthly_message_limit", sa.Integer(), nullable=False),
        sa.Column("monthly_price", sa.Integer(), nullable=False),
        sa.CheckConstraint("code IN ('free', 'basic', 'pro')", name="ck_plans_code"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    # Placeholder values (team to decide); `python -m app.cli seed` keeps them in sync with database/seed/plans.json.
    op.bulk_insert(
        plans,
        [
            {"code": "free", "name": "Free", "monthly_message_limit": 100, "monthly_price": 0},
            {"code": "basic", "name": "Basic", "monthly_message_limit": 1000, "monthly_price": 500},
            {"code": "pro", "name": "Pro", "monthly_message_limit": 5000, "monthly_price": 1500},
        ],
    )

    # Existing shops default to Free.
    op.add_column("shops", sa.Column("plan_id", sa.Integer(), nullable=True))
    op.execute("UPDATE shops SET plan_id = (SELECT id FROM plans WHERE code = 'free')")
    op.alter_column("shops", "plan_id", nullable=False)
    op.create_foreign_key("fk_shops_plan_id", "shops", "plans", ["plan_id"], ["id"])
    op.create_index(op.f("ix_shops_plan_id"), "shops", ["plan_id"])

    op.create_table(
        "simulated_payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('simulated_success')", name="ck_simulated_payments_status"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_simulated_payments_shop_id"), "simulated_payments", ["shop_id"])

    op.create_table(
        "shop_message_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("ai_messages_count", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shop_id", "period", name="uq_shop_message_usage_shop_period"),
    )
    op.create_index(op.f("ix_shop_message_usage_shop_id"), "shop_message_usage", ["shop_id"])


def downgrade() -> None:
    op.drop_table("shop_message_usage")
    op.drop_table("simulated_payments")
    op.drop_index(op.f("ix_shops_plan_id"), table_name="shops")
    op.drop_constraint("fk_shops_plan_id", "shops", type_="foreignkey")
    op.drop_column("shops", "plan_id")
    op.drop_table("plans")
