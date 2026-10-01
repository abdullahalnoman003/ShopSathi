from shopsathi_ai.config import AISettings
from shopsathi_ai.providers import EmbeddingProvider, get_embedding_provider

from app.core.config import get_settings


def build_ai_settings() -> AISettings:
    """AI engine settings taken from the backend's settings (.env), not from os.environ alone."""
    s = get_settings()
    return AISettings(
        llm_provider=s.llm_provider,  # type: ignore[arg-type]
        llm_model=s.llm_model,
        embedding_provider=s.embedding_provider,  # type: ignore[arg-type]
        embedding_model=s.embedding_model,
        embedding_dim=s.embedding_dim,
        openai_api_key=s.openai_api_key,
        gemini_api_key=s.gemini_api_key,
    )


_provider: EmbeddingProvider | None = None


def get_embedder() -> EmbeddingProvider:
    """One shared provider per process (a local model is expensive to load)."""
    global _provider
    if _provider is None:
        _provider = get_embedding_provider(build_ai_settings())
    return _provider


def reset_embedder() -> None:
    global _provider
    _provider = None
