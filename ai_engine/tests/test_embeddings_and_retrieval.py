import math
from decimal import Decimal

import httpx
import pytest

from shopsathi_ai.chunking import Chunk, PolicyData, ProductData, format_money, policy_chunks, product_chunks, split_text
from shopsathi_ai.config import AISettings
from shopsathi_ai.interfaces import RetrievedChunk
from shopsathi_ai.providers import EmbeddingProviderError, get_embedding_provider
from shopsathi_ai.providers.local_embeddings import LocalEmbeddingProvider
from shopsathi_ai.providers.mock import MockEmbeddingProvider
from shopsathi_ai.providers.openai_embeddings import OpenAIEmbeddingProvider
from shopsathi_ai.retrieval import retrieve


# ---------- chunking ----------

def saree(**over):
    data = dict(id=7, name="Red Jamdani Saree", description="Hand-woven red saree.", price=Decimal("4800.00"),
                sizes=[], colours=["Red"], stock_count=6)
    data.update(over)
    return ProductData(**data)


def test_product_chunk_has_all_facts_and_metadata():
    [chunk] = product_chunks(saree())
    assert (chunk.source_type, chunk.source_id) == ("product", 7)
    for fact in ["Red Jamdani Saree", "Hand-woven red saree.", "4800 BDT", "Colours: Red", "In stock (6 available)"]:
        assert fact in chunk.content
    assert "Sizes: not applicable" in chunk.content


def test_product_out_of_stock_and_sizes():
    [chunk] = product_chunks(saree(stock_count=0, sizes=["M", "L"], price=1250.5))
    assert "Out of stock" in chunk.content and "available" not in chunk.content
    assert "Sizes: M, L" in chunk.content and "1250.5 BDT" in chunk.content


def test_long_description_is_split_into_small_chunks():
    sentence = "This saree is woven by hand in Tangail. "
    chunks = product_chunks(saree(description=sentence * 40))
    assert len(chunks) > 1
    assert all(c.source_id == 7 and c.source_type == "product" for c in chunks)
    assert all(len(c.content) < 800 for c in chunks)
    assert all("Red Jamdani Saree" in c.content for c in chunks)  # every piece names its product
    assert "Price:" in chunks[0].content and "Price:" not in chunks[1].content


def test_split_text_edge_cases():
    assert split_text("") == [] and split_text("   ") == []
    assert split_text("short") == ["short"]
    parts = split_text("a" * 1500, max_chars=600)
    assert [len(p) for p in parts] == [600, 600, 300]
    assert all(len(p) <= 600 for p in split_text("word " * 500))


def test_policy_chunks():
    chunks = policy_chunks(
        PolicyData(
            shop_id=3,
            delivery_time="1-2 days inside Dhaka",
            return_rules="",  # empty fields produce no chunk
            payment_options="COD, bKash",
            delivery_areas=[("Inside Dhaka", Decimal("60.00")), ("Khagan", 100)],
        )
    )
    assert all((c.source_type, c.source_id) == ("policy", 3) for c in chunks)
    text = [c.content for c in chunks]
    assert len(text) == 4
    assert any("Delivery time" in t and "1-2 days" in t for t in text)
    assert not any("Return rules" in t for t in text)
    assert "Shop policy - Delivery charge for Khagan: 100 BDT" in text
    assert "Shop policy - Delivery charge for Inside Dhaka: 60 BDT" in text
    assert policy_chunks(PolicyData(shop_id=3)) == []


def test_format_money():
    assert [format_money(v) for v in (Decimal("4800.00"), 1250.5, "99.90", 0, 100)] == ["4800", "1250.5", "99.9", "0", "100"]


# ---------- providers ----------

def test_mock_embedding_reports_usage_and_is_deterministic():
    p = MockEmbeddingProvider(16)
    a = p.embed_with_usage(["red saree", "blue"])
    b = p.embed_with_usage(["red saree", "blue"])
    assert a.vectors == b.vectors and len(a.vectors[0]) == 16
    assert a.input_tokens == 3 and (a.provider, a.model) == ("mock", "mock")
    assert p.embed(["red saree"]) == [a.vectors[0]]


def test_openai_provider_parses_response_and_usage():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        seen["body"], seen["auth"] = body, request.headers["authorization"]
        data = [{"index": i, "embedding": [float(i)] * 4} for i in reversed(range(len(body["input"])))]  # out of order
        return httpx.Response(200, json={"data": data, "usage": {"prompt_tokens": 11, "total_tokens": 11}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAIEmbeddingProvider("sk-test", "text-embedding-3-small", dim=4, client=client)
    res = p.embed_with_usage(["a", "b", "c"])
    assert res.vectors == [[0.0] * 4, [1.0] * 4, [2.0] * 4]  # re-ordered by index
    assert res.input_tokens == 11 and (res.provider, res.model) == ("openai", "text-embedding-3-small")
    assert seen["auth"] == "Bearer sk-test" and seen["body"]["dimensions"] == 4  # non-native dim is requested


def test_openai_provider_errors_are_clear():
    with pytest.raises(EmbeddingProviderError, match="OPENAI_API_KEY"):
        OpenAIEmbeddingProvider("")
    failing = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429, json={"error": "rate"})))
    with pytest.raises(EmbeddingProviderError, match="request failed"):
        OpenAIEmbeddingProvider("k", dim=4, client=failing).embed(["x"])
    wrong_dim = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}], "usage": {"prompt_tokens": 1}})
        )
    )
    with pytest.raises(EmbeddingProviderError, match="dimensional"):
        OpenAIEmbeddingProvider("k", dim=4, client=wrong_dim).embed(["x"])


def test_openai_native_dim_sends_no_dimensions_param():
    bodies = []

    def handler(request):
        import json

        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.0] * 1536}], "usage": {"prompt_tokens": 1}})

    p = OpenAIEmbeddingProvider("k", dim=1536, client=httpx.Client(transport=httpx.MockTransport(handler)))
    p.embed(["x"])
    assert "dimensions" not in bodies[0]


class FakeEncoder:
    def __init__(self):
        self.inputs = []

    def encode(self, texts, normalize_embeddings=True):
        self.inputs.append(texts)
        return [[0.5, 0.5, 0.5] for _ in texts]


def test_local_provider_uses_e5_prefixes_only_for_e5_models():
    enc = FakeEncoder()
    e5 = LocalEmbeddingProvider("intfloat/multilingual-e5-small", dim=3, encoder=enc)
    e5.embed_with_usage(["lal saree"], is_query=True)
    e5.embed_with_usage(["Red Saree"])
    assert enc.inputs == [["query: lal saree"], ["passage: Red Saree"]]

    enc2 = FakeEncoder()
    bge = LocalEmbeddingProvider("BAAI/bge-m3", dim=3, encoder=enc2)
    res = bge.embed_with_usage(["lal saree"], is_query=True)
    assert enc2.inputs == [["lal saree"]] and res.provider == "local"
    with pytest.raises(EmbeddingProviderError, match="dimensional"):
        LocalEmbeddingProvider("BAAI/bge-m3", dim=1024, encoder=FakeEncoder()).embed(["x"])


def test_factory_selects_providers():
    assert isinstance(get_embedding_provider(AISettings(embedding_provider="mock")), MockEmbeddingProvider)
    assert isinstance(
        get_embedding_provider(AISettings(embedding_provider="openai", openai_api_key="k")), OpenAIEmbeddingProvider
    )
    assert isinstance(get_embedding_provider(AISettings(embedding_provider="local", embedding_model="BAAI/bge-m3")), LocalEmbeddingProvider)
    with pytest.raises(EmbeddingProviderError):
        get_embedding_provider(AISettings(embedding_provider="openai", openai_api_key=""))


# ---------- retrieval with an in-memory fake gateway ----------

def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


class FakeGateway:
    """Holds embedded chunks per shop in memory (a stand-in for the backend's pgvector gateway)."""

    def __init__(self, embedder):
        self.embedder = embedder
        self.rows: list[tuple[int, Chunk, list[float]]] = []
        self.usage: list[tuple] = []
        self.searched_shops: list[int] = []

    def add(self, shop_id, chunk):
        self.rows.append((shop_id, chunk, self.embedder.embed([chunk.content])[0]))

    def vector_search(self, shop_id, query_vector, top_k, source_types=None):
        self.searched_shops.append(shop_id)
        hits = [
            RetrievedChunk(c.source_type, c.source_id, c.content, cosine(query_vector, v))
            for sid, c, v in self.rows
            if sid == shop_id and (source_types is None or c.source_type in source_types)
        ]
        return sorted(hits, key=lambda h: h.score, reverse=True)[:top_k]

    def log_ai_usage(self, shop_id, operation, provider, model, input_tokens, output_tokens=0):
        self.usage.append((shop_id, operation, provider, model, input_tokens, output_tokens))


@pytest.fixture
def embedder():
    return MockEmbeddingProvider(64)


def test_retrieve_ranks_exact_content_first_and_logs_usage(embedder):
    gw = FakeGateway(embedder)
    chunks = [*product_chunks(saree()), *product_chunks(saree(id=8, name="Cotton Panjabi")), *policy_chunks(PolicyData(1, delivery_time="2 days"))]
    for c in chunks:
        gw.add(1, c)
    query = product_chunks(saree(id=8, name="Cotton Panjabi"))[0].content  # identical text -> identical mock vector
    hits = retrieve(1, query, 2, embedder=embedder, gateway=gw)
    assert len(hits) == 2
    assert (hits[0].source_type, hits[0].source_id) == ("product", 8)
    assert hits[0].score >= hits[1].score and hits[0].score == pytest.approx(1.0)
    assert gw.usage == [(1, "embedding", "mock", "mock", len(query.split()), 0)]


def test_retrieve_never_returns_another_shops_chunks(embedder):
    gw = FakeGateway(embedder)
    shop_a_chunk = product_chunks(saree(id=1, name="Shop A Blue Mug"))[0]
    shop_b_chunk = product_chunks(saree(id=2, name="Shop B Red Saree"))[0]
    gw.add(1, shop_a_chunk)
    gw.add(2, shop_b_chunk)
    # the query is exactly shop B's chunk: B has a perfect match, but A asks
    hits = retrieve(1, shop_b_chunk.content, 5, embedder=embedder, gateway=gw)
    assert [h.content for h in hits] == [shop_a_chunk.content]
    assert gw.searched_shops == [1] and gw.usage[0][0] == 1
    assert [h.content for h in retrieve(2, shop_b_chunk.content, 5, embedder=embedder, gateway=gw)] == [shop_b_chunk.content]


def test_retrieve_source_type_filter_and_edge_cases(embedder):
    gw = FakeGateway(embedder)
    gw.add(1, product_chunks(saree())[0])
    gw.add(1, policy_chunks(PolicyData(1, delivery_time="2 days"))[0])
    only_policy = retrieve(1, "delivery", 5, embedder=embedder, gateway=gw, source_types=["policy"])
    assert [h.source_type for h in only_policy] == ["policy"]
    assert retrieve(1, "   ", 5, embedder=embedder, gateway=gw) == []
    assert retrieve(1, "x", 0, embedder=embedder, gateway=gw) == []
    assert retrieve(9, "x", 5, embedder=embedder, gateway=gw) == []  # unknown shop: nothing
