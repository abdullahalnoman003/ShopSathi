from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Chat-completion provider returning structured JSON."""

    @abstractmethod
    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Return the model's reply parsed as a JSON object."""


class EmbeddingProvider(ABC):
    """Text embedding provider."""

    @property
    @abstractmethod
    def dim(self) -> int:
        """Length of the vectors returned by ``embed``."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text."""
