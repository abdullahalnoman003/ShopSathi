from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class LLMProviderError(RuntimeError):
    """An LLM call failed (network, rate limit, unusable response). Callers fall back safely."""


@dataclass(frozen=True)
class LLMResult:
    """A parsed JSON answer plus the token usage needed for per-shop cost logging (NFR-08)."""

    data: dict[str, Any]
    input_tokens: int
    output_tokens: int
    provider: str
    model: str


class LLMProvider(ABC):
    """Chat-completion provider returning structured JSON."""

    #: short provider name used in usage logs, e.g. "openai"
    name: str = "unknown"
    #: model name used in usage logs and cost lookup
    model: str = "unknown"

    @abstractmethod
    def generate_json_with_usage(self, system_prompt: str, user_prompt: str, *, task: str = "generic") -> LLMResult:
        """Return the model's reply parsed as a JSON object, with token usage.

        ``task`` names the step ("understand" or "reply"); real models ignore it, test doubles use it.
        """

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Return the model's reply parsed as a JSON object."""
        return self.generate_json_with_usage(system_prompt, user_prompt).data


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
