"""An in-memory ``ShopDataGateway`` built from the fixture catalogue and policy, so the evaluation runs without the
backend or a database. It follows the backend's rules (name match first, similarity only as a fallback, in-stock
browsing, exact normalised delivery areas) so the AI engine is tested the way it runs in production."""

import json
import math
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from shopsathi_ai.chunking import Chunk, PolicyData, ProductData, policy_chunks, product_chunks
from shopsathi_ai.interfaces import DeliveryChargeInfo, ProductInfo, RetrievedChunk, StockInfo
from shopsathi_ai.providers.base import EmbeddingProvider

_WORD = re.compile(r"[\wঀ-৿]+", re.UNICODE)
_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def tokens(text: str) -> list[str]:
    """Distinct lower-case words of 3+ characters (the backend's rule)."""
    seen: list[str] = []
    for w in _WORD.findall(text.casefold()):
        if len(w) >= 3 and w not in seen:
            seen.append(w)
    return seen


def normalise_area(text: str) -> str:
    return _NON_WORD.sub(" ", text.casefold()).strip()


@dataclass
class Fixture:
    shop_id: int
    shop_name: str
    products: list[ProductInfo]
    policy: PolicyData
    policy_raw: dict
    catalogue_raw: dict

    def product_by_name(self, name: str) -> ProductInfo | None:
        return next((p for p in self.products if p.name.casefold() == name.casefold()), None)


def load_fixture(catalogue: Path | None = None, policy: Path | None = None) -> Fixture:
    cat = json.loads((catalogue or FIXTURES / "shop_catalogue.json").read_text(encoding="utf-8"))
    pol = json.loads((policy or FIXTURES / "shop_policy.json").read_text(encoding="utf-8"))
    shop = cat["shop"]
    products = [
        ProductInfo(
            id=p["id"], name=p["name"], price=Decimal(str(p["price"])), sizes=list(p.get("sizes", [])), colours=list(p.get("colours", [])),
            stock_count=int(p["stock_count"]), description=p.get("description", ""), photos=[],
        )
        for p in cat["products"]
    ]
    policy = PolicyData(
        shop_id=shop["id"], delivery_time=pol.get("delivery_time", ""), return_rules=pol.get("return_rules", ""),
        payment_options=pol.get("payment_options", ""), delivery_areas=[(a["area_name"], Decimal(str(a["charge"]))) for a in pol.get("delivery_areas", [])],
    )
    return Fixture(shop["id"], shop["name"], products, policy, pol, cat)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class EvalGateway:
    fixture: Fixture
    embedder: EmbeddingProvider
    chunks: list[tuple[Chunk, list[float]]] = field(default_factory=list)
    usage: list[tuple[str, str, str, int, int]] = field(default_factory=list)  # (operation, provider, model, in, out)
    embedding_tokens: int = 0

    def __post_init__(self) -> None:
        texts: list[Chunk] = []
        for p in self.fixture.products:
            texts += product_chunks(ProductData(p.id, p.name, p.description, p.price, p.sizes, p.colours, p.stock_count))
        texts += policy_chunks(self.fixture.policy)
        result = self.embedder.embed_with_usage([c.content for c in texts])
        self.embedding_tokens += result.input_tokens
        self.chunks = list(zip(texts, result.vectors))

    # ------------------------------------------------------------ ShopDataGateway

    def vector_search(self, shop_id: int, query_vector: list[float], top_k: int, source_types: Sequence[str] | None = None) -> list[RetrievedChunk]:
        scored = [
            RetrievedChunk(source_type=c.source_type, source_id=c.source_id, content=c.content, score=_cosine(query_vector, v))
            for c, v in self.chunks
            if not source_types or c.source_type in source_types
        ]
        return sorted(scored, key=lambda r: -r.score)[:top_k]

    def log_ai_usage(self, shop_id: int, operation: str, provider: str, model: str, input_tokens: int, output_tokens: int = 0) -> None:
        self.usage.append((operation, provider, model, input_tokens, output_tokens))

    def _as(self, p: ProductInfo, match: str, score: float) -> ProductInfo:
        return ProductInfo(p.id, p.name, p.price, list(p.sizes), list(p.colours), p.stock_count, p.description, [], match, score)  # type: ignore[arg-type]

    def search_products(self, shop_id: int, query_text: str, query_vector: list[float] | None, top_k: int) -> list[ProductInfo]:
        found: list[ProductInfo] = []
        words = tokens(query_text)
        if words:
            scored = []
            for p in self.fixture.products:
                name = p.name.casefold()
                hits = [w for w in words if w in name]
                if hits:  # the backend's OR-of-ilike, scored by the share of query words in the name
                    scored.append((len(hits) / len(words), p))
            scored.sort(key=lambda x: (-x[0], x[1].id))
            found = [self._as(p, "name", s) for s, p in scored]
        if query_vector is not None and not found:  # similarity is only a fallback when no name matches
            for hit in self.vector_search(shop_id, query_vector, top_k * 2, ["product"]):
                product = next((p for p in self.fixture.products if p.id == hit.source_id), None)
                if product is not None and all(f.id != product.id for f in found):
                    found.append(self._as(product, "semantic", hit.score))
        return found[:top_k]

    def check_stock(self, shop_id: int, product_id: int, size: str | None = None, colour: str | None = None) -> StockInfo | None:
        p = next((p for p in self.fixture.products if p.id == product_id), None)
        if p is None:
            return None
        sizes, colours = [s.casefold() for s in p.sizes], [c.casefold() for c in p.colours]
        return StockInfo(
            p.id, p.name, p.stock_count, p.stock_count > 0, list(p.sizes), list(p.colours),
            size=size, size_offered=None if size is None else size.casefold() in sizes,
            colour=colour, colour_offered=None if colour is None else colour.casefold() in colours,
        )

    def get_delivery_charge(self, shop_id: int, area_text: str) -> DeliveryChargeInfo:
        key = normalise_area(area_text)
        for name, charge in self.fixture.policy.delivery_areas:
            if normalise_area(name) == key:
                return DeliveryChargeInfo(True, name, Decimal(str(charge)))
        return DeliveryChargeInfo(False)

    def get_products(self, shop_id: int, product_ids: Sequence[int]) -> list[ProductInfo]:
        by_id = {p.id: p for p in self.fixture.products}
        return [self._as(by_id[i], "name", 1.0) for i in product_ids if i in by_id]

    def browse_products(self, shop_id: int, max_price: Decimal | None, limit: int) -> list[ProductInfo]:
        ok = [p for p in self.fixture.products if p.stock_count > 0 and (max_price is None or p.price <= max_price)]
        return [self._as(p, "name", 0.0) for p in sorted(ok, key=lambda p: -p.id)[:limit]]
