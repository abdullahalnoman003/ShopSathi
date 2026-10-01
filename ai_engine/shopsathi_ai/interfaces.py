"""The ``ShopDataGateway`` protocol: the only way the AI engine reads or writes shop data.

The backend implements it (app/ai_adapters/gateway.py); the AI engine never connects to the database.
Later prompts add more methods here (products, orders, ...).
"""

from dataclasses import dataclass
from typing import Protocol, Sequence

from shopsathi_ai.chunking import SourceType


@dataclass(frozen=True)
class RetrievedChunk:
    source_type: SourceType
    source_id: int
    content: str
    #: cosine similarity, higher is closer (1.0 = identical direction)
    score: float


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
