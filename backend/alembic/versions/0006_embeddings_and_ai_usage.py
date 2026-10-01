"""embedding_chunks (pgvector) and ai_usage_logs

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-05

The vector column size comes from EMBEDDING_DIM at migration time. To change model/dimension later see
docs/CONVENTIONS.md ("python -m app.cli reembed-all --resize-column").
"""
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from app.core.config import get_settings

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "embedding_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(get_settings().embedding_dim), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source_type IN ('product', 'policy')", name="ck_embedding_chunks_source_type"),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_embedding_chunks_shop_source", "embedding_chunks", ["shop_id", "source_type", "source_id"])
    op.create_index(
        "ix_embedding_chunks_embedding_hnsw",
        "embedding_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_logs_shop_created", "ai_usage_logs", ["shop_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_logs_shop_created", table_name="ai_usage_logs")
    op.drop_table("ai_usage_logs")
    op.drop_index("ix_embedding_chunks_embedding_hnsw", table_name="embedding_chunks")
    op.drop_index("ix_embedding_chunks_shop_source", table_name="embedding_chunks")
    op.drop_table("embedding_chunks")
