from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class LLMProvider(ABC):
    """Chat-completion provider returning structured JSON."""

    @abstractmethod
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Return the model's reply parsed as a JSON object."""


class EmbeddingProviderError(RuntimeError):
    """An embedding call failed (network, rate limit, bad response). Callers may retry."""


@dataclass(frozen=True)
class EmbeddingResult:
    """Vectors plus the usage info needed for per-shop cost logging (NFR-08)."""

    vectors: list[list[float]]
    input_tokens: int
    provider: str
    model: str


class EmbeddingProvider(ABC):
    """Text embedding provider."""

    #: short provider name used in usage logs, e.g. "openai"
    name: str = "unknown"
    #: model name used in usage logs and cost lookup
    model: str = "unknown"

    @property
    @abstractmethod
    def dim(self) -> int:
        """Length of the vectors returned by ``embed``."""

    @abstractmethod
    def embed_with_usage(self, texts: list[str], *, is_query: bool = False) -> EmbeddingResult:
        """Embed texts and report token usage. ``is_query`` marks search queries (some models need it)."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text."""
        return self.embed_with_usage(texts).vectors
