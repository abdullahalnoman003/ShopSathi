"""Keeps each shop's product and policy embeddings in sync (workflow step 2, AI-R13).

Chunks are produced by the AI engine's pure chunking functions, embedded by the configured provider and
stored per shop in pgvector. Every query here is scoped by shop_id.
"""

import logging
from dataclasses import dataclass

from shopsathi_ai.chunking import Chunk, PolicyData, ProductData, SourceType, policy_chunks, product_chunks
from shopsathi_ai.providers import EmbeddingProvider
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.ai_adapters.factory import get_embedder
from app.core.config import get_settings
from app.models import EmbeddingChunk, Product
from app.services.ai_usage import log_ai_usage
from app.services.policy import PolicyService
from app.services.tenant import scoped_select

logger = logging.getLogger("shopsathi.embeddings")


class DimensionMismatch(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbedOutcome:
    chunks: int
    skipped_stale: bool = False


def column_dimension(db: Session) -> int | None:
    """Vector size of the embedding_chunks.embedding column."""
    return db.scalar(
        text(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'embedding_chunks'::regclass AND attname = 'embedding'"
        )
    )


class EmbeddingService:
    def __init__(self, db: Session, embedder: EmbeddingProvider | None = None) -> None:
        self.db = db
        self.embedder = embedder or get_embedder()

    # ---- building chunks from current database state ----

    def _product_chunks(self, shop_id: int, product_id: int) -> list[Chunk] | None:
        """Chunks for the product as it is NOW; None if the product no longer exists."""
        product = self.db.scalars(
            scoped_select(Product, shop_id).where(Product.id == product_id).execution_options(populate_existing=True)
        ).first()
        if product is None:
            return None
        return product_chunks(
            ProductData(
                id=product.id,
                name=product.name,
                description=product.description,
                price=product.price,
                sizes=list(product.sizes),
                colours=list(product.colours),
                stock_count=product.stock_count,
            )
        )

    def _policy_chunks(self, shop_id: int) -> list[Chunk]:
        self.db.expire_all()
        p = PolicyService(self.db, shop_id).get()
        return policy_chunks(
            PolicyData(
                shop_id=shop_id,
                delivery_time=p.delivery_time,
                return_rules=p.return_rules,
                payment_options=p.payment_options,
                delivery_areas=list(p.delivery_areas),
            )
        )

    # ---- embedding + storing ----

    def _embed(self, shop_id: int, chunks: list[Chunk]) -> list[list[float]]:
        if not chunks:
            return []
        result = self.embedder.embed_with_usage([c.content for c in chunks])
        # log the spend right away, even if the result later turns out to be stale
        log_ai_usage(self.db, shop_id, "embedding", result.provider, result.model, result.input_tokens)
        return result.vectors

    def _replace(
        self,
        shop_id: int,
        source_type: SourceType,
        source_id: int,
        embedded: list[Chunk],
        vectors: list[list[float]],
        recompute,
    ) -> EmbedOutcome:
        """Swap the old chunks of one source for the new ones in a single transaction.

        Under a per-source advisory lock, the source is read again: if it changed while we were embedding,
        a newer task is (or will be) queued for it, so this stale result is dropped instead of overwriting.
        """
        self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"embed:{shop_id}:{source_type}:{source_id}"},
        )
        current = recompute()
        if current is not None and [c.content for c in current] != [c.content for c in embedded]:
            self.db.rollback()
            logger.info("stale embedding dropped for %s %s (shop %s)", source_type, source_id, shop_id)
            return EmbedOutcome(chunks=0, skipped_stale=True)
        self.db.execute(
            delete(EmbeddingChunk).where(
                EmbeddingChunk.shop_id == shop_id,
                EmbeddingChunk.source_type == source_type,
                EmbeddingChunk.source_id == source_id,
            )
        )
        if current is not None:
            self.db.add_all(
                EmbeddingChunk(
                    shop_id=shop_id, source_type=c.source_type, source_id=c.source_id, content=c.content, embedding=v
                )
                for c, v in zip(embedded, vectors)
            )
        self.db.commit()
        return EmbedOutcome(chunks=len(embedded))

    def embed_product(self, shop_id: int, product_id: int) -> EmbedOutcome:
        """(Re)create the chunks of one product; removes them if the product no longer exists."""
        chunks = self._product_chunks(shop_id, product_id)
        if chunks is None:
            return self.delete_product(shop_id, product_id)
        vectors = self._embed(shop_id, chunks)
        return self._replace(
            shop_id, "product", product_id, chunks, vectors, lambda: self._product_chunks(shop_id, product_id)
        )

    def delete_product(self, shop_id: int, product_id: int) -> EmbedOutcome:
        self.db.execute(
            delete(EmbeddingChunk).where(
                EmbeddingChunk.shop_id == shop_id,
                EmbeddingChunk.source_type == "product",
                EmbeddingChunk.source_id == product_id,
            )
        )
        self.db.commit()
        return EmbedOutcome(chunks=0)

    def embed_policy(self, shop_id: int) -> EmbedOutcome:
        """(Re)create all policy chunks of the shop (none if the policy is empty)."""
        chunks = self._policy_chunks(shop_id)
        vectors = self._embed(shop_id, chunks)
        return self._replace(shop_id, "policy", shop_id, chunks, vectors, lambda: self._policy_chunks(shop_id))

    # ---- bulk (CLI) ----

    def check_dimension(self) -> None:
        dim = column_dimension(self.db)
        want = get_settings().embedding_dim
        if dim != want:
            raise DimensionMismatch(
                f"embedding_chunks.embedding is vector({dim}) but EMBEDDING_DIM is {want}. "
                "Run: python -m app.cli reembed-all --resize-column"
            )

    def reembed_shop(self, shop_id: int) -> dict[str, int]:
        """Rebuild every chunk of one shop, and drop chunks of products that no longer exist."""
        self.check_dimension()
        product_ids = list(self.db.scalars(scoped_select(Product, shop_id).with_only_columns(Product.id)))
        stale = self.db.execute(
            delete(EmbeddingChunk).where(
                EmbeddingChunk.shop_id == shop_id,
                EmbeddingChunk.source_type == "product",
                EmbeddingChunk.source_id.not_in(product_ids or [0]),
            )
        )
        self.db.commit()
        total = 0
        for pid in product_ids:
            total += self.embed_product(shop_id, pid).chunks
        policy_total = self.embed_policy(shop_id).chunks
        return {
            "products": len(product_ids),
            "product_chunks": total,
            "policy_chunks": policy_total,
            "orphans_removed": stale.rowcount or 0,
        }

    def chunk_count(self, shop_id: int) -> int:
        return self.db.scalar(select(func.count()).select_from(scoped_select(EmbeddingChunk, shop_id).subquery())) or 0
