"""Local multilingual sentence-embedding model (e.g. BAAI/bge-m3 or intfloat/multilingual-e5-*).

Needs the optional extra: pip install "shopsathi-ai[local]"  (sentence-transformers + torch).
The model is downloaded on first use and runs on this machine: no API key, no per-call cost.
"""

from typing import Any

from shopsathi_ai.providers.base import EmbeddingProvider, EmbeddingProviderError, EmbeddingResult


class LocalEmbeddingProvider(EmbeddingProvider):
    name = "local"

    def __init__(self, model: str = "BAAI/bge-m3", dim: int = 1024, encoder: Any = None) -> None:
        self.model = model
        self._dim = dim
        self._encoder = encoder  # injectable for tests

    @property
    def dim(self) -> int:
        return self._dim

    def _load(self) -> Any:
        if self._encoder is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise EmbeddingProviderError(
                    'The local embedding model needs: pip install "shopsathi-ai[local]"'
                ) from e
            self._encoder = SentenceTransformer(self.model)
        return self._encoder

    def _prefix(self, is_query: bool) -> str:
        # multilingual-e5 models were trained with these prefixes; bge-m3 needs none.
        if "e5" in self.model.lower():
            return "query: " if is_query else "passage: "
        return ""

    def embed_with_usage(self, texts: list[str], *, is_query: bool = False) -> EmbeddingResult:
        encoder = self._load()
        prefix = self._prefix(is_query)
        try:
            raw = encoder.encode([prefix + t for t in texts], normalize_embeddings=True)
        except Exception as e:
            raise EmbeddingProviderError(f"Local embedding failed: {e.__class__.__name__}") from e
        vectors = [[float(x) for x in v] for v in raw]
        if any(len(v) != self._dim for v in vectors):
            raise EmbeddingProviderError(f"{self.model} does not produce {self._dim}-dimensional vectors; check EMBEDDING_DIM")
        tokens = sum(len(t.split()) for t in texts)  # approximate: local models have no billing
        return EmbeddingResult(vectors, tokens, self.name, self.model)
