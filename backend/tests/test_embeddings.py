from decimal import Decimal

import pytest
from shopsathi_ai.chunking import PolicyData, ProductData, product_chunks
from shopsathi_ai.providers.mock import MockEmbeddingProvider
from shopsathi_ai.retrieval import retrieve
from sqlalchemy import select, text, update

from app.ai_adapters.gateway import BackendShopDataGateway
from app.cli import main as cli_main
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import AiUsageLog, EmbeddingChunk, Product, Shop
from app.services.ai_usage import estimate_cost
from app.services.embeddings import EmbedOutcome, EmbeddingService
from app.workers import tasks
from app.workers.dispatch import enqueue
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"


def signup(client, email="a@example.com", shop="Shop A"):
    r = client.post(
        f"{API}/auth/signup",
        json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD},
    )
    return r.json()["access_token"]


def shop_id_of(db, name):
    return db.scalar(select(Shop.id).where(Shop.name == name))


def body(**over):
    data = {"name": "Red Jamdani Saree", "description": "Hand-woven", "price": 4800, "sizes": [], "colours": ["Red"], "stock_count": 6}
    data.update(over)
    return data


def create_product(client, token, **over):
    r = client.post(f"{API}/products", json=body(**over), headers=auth_header(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def contents(db, shop_id, source_type=None):
    q = select(EmbeddingChunk.content).where(EmbeddingChunk.shop_id == shop_id).order_by(EmbeddingChunk.id)
    if source_type:
        q = q.where(EmbeddingChunk.source_type == source_type)
    return list(db.scalars(q))


@pytest.fixture
def token(client):
    return signup(client)


# ---------- keeping chunks in sync ----------

def test_creating_a_product_embeds_it_and_logs_usage(client, token, db):
    pid = create_product(client, token)
    shop = shop_id_of(db, "Shop A")
    [content] = contents(db, shop, "product")
    assert "Red Jamdani Saree" in content and "4800 BDT" in content and "In stock (6 available)" in content
    row = db.execute(select(EmbeddingChunk.source_type, EmbeddingChunk.source_id).where(EmbeddingChunk.shop_id == shop)).one()
    assert (row.source_type, row.source_id) == ("product", pid)

    log = db.scalars(select(AiUsageLog)).all()
    assert len(log) == 1
    assert (log[0].shop_id, log[0].operation, log[0].provider, log[0].model) == (shop, "embedding", "mock", "mock")
    assert log[0].input_tokens > 0 and log[0].output_tokens == 0 and log[0].estimated_cost == 0


def test_editing_a_product_replaces_its_chunks(client, token, db):
    pid = create_product(client, token)
    shop = shop_id_of(db, "Shop A")
    r = client.put(f"{API}/products/{pid}", json=body(name="Blue Saree", price=5200, stock_count=0), headers=auth_header(token))
    assert r.status_code == 200
    [content] = contents(db, shop, "product")  # replaced, not duplicated
    assert "Blue Saree" in content and "5200 BDT" in content and "Out of stock" in content
    assert "Red Jamdani" not in content
    assert len(db.scalars(select(AiUsageLog)).all()) == 2  # one embedding call per change


def test_long_description_makes_several_chunks_and_shrinking_it_removes_them(client, token, db):
    pid = create_product(client, token, description="Woven by hand in Tangail. " * 60)
    shop = shop_id_of(db, "Shop A")
    assert len(contents(db, shop, "product")) > 1
    client.put(f"{API}/products/{pid}", json=body(description="Short."), headers=auth_header(token))
    assert len(contents(db, shop, "product")) == 1


def test_deleting_a_product_removes_its_chunks_only(client, token, db):
    keep = create_product(client, token, name="Keeper")
    gone = create_product(client, token, name="Goner")
    shop = shop_id_of(db, "Shop A")
    assert len(contents(db, shop)) == 2
    assert client.delete(f"{API}/products/{gone}", headers=auth_header(token)).status_code == 204
    [left] = contents(db, shop)
    assert "Keeper" in left
    assert db.scalar(select(EmbeddingChunk.source_id).where(EmbeddingChunk.shop_id == shop)) == keep


def test_photo_change_triggers_reembedding(client, token, db, monkeypatch):
    calls = []
    monkeypatch.setattr(tasks.EmbeddingService, "embed_product", lambda self, s, p: calls.append(p) or EmbedOutcome(0))
    pid = create_product(client, token)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    client.post(f"{API}/products/{pid}/photos", files=[("files", ("a.png", png, "image/png"))], headers=auth_header(token))
    assert calls == [pid, pid]  # create + photo upload


def test_policy_save_embeds_policy_chunks_and_resave_replaces_them(client, token, db):
    shop = shop_id_of(db, "Shop A")
    policy = {
        "delivery_time": "1-2 days inside Dhaka",
        "return_rules": "Return within 3 days",
        "payment_options": "COD, bKash",
        "delivery_areas": [{"area_name": "Inside Dhaka", "charge": 60}, {"area_name": "Khagan", "charge": 100}],
    }
    assert client.put(f"{API}/shop/policy", json=policy, headers=auth_header(token)).status_code == 200
    got = contents(db, shop, "policy")
    assert len(got) == 5
    assert any("Delivery charge for Khagan: 100 BDT" in c for c in got)
    assert any("Return rules" in c and "3 days" in c for c in got)

    policy["delivery_areas"] = [{"area_name": "Khagan", "charge": 110}]
    policy["return_rules"] = ""
    client.put(f"{API}/shop/policy", json=policy, headers=auth_header(token))
    got = contents(db, shop, "policy")
    assert len(got) == 3  # delivery time, payment options, Khagan
    assert any("Khagan: 110 BDT" in c for c in got) and not any("Inside Dhaka: 60" in c for c in got)
    assert not any("Return rules" in c for c in got)

    client.put(f"{API}/shop/policy", json={"delivery_areas": []}, headers=auth_header(token))
    assert contents(db, shop, "policy") == []  # emptied policy leaves no chunks


def test_policy_and_product_chunks_do_not_replace_each_other(client, token, db):
    shop = shop_id_of(db, "Shop A") or None
    create_product(client, token)
    shop = shop_id_of(db, "Shop A")
    client.put(f"{API}/shop/policy", json={"delivery_time": "2 days"}, headers=auth_header(token))
    assert len(contents(db, shop, "product")) == 1 and len(contents(db, shop, "policy")) == 1
    client.put(f"{API}/shop/policy", json={"delivery_time": "3 days"}, headers=auth_header(token))
    assert len(contents(db, shop, "product")) == 1 and len(contents(db, shop, "policy")) == 1


def test_csv_import_embeds_each_imported_product(client, token, db):
    csv = "name,price,stock\nImported One,100,3\nImported Two,200,0\n,5,1\n"
    r = client.post(f"{API}/products/import", files={"file": ("p.csv", csv.encode(), "text/csv")}, headers=auth_header(token))
    assert r.json()["imported"] == 2
    got = contents(db, shop_id_of(db, "Shop A"), "product")
    assert len(got) == 2 and any("Imported Two" in c and "Out of stock" in c for c in got)


def test_embedding_a_missing_product_is_a_noop(db):
    assert tasks.embed_product(999999) == 0


def test_stale_result_is_dropped_when_product_changes_during_embedding(client, token, db):
    pid = create_product(client, token, name="Version One")
    shop = shop_id_of(db, "Shop A")

    class RacingEmbedder(MockEmbeddingProvider):
        """Simulates the seller editing the product while the embedding call is in flight."""

        def embed_with_usage(self, texts, *, is_query=False):
            with SessionLocal() as other:
                other.execute(update(Product).where(Product.id == pid).values(name="Version Two"))
                other.commit()
            return super().embed_with_usage(texts, is_query=is_query)

    outcome = EmbeddingService(db, RacingEmbedder(1536)).embed_product(shop, pid)
    assert outcome.skipped_stale is True
    assert "Version One" in contents(db, shop)[0]  # the stale vector did not overwrite anything
    assert EmbeddingService(db, MockEmbeddingProvider(1536)).embed_product(shop, pid).skipped_stale is False
    assert "Version Two" in contents(db, shop)[0]


def test_queue_failure_does_not_fail_the_request(monkeypatch, caplog):
    class BrokenTask:
        name = "broken"

        def delay(self, *a):
            raise ConnectionError("redis down")

    with pytest.raises(ConnectionError):  # eager/test mode raises so tests notice
        enqueue(BrokenTask(), 1)
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "false")
    get_settings.cache_clear()
    try:
        enqueue(BrokenTask(), 1)  # production mode: logged, not raised
        assert "could not queue" in caplog.text
    finally:
        monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")
        get_settings.cache_clear()


# ---------- retrieval is isolated per shop ----------

def test_retrieval_never_returns_another_shops_chunks(client, db):
    a = signup(client, "a@example.com", "Shop A")
    b = signup(client, "b@example.com", "Shop B")
    create_product(client, a, name="Blue Mug", price=300)
    create_product(client, b, name="Red Saree", price=900)
    shop_a, shop_b = shop_id_of(db, "Shop A"), shop_id_of(db, "Shop B")

    embedder = MockEmbeddingProvider(1536)
    gateway = BackendShopDataGateway(db)
    b_text = product_chunks(ProductData(0, "Red Saree", "Hand-woven", Decimal("900"), [], ["Red"], 6))[0].content
    assert b_text in contents(db, shop_b)  # the query below matches B's chunk exactly

    hits_a = retrieve(shop_a, b_text, 5, embedder=embedder, gateway=gateway)
    assert hits_a and all("Blue Mug" in h.content for h in hits_a)
    assert not any("Red Saree" in h.content for h in hits_a)

    hits_b = retrieve(shop_b, b_text, 5, embedder=embedder, gateway=gateway)
    assert [h.content for h in hits_b] == [b_text]
    assert hits_b[0].score == pytest.approx(1.0, abs=1e-4) and hits_b[0].source_type == "product"


def test_retrieval_ranking_top_k_filters_and_empty_shop(client, token, db):
    for name in ["Red Saree", "Blue Mug", "Green Lamp"]:
        create_product(client, token, name=name)
    client.put(f"{API}/shop/policy", json={"delivery_time": "2 days"}, headers=auth_header(token))
    shop = shop_id_of(db, "Shop A")
    embedder, gateway = MockEmbeddingProvider(1536), BackendShopDataGateway(db)

    target = [c for c in contents(db, shop, "product") if "Blue Mug" in c][0]
    hits = retrieve(shop, target, 2, embedder=embedder, gateway=gateway)
    assert len(hits) == 2 and "Blue Mug" in hits[0].content and hits[0].score >= hits[1].score

    only_policy = retrieve(shop, "delivery", 10, embedder=embedder, gateway=gateway, source_types=["policy"])
    assert [h.source_type for h in only_policy] == ["policy"]

    empty_shop = Shop(name="Empty", plan_id=db.scalar(select(Shop.plan_id)))
    db.add(empty_shop)
    db.commit()
    assert retrieve(empty_shop.id, "anything", 5, embedder=embedder, gateway=gateway) == []


def test_retrieval_query_embedding_is_logged_for_that_shop(client, token, db):
    create_product(client, token)
    shop = shop_id_of(db, "Shop A")
    before = len(db.scalars(select(AiUsageLog)).all())
    retrieve(shop, "lal saree", 3, embedder=MockEmbeddingProvider(1536), gateway=BackendShopDataGateway(db))
    logs = db.scalars(select(AiUsageLog).order_by(AiUsageLog.id)).all()
    assert len(logs) == before + 1
    assert (logs[-1].shop_id, logs[-1].operation, logs[-1].input_tokens) == (shop, "embedding", 2)


def test_index_is_hnsw_cosine(db):
    definition = db.scalar(text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_embedding_chunks_embedding_hnsw'"))
    assert definition and "hnsw" in definition and "vector_cosine_ops" in definition


# ---------- cost logging ----------

def test_cost_uses_configured_per_model_rates(monkeypatch):
    assert estimate_cost("text-embedding-3-small", 1_000_000) == Decimal("0.020000")
    assert estimate_cost("text-embedding-3-small", 500) == Decimal("0.000010")
    assert estimate_cost("unknown-model", 1_000_000) == 0
    monkeypatch.setenv("AI_COST_RATES", '{"my-model": {"input_per_1m": 1.5, "output_per_1m": 3}}')
    get_settings.cache_clear()
    try:
        assert estimate_cost("my-model", 2_000_000, 1_000_000) == Decimal("6.000000")
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


# ---------- CLI ----------

def test_reembed_shop_rebuilds_missing_chunks_and_removes_orphans(client, token, db):
    create_product(client, token, name="One")
    create_product(client, token, name="Two")
    client.put(f"{API}/shop/policy", json={"delivery_time": "2 days"}, headers=auth_header(token))
    shop = shop_id_of(db, "Shop A")
    want = sorted(contents(db, shop))
    db.execute(text("DELETE FROM embedding_chunks"))
    db.add(EmbeddingChunk(shop_id=shop, source_type="product", source_id=424242, content="orphan", embedding=[0.1] * 1536))
    db.commit()

    assert cli_main(["reembed-shop", "--shop-id", str(shop)]) == 0
    db.expire_all()
    assert sorted(contents(db, shop)) == want  # rebuilt, orphan gone
    assert cli_main(["reembed-shop", "--shop-id", "999999"]) == 1


def test_reembed_all_covers_every_shop_and_reports_dimension_mismatch(client, db, monkeypatch):
    a = signup(client, "a@example.com", "Shop A")
    b = signup(client, "b@example.com", "Shop B")
    create_product(client, a, name="A item")
    create_product(client, b, name="B item")
    db.execute(text("DELETE FROM embedding_chunks"))
    db.commit()
    assert cli_main(["reembed-all"]) == 0
    assert len(contents(db, shop_id_of(db, "Shop A"))) == 1 and len(contents(db, shop_id_of(db, "Shop B"))) == 1

    monkeypatch.setenv("EMBEDDING_DIM", "8")  # config no longer matches the vector(1536) column
    get_settings.cache_clear()
    try:
        assert cli_main(["reembed-all"]) == 1
    finally:
        monkeypatch.setenv("EMBEDDING_DIM", "1536")
        get_settings.cache_clear()


def test_seed_queues_embeddings_for_demo_data(db, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "demo-password-1")
    assert cli_main(["seed"]) == 0
    products = db.scalar(text("SELECT count(*) FROM products"))
    product_chunks_n = db.scalar(text("SELECT count(*) FROM embedding_chunks WHERE source_type='product'"))
    policy_chunks_n = db.scalar(text("SELECT count(*) FROM embedding_chunks WHERE source_type='policy'"))
    assert products >= 8 and product_chunks_n >= products and policy_chunks_n >= 10
