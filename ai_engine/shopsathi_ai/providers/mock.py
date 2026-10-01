"""Deterministic offline TEST DOUBLES for automated tests.

These are NOT AI: they never understand text or call any model. Do not use
them to demo or ship product behaviour.
"""

import hashlib
from typing import Any

from shopsathi_ai.providers.base import EmbeddingProvider, LLMProvider


class MockLLMProvider(LLMProvider):
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return {"mock": True, "echo": user_prompt}


class MockEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dim: int = 1536) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        out: list[float] = []
        counter = 0
        while len(out) < self._dim:
            digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
            out.extend(b / 255.0 for b in digest)
            counter += 1
        return out[: self._dim]
