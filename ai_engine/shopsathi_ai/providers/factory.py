from shopsathi_ai.config import AISettings, get_ai_settings
from shopsathi_ai.providers.base import EmbeddingProvider, LLMProvider
from shopsathi_ai.providers.mock import MockEmbeddingProvider, MockLLMProvider


def get_llm_provider(settings: AISettings | None = None) -> LLMProvider:
    settings = settings or get_ai_settings()
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    # Real OpenAI / Gemini LLM implementations arrive in Prompt 9.
    raise NotImplementedError(f"LLM provider '{settings.llm_provider}' is not implemented yet")


def get_embedding_provider(settings: AISettings | None = None) -> EmbeddingProvider:
    settings = settings or get_ai_settings()
    if settings.embedding_provider == "mock":
        return MockEmbeddingProvider(settings.embedding_dim)
    if settings.embedding_provider == "openai":
        from shopsathi_ai.providers.openai_embeddings import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(settings.openai_api_key, settings.embedding_model, settings.embedding_dim)
    if settings.embedding_provider == "local":
        from shopsathi_ai.providers.local_embeddings import LocalEmbeddingProvider

        return LocalEmbeddingProvider(settings.embedding_model, settings.embedding_dim)
    raise ValueError(f"Unknown embedding provider '{settings.embedding_provider}'")
