"""one Messenger chat per shop and customer

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-10
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Two webhook deliveries racing for the same new customer must not create two chats.
    op.create_index(
        "uq_chats_shop_messenger_psid",
        "chats",
        ["shop_id", "customer_psid"],
        unique=True,
        postgresql_where="channel = 'messenger' AND customer_psid IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_chats_shop_messenger_psid", table_name="chats")
