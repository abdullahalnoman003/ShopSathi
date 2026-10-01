"""The backend's implementation of the AI engine's ``ShopDataGateway`` protocol.

Every query here is scoped by shop_id: one shop's data is never used for another shop.
"""

import re
from typing import Sequence

from shopsathi_ai.chunking import SourceType
from shopsathi_ai.interfaces import DeliveryChargeInfo, ProductInfo, RetrievedChunk, StockInfo
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.models import EmbeddingChunk, Product
from app.services.ai_usage import log_ai_usage
from app.services.policy import PolicyService
from app.services.tenant import scoped_select

_WORD = re.compile(r"[\wঀ-৿]+", re.UNICODE)


def _tokens(text_: str) -> list[str]:
    """Distinct lower-case words of 3+ characters."""
    seen: list[str] = []
    for w in _WORD.findall(text_.casefold()):
        if len(w) >= 3 and w not in seen:
            seen.append(w)
    return seen


def _like(token: str) -> str:
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _info(p: Product, match: str, score: float) -> ProductInfo:
    return ProductInfo(
        id=p.id,
        name=p.name,
        price=p.price,
        sizes=list(p.sizes),
        colours=list(p.colours),
        stock_count=p.stock_count,
        description=p.description,
        match=match,  # type: ignore[arg-type]
        score=score,
    )


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

    # ---- tools (Prompt 9) ----

    def search_products(
        self, shop_id: int, query_text: str, query_vector: list[float] | None, top_k: int
    ) -> list[ProductInfo]:
        """Products whose name contains the customer's words first, then products found by similarity."""
        found: list[ProductInfo] = []
        tokens = _tokens(query_text)
        if tokens:
            conditions = [Product.name.ilike(_like(t), escape="\\") for t in tokens]
            candidates = self.db.scalars(scoped_select(Product, shop_id).where(or_(*conditions)).limit(50)).all()
            scored = []
            for p in candidates:
                name = p.name.casefold()
                scored.append((sum(1 for t in tokens if t in name) / len(tokens), p))
            scored.sort(key=lambda x: (-x[0], x[1].id))
            found = [_info(p, "name", score) for score, p in scored]
        if query_vector is not None and not found:  # similarity is only a fallback when no name matches
            seen = {p.id for p in found}
            for hit in self.vector_search(shop_id, query_vector, top_k * 2, ["product"]):
                if hit.source_id in seen:
                    continue
                product = self.db.scalars(scoped_select(Product, shop_id).where(Product.id == hit.source_id)).first()
                if product is not None:
                    seen.add(product.id)
                    found.append(_info(product, "semantic", hit.score))
        return found[:top_k]

    def check_stock(
        self, shop_id: int, product_id: int, size: str | None = None, colour: str | None = None
    ) -> StockInfo | None:
        product = self.db.scalars(scoped_select(Product, shop_id).where(Product.id == product_id)).first()
        if product is None:
            return None
        sizes = [s.casefold() for s in product.sizes]
        colours = [c.casefold() for c in product.colours]
        return StockInfo(
            product_id=product.id,
            name=product.name,
            stock_count=product.stock_count,
            in_stock=product.stock_count > 0,
            sizes=list(product.sizes),
            colours=list(product.colours),
            size=size,
            size_offered=None if size is None else size.casefold() in sizes,
            colour=colour,
            colour_offered=None if colour is None else colour.casefold() in colours,
        )

    def get_delivery_charge(self, shop_id: int, area_text: str) -> DeliveryChargeInfo:
        found = PolicyService(self.db, shop_id).get_delivery_charge(area_text)
        return DeliveryChargeInfo(found=found.found, area_name=found.area_name, charge=found.charge)
