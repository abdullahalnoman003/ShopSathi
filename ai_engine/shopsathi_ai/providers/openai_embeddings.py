"""OpenAI embeddings (text-embedding-3-small) over plain HTTPS with httpx."""

import httpx

from shopsathi_ai.providers.base import EmbeddingProvider, EmbeddingProviderError, EmbeddingResult

_URL = "https://api.openai.com/v1/embeddings"
_BATCH = 100
_NATIVE_DIM = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072, "text-embedding-ada-002": 1536}


class OpenAIEmbeddingProvider(EmbeddingProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dim: int = 1536,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise EmbeddingProviderError("OPENAI_API_KEY is not set")
        self._api_key = api_key
        self.model = model
        self._dim = dim
        self._client = client or httpx.Client(timeout=30)

    @property
    def dim(self) -> int:
        return self._dim

    def embed_with_usage(self, texts: list[str], *, is_query: bool = False) -> EmbeddingResult:
        vectors: list[list[float]] = []
        tokens = 0
        for start in range(0, len(texts), _BATCH):
            batch = texts[start : start + _BATCH]
            payload: dict = {"model": self.model, "input": batch}
            if self._dim != _NATIVE_DIM.get(self.model):
                payload["dimensions"] = self._dim  # text-embedding-3-* can shorten vectors
            try:
                res = self._client.post(_URL, json=payload, headers={"Authorization": f"Bearer {self._api_key}"})
                res.raise_for_status()
                data = res.json()
                rows = sorted(data["data"], key=lambda r: r["index"])
                vectors.extend(r["embedding"] for r in rows)
                tokens += int(data["usage"]["prompt_tokens"])
            except (httpx.HTTPError, KeyError, ValueError) as e:
                raise EmbeddingProviderError(f"OpenAI embedding request failed: {e.__class__.__name__}") from e
        if len(vectors) != len(texts) or any(len(v) != self._dim for v in vectors):
            raise EmbeddingProviderError(f"OpenAI returned vectors that are not {self._dim}-dimensional; check EMBEDDING_DIM")
        return EmbeddingResult(vectors, tokens, self.name, self.model)
