"""The ``ShopDataGateway`` protocol: the only way the AI engine reads or writes shop data.

The backend implements it (app/ai_adapters/gateway.py); the AI engine never connects to the database.
Later prompts add more methods here (orders, ...).
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Protocol, Sequence

from shopsathi_ai.chunking import SourceType


@dataclass(frozen=True)
class RetrievedChunk:
    source_type: SourceType
    source_id: int
    content: str
    #: cosine similarity, higher is closer (1.0 = identical direction)
    score: float


@dataclass(frozen=True)
class ProductInfo:
    """A catalogue product as the AI tools see it (the shop's source of truth)."""

    id: int
    name: str
    price: Decimal  # BDT
    sizes: list[str] = field(default_factory=list)
    colours: list[str] = field(default_factory=list)
    stock_count: int = 0
    description: str = ""
    #: full photo URLs in order (the first one is shown with a suggestion)
    photos: list[str] = field(default_factory=list)
    #: "name" = the product name matched the customer's words; "semantic" = found by embedding similarity
    match: Literal["name", "semantic"] = "name"
    #: fraction of query words found in the name (name matches) or cosine similarity (semantic matches)
    score: float = 1.0


@dataclass(frozen=True)
class StockInfo:
    product_id: int
    name: str
    stock_count: int  # for the product overall (the catalogue has no per-size stock)
    in_stock: bool
    sizes: list[str]
    colours: list[str]
    size: str | None = None
    #: None when no size was asked about; True/False whether the product is offered in that size
    size_offered: bool | None = None
    colour: str | None = None
    colour_offered: bool | None = None


@dataclass(frozen=True)
class DeliveryChargeInfo:
    found: bool
    area_name: str | None = None
    charge: Decimal | None = None


class ShopDataGateway(Protocol):
    def vector_search(
        self,
        shop_id: int,
        query_vector: list[float],
        top_k: int,
        source_types: Sequence[SourceType] | None = None,
    ) -> list[RetrievedChunk]:
        """Return the ``top_k`` chunks of THIS shop closest to the query, best first.

        Implementations must filter by ``shop_id``: one shop's data is never used for another shop.
        """
        ...

    def log_ai_usage(
        self,
        shop_id: int,
        operation: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int = 0,
    ) -> None:
        """Record one AI API call for per-shop cost tracking (NFR-08)."""
        ...

    # ---- tool data (Prompt 9) ----

    def search_products(
        self, shop_id: int, query_text: str, query_vector: list[float] | None, top_k: int
    ) -> list[ProductInfo]:
        """Products of THIS shop that match the customer's words (name match first, then semantic)."""
        ...

    def check_stock(
        self, shop_id: int, product_id: int, size: str | None = None, colour: str | None = None
    ) -> StockInfo | None:
        """Stock and size/colour availability of one product of THIS shop; None if it is not this shop's."""
        ...

    def get_delivery_charge(self, shop_id: int, area_text: str) -> DeliveryChargeInfo:
        """Exact (normalised) match of an area in this shop's policy. No guessing."""
        ...

    # ---- product suggestions (Prompt 10): live reads from the products table ----

    def get_products(self, shop_id: int, product_ids: Sequence[int]) -> list[ProductInfo]:
        """Current data (price, stock, photos) of these products of THIS shop; unknown ids are skipped."""
        ...

    def browse_products(self, shop_id: int, max_price: Decimal | None, limit: int) -> list[ProductInfo]:
        """In-stock products of THIS shop, optionally at or below ``max_price``."""
        ...
