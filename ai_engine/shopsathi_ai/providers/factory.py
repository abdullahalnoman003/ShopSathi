from shopsathi_ai.config import AISettings, get_ai_settings
from shopsathi_ai.providers.base import EmbeddingProvider, LLMProvider
from shopsathi_ai.providers.mock import MockEmbeddingProvider, MockLLMProvider


def get_llm_provider(settings: AISettings | None = None) -> LLMProvider:
    settings = settings or get_ai_settings()
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    # Real OpenAI / Gemini implementations arrive in Prompt 8/9.
    raise NotImplementedError(f"LLM provider '{settings.llm_provider}' is not implemented yet")


def get_embedding_provider(settings: AISettings | None = None) -> EmbeddingProvider:
    settings = settings or get_ai_settings()
    if settings.embedding_provider == "mock":
        return MockEmbeddingProvider(settings.embedding_dim)
    # Real OpenAI / local implementations arrive in Prompt 8/9.
    raise NotImplementedError(
        f"Embedding provider '{settings.embedding_provider}' is not implemented yet"
    )
