from shopsathi_ai.config import AISettings
from shopsathi_ai.providers import get_embedding_provider, get_llm_provider
from shopsathi_ai.providers.mock import MockEmbeddingProvider, MockLLMProvider


def test_factory_returns_mock_providers():
    settings = AISettings(llm_provider="mock", embedding_provider="mock", embedding_dim=8)
    assert isinstance(get_llm_provider(settings), MockLLMProvider)
    emb = get_embedding_provider(settings)
    assert isinstance(emb, MockEmbeddingProvider)
    vectors = emb.embed(["a", "a", "b"])
    assert len(vectors[0]) == 8
    assert vectors[0] == vectors[1] != vectors[2]
