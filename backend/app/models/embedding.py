from datetime import datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.core.database import Base


class EmbeddingChunk(Base):
    """One searchable chunk of a shop's product or policy. Always queried together with shop_id."""

    __tablename__ = "embedding_chunks"
    __table_args__ = (
        CheckConstraint("source_type IN ('product', 'policy')", name="ck_embedding_chunks_source_type"),
        # shop_id is the leading column, so this also serves "all chunks of a shop" lookups
        Index("ix_embedding_chunks_shop_source", "shop_id", "source_type", "source_id"),
        # approximate nearest-neighbour search by cosine distance
        Index(
            "ix_embedding_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(20))
    #: product id for products; the shop id for the shop policy
    source_id: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(get_settings().embedding_dim))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AiUsageLog(Base):
    """One AI API call, for per-shop cost tracking (NFR-08). Reused by later AI prompts."""

    __tablename__ = "ai_usage_logs"
    __table_args__ = (Index("ix_ai_usage_logs_shop_created", "shop_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    operation: Mapped[str] = mapped_column(String(50))  # e.g. "embedding"
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)  # USD
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
