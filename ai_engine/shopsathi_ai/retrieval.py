"""The Retriever: embed a customer message and fetch the most relevant chunks of that shop."""

from typing import Sequence

from shopsathi_ai.chunking import SourceType
from shopsathi_ai.interfaces import RetrievedChunk, ShopDataGateway
from shopsathi_ai.providers.base import EmbeddingProvider


def retrieve(
    shop_id: int,
    query_text: str,
    top_k: int,
    *,
    embedder: EmbeddingProvider,
    gateway: ShopDataGateway,
    source_types: Sequence[SourceType] | None = None,
) -> list[RetrievedChunk]:
    """Return up to ``top_k`` chunks of ``shop_id`` ranked by similarity to ``query_text``.

    The query embedding call is logged through the gateway like every other AI call.
    """
    query_text = query_text.strip()
    if not query_text or top_k <= 0:
        return []
    result = embedder.embed_with_usage([query_text], is_query=True)
    gateway.log_ai_usage(shop_id, "embedding", result.provider, result.model, result.input_tokens)
    return gateway.vector_search(shop_id, result.vectors[0], top_k, source_types)
