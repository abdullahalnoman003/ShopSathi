"""Deterministic offline TEST DOUBLES for automated tests.

These are NOT AI: they never understand text or call any model. Do not use
them to demo or ship product behaviour.
"""

import hashlib
from typing import Any

from shopsathi_ai.providers.base import EmbeddingProvider, EmbeddingResult, LLMProvider


class MockLLMProvider(LLMProvider):
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return {"mock": True, "echo": user_prompt}


class MockEmbeddingProvider(EmbeddingProvider):
    """Same text -> same vector. Different texts -> unrelated vectors (no semantics)."""

    name = "mock"
    model = "mock"

    def __init__(self, dim: int = 1536) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed_with_usage(self, texts: list[str], *, is_query: bool = False) -> EmbeddingResult:
        tokens = sum(len(t.split()) for t in texts)  # rough, deterministic
        return EmbeddingResult([self._vector(t) for t in texts], tokens, self.name, self.model)

    def _vector(self, text: str) -> list[float]:
        out: list[float] = []
        counter = 0
        while len(out) < self._dim:
            digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
            out.extend(b / 255.0 - 0.5 for b in digest)  # centred so unrelated texts are not all "close"
            counter += 1
        return out[: self._dim]
