"""The backend's implementation of the AI engine's ``ShopDataGateway`` protocol."""

from typing import Sequence

from shopsathi_ai.chunking import SourceType
from shopsathi_ai.interfaces import RetrievedChunk
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import EmbeddingChunk
from app.services.ai_usage import log_ai_usage
from app.services.tenant import scoped_select


class BackendShopDataGateway:
    def __init__(self, db: Session) -> None:
        self.db = db

    def vector_search(
        self,
        shop_id: int,
        query_vector: list[float],
        top_k: int,
        source_types: Sequence[SourceType] | None = None,
    ) -> list[RetrievedChunk]:
        """Cosine search over THIS shop's chunks only (the shop_id filter is part of every query)."""
        distance = EmbeddingChunk.embedding.cosine_distance(query_vector)
        stmt = scoped_select(EmbeddingChunk, shop_id)
        if source_types:
            stmt = stmt.where(EmbeddingChunk.source_type.in_(list(source_types)))
        stmt = stmt.add_columns(distance.label("distance")).order_by(distance).limit(top_k)
        # With the HNSW index plus a shop filter, make the index keep scanning until top_k rows
        # of this shop are found (pgvector >= 0.8) instead of returning fewer.
        try:
            with self.db.begin_nested():
                self.db.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        except Exception:
            pass  # older pgvector: no iterative scan
        rows = self.db.execute(stmt).all()
        return [
            RetrievedChunk(
                source_type=chunk.source_type,  # type: ignore[arg-type]
                source_id=chunk.source_id,
                content=chunk.content,
                score=1.0 - float(dist),
            )
            for chunk, dist in rows
        ]

    def log_ai_usage(
        self,
        shop_id: int,
        operation: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int = 0,
    ) -> None:
        log_ai_usage(self.db, shop_id, operation, provider, model, input_tokens, output_tokens)
