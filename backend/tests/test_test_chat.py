import pytest
from shopsathi_ai.engine import ConversationEngine
from shopsathi_ai.providers import LLMProviderError
from shopsathi_ai.providers.mock import MockEmbeddingProvider, MockLLMProvider
from sqlalchemy import select

from app.ai_adapters.gateway import BackendShopDataGateway
from app.core.config import get_settings
from app.core.redis import get_redis
from app.models import AiUsageLog, Chat, Message, Shop
from app.services.chat_memory import ChatMemoryService
from app.services.conversation import ConversationService
from app.services.usage import UsageLimitService
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"


def signup(client, email="a@example.com", shop="Rina Fashion House"):
    r = client.post(
        f"{API}/auth/signup",
        json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD},
    )
    return r.json()["access_token"]


def add_product(client, token, **over):
    body = {"name": "x", "description": "", "price": 100, "sizes": [], "colours": [], "stock_count": 5}
    body.update(over)
    r = client.post(f"{API}/products", json=body, headers=auth_header(token))
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def shop(client):
    """A demo-like shop: products and a delivery policy (embeddings are built inline in tests)."""
    token = signup(client)
    add_product(client, token, name="Red Jamdani Saree", price=4800, colours=["Red"], stock_count=6, description="Hand-woven.")
    add_product(client, token, name="Cotton Panjabi", price=1850, sizes=["M", "L", "XL"], colours=["White", "Navy"], stock_count=24)
    add_product(client, token, name="Matte Lipstick", price=650, colours=["Rose"], stock_count=0)
    client.put(
        f"{API}/shop/policy",
        json={
            "delivery_time": "Inside Dhaka 1-2 days, outside Dhaka 3-5 days.",
            "return_rules": "Unused items can be returned within 3 days.",
            "payment_options": "Cash on delivery or bKash.",
            "delivery_areas": [{"area_name": "Inside Dhaka", "charge": 60}, {"area_name": "Khagan", "charge": 100}],
        },
        headers=auth_header(token),
    )
    return token


def start(client, token):
    r = client.post(f"{API}/test-chat/sessions", headers=auth_header(token))
    assert r.status_code == 201
    return r.json()["id"]


def say(client, token, session, text):
    r = client.post(f"{API}/test-chat/sessions/{session}/messages", json={"text": text}, headers=auth_header(token))
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------- conversation


def test_proposal_example_messages_get_grounded_replies(client, shop):
    sid = start(client, shop)

    first = say(client, shop, sid, "Red Jamdani Saree price koto?")
    text = first["ai_message"]["text"]
    assert text.startswith("Assalamu alaikum! Ami Rina Fashion House-er automatic assistant")  # banglish disclosure
    assert "4800" in text and "Red Jamdani Saree" in text
    assert first["ai_message"]["intent"] == "price" and first["ai_message"]["language_style"] == "banglish"
    assert first["handover"] == {"needed": False, "reason": None}

    size = say(client, shop, sid, "Cotton Panjabi XL ache?")["ai_message"]
    assert "automatic assistant" not in size["text"] and "XL" in size["text"] and "24" in size["text"]
    assert size["intent"] == "size_stock"

    follow_up = say(client, shop, sid, "eta ki XL e pawa jabe?")["ai_message"]  # "eta" = the panjabi, from memory
    assert "Cotton Panjabi" in follow_up["text"] and follow_up["extras"]["entities"]["product_name"] == "Cotton Panjabi"

    delivery = say(client, shop, sid, "Khagan e delivery charge koto?")["ai_message"]
    assert "100" in delivery["text"] and "Khagan" in delivery["text"] and delivery["intent"] == "delivery"

    out_of_stock = say(client, shop, sid, "Matte Lipstick ache?")["ai_message"]["text"]
    assert "stock" in out_of_stock.lower() or "nei" in out_of_stock.lower()


def test_unknown_question_says_i_will_check_with_the_shop(client, shop):
    for message, expected in [
        ("Blender price koto?", "Ami shop-er sathe check kore apnake janacchi."),
        ("What is the price of the blender?", "I'll check with the shop and get back to you."),
    ]:
        sid = start(client, shop)  # a flagged conversation is paused, so one conversation per question
        say(client, shop, sid, "hello")  # consume the disclosure
        res = say(client, shop, sid, message)
        assert res["ai_message"]["text"] == expected
        assert res["handover"] == {"needed": True, "reason": "not_in_shop_data"}
        assert res["ai_message"]["extras"]["handover"]["needed"] is True


def test_bangla_script_reply_is_in_bangla(client, shop):
    sid = start(client, shop)
    res = say(client, shop, sid, "ব্লেন্ডারের দাম কত?")["ai_message"]
    assert res["language_style"] == "bangla"
    assert "স্বয়ংক্রিয় সহকারী" in res["text"] and "আমি দোকানের সাথে জেনে আপনাকে জানাচ্ছি।" in res["text"]


def test_disclosure_is_sent_in_the_first_ai_reply_only(client, shop, db):
    sid = start(client, shop)
    replies = [say(client, shop, sid, m)["ai_message"]["text"] for m in ("Hello", "Red Jamdani Saree price koto?", "Cotton Panjabi price koto?")]
    assert sum("automatic assistant" in r for r in replies) == 1 and "automatic assistant" in replies[0]
    assert db.scalar(select(Chat.ai_disclosure_sent).where(Chat.id == sid)) is True
    other = start(client, shop)  # a new conversation introduces itself again
    assert "automatic assistant" in say(client, shop, other, "Hello")["ai_message"]["text"]


def test_messages_are_persisted_with_ai_fields(client, shop, db):
    sid = start(client, shop)
    say(client, shop, sid, "Red Jamdani Saree price koto?")
    rows = db.scalars(select(Message).where(Message.chat_id == sid).order_by(Message.id)).all()
    assert [m.sender for m in rows] == ["customer", "ai"]
    customer, ai = rows
    assert customer.received_at is not None and ai.sent_at is not None
    assert (customer.intent, ai.intent) == ("price", "price") and ai.confidence is not None and ai.language_style == "banglish"
    assert ai.extras["tools"][0]["name"] == "search_products" and ai.extras["disclosure"] is True
    assert ai.extras["handover"] == {"needed": False, "reason": None, "detail": None}
    chat = db.get(Chat, sid)
    assert chat.channel == "test" and chat.last_customer_message_at is not None and chat.created_by_user_id is not None

    listed = client.get(f"{API}/test-chat/sessions/{sid}/messages", headers=auth_header(shop)).json()
    assert [m["sender"] for m in listed] == ["customer", "ai"] and listed[1]["text"] == ai.text


def test_ai_usage_is_logged_per_shop(client, shop, db):
    sid = start(client, shop)
    say(client, shop, sid, "Red Jamdani Saree price koto?")
    shop_id = db.scalar(select(Shop.id).where(Shop.name == "Rina Fashion House"))
    names = {r.operation for r in db.scalars(select(AiUsageLog).where(AiUsageLog.shop_id == shop_id))}
    assert {"intent", "chat_reply", "embedding"} <= names
    chat_logs = db.scalars(select(AiUsageLog).where(AiUsageLog.operation.in_(["intent", "chat_reply"]))).all()
    assert len(chat_logs) == 2 and all(r.shop_id == shop_id and r.input_tokens > 0 for r in chat_logs)
    assert {r.output_tokens > 0 for r in chat_logs} == {True}


def test_test_chats_are_not_counted_against_the_message_limit(client, shop, db):
    sid = start(client, shop)
    for m in ("Hello", "Red Jamdani Saree price koto?"):
        say(client, shop, sid, m)
    shop_id = db.scalar(select(Shop.id))
    assert UsageLimitService(db).get_usage(shop_id).used == 0


# ------------------------------------------------------------- sessions API


def test_session_list_and_validation(client, shop):
    h = auth_header(shop)
    s1, s2 = start(client, shop), start(client, shop)
    say(client, shop, s1, "Red Jamdani Saree price koto?")
    sessions = client.get(f"{API}/test-chat/sessions", headers=h).json()
    assert [s["id"] for s in sessions] == [s1, s2]  # most recently active first
    assert sessions[0]["message_count"] == 2 and sessions[0]["last_message"].startswith("Assalamu") and len(sessions[0]["last_message"]) <= 80
    assert sessions[1]["message_count"] == 0 and sessions[1]["last_message"] is None

    url = f"{API}/test-chat/sessions/{s1}/messages"
    assert client.post(url, json={"text": ""}, headers=h).status_code == 422
    assert client.post(url, json={"text": "   "}, headers=h).status_code == 422
    assert client.post(url, json={"text": "x" * 1001}, headers=h).status_code == 422
    assert client.post(f"{API}/test-chat/sessions/999999/messages", json={"text": "hi"}, headers=h).status_code == 404


def test_test_chat_of_shop_a_cannot_be_used_by_shop_b(client, shop):
    b = signup(client, "b@example.com", "Shop B")
    add_product(client, b, name="Blender", price=999)
    sid = start(client, shop)
    say(client, shop, sid, "Hello")
    hb = auth_header(b)
    assert client.get(f"{API}/test-chat/sessions/{sid}/messages", headers=hb).status_code == 404
    assert client.post(f"{API}/test-chat/sessions/{sid}/messages", json={"text": "hi"}, headers=hb).status_code == 404
    assert client.get(f"{API}/test-chat/sessions", headers=hb).json() == []
    # and shop A's AI never answers from shop B's catalogue
    reply = say(client, shop, sid, "Blender price koto?")["ai_message"]["text"]
    assert "999" not in reply and "check kore" in reply
    own = start(client, b)
    assert "999" in say(client, b, own, "Blender price koto?")["ai_message"]["text"]


def test_moderator_and_anonymous_are_blocked(client, shop):
    sid = start(client, shop)
    client.post(f"{API}/shop/staff", json={"email": "mod@example.com", "full_name": "Mod", "password": PASSWORD}, headers=auth_header(shop))
    mod = auth_header(client.post(f"{API}/auth/login", json={"email": "mod@example.com", "password": PASSWORD}).json()["access_token"])
    assert client.post(f"{API}/test-chat/sessions", headers=mod).status_code == 403
    assert client.get(f"{API}/test-chat/sessions", headers=mod).status_code == 403
    assert client.get(f"{API}/test-chat/sessions/{sid}/messages", headers=mod).status_code == 403
    assert client.post(f"{API}/test-chat/sessions/{sid}/messages", json={"text": "hi"}, headers=mod).status_code == 403
    assert client.post(f"{API}/test-chat/sessions").status_code == 401


# ------------------------------------------------- service, memory, privacy


def test_short_term_memory_keeps_only_the_last_turns(client, shop, db, monkeypatch):
    monkeypatch.setenv("CHAT_MEMORY_TURNS", "4")
    get_settings.cache_clear()
    try:
        sid = start(client, shop)
        for m in ("Hello", "Red Jamdani Saree price koto?", "Cotton Panjabi price koto?"):
            say(client, shop, sid, m)
        shop_id = db.scalar(select(Shop.id))
        key = f"chatmem:{shop_id}:{sid}"
        assert get_redis().llen(key) == 4  # 6 turns happened, only the last 4 are kept
        assert 0 < get_redis().ttl(key) <= get_settings().chat_memory_ttl_seconds
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_memory_is_rebuilt_from_the_database_when_redis_expired(client, shop, db):
    sid = start(client, shop)
    say(client, shop, sid, "Cotton Panjabi price koto?")
    shop_id = db.scalar(select(Shop.id))
    get_redis().delete(f"chatmem:{shop_id}:{sid}")
    reply = say(client, shop, sid, "eta ki XL e pawa jabe?")["ai_message"]
    assert "Cotton Panjabi" in reply["text"]  # context came back from the stored messages


class SpyEngine(ConversationEngine):
    def __init__(self, inner):
        self.inner = inner
        self.seen = []

    def process_customer_message(self, shop_id, chat_context, message):
        self.seen.append((shop_id, chat_context))
        return self.inner.process_customer_message(shop_id, chat_context, message)


def test_engine_only_gets_recent_turns_and_shop_name(client, shop, db, monkeypatch):
    monkeypatch.setenv("CHAT_MEMORY_TURNS", "4")
    get_settings.cache_clear()
    try:
        sid = start(client, shop)
        chat = db.get(Chat, sid)
        spy = SpyEngine(ConversationEngine(MockLLMProvider(), MockEmbeddingProvider(1536), BackendShopDataGateway(db)))
        service = ConversationService(db, spy)
        for m in ["Hello", "Red Jamdani Saree price koto?", "Cotton Panjabi price koto?", "Khagan e delivery charge koto?"]:
            service.handle_customer_message(chat, m)
        sizes = [len(ctx.recent_turns) for _, ctx in spy.seen]
        assert sizes == [0, 2, 4, 4]  # never more than the configured last N turns
        assert spy.seen[0][1].is_first_ai_reply and not spy.seen[1][1].is_first_ai_reply
        assert spy.seen[0][1].shop_name == "Rina Fashion House"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_service_is_channel_independent_and_survives_an_llm_outage(client, shop, db):
    """Prompt 14 will call handle_customer_message for 'messenger' chats."""
    shop_id = db.scalar(select(Shop.id))
    chat = Chat(shop_id=shop_id, channel="messenger", customer_psid="psid-123", customer_name="Customer")
    db.add(chat)
    db.commit()

    class Down(MockLLMProvider):
        def generate_json_with_usage(self, *a, **k):
            raise LLMProviderError("provider down")

    engine = ConversationEngine(Down(), MockEmbeddingProvider(1536), BackendShopDataGateway(db))
    result = ConversationService(db, engine).handle_customer_message(chat, "Red Jamdani Saree price koto?")
    assert (result.engine_result.handover.reason, result.engine_result.handover.detail) == ("low_confidence", "ai_unavailable")
    assert "check kore" in result.ai_message.text
    assert [m.sender for m in db.scalars(select(Message).where(Message.chat_id == chat.id).order_by(Message.id))] == ["customer", "ai"]


# ---------------------------------------------------------------- gateway tools


def test_gateway_tools_are_shop_scoped(client, shop, db):
    b = signup(client, "b@example.com", "Shop B")
    b_product = add_product(client, b, name="Red Silk Saree", price=7000)
    shop_a, shop_b = db.scalars(select(Shop.id).order_by(Shop.id)).all()
    gw = BackendShopDataGateway(db)

    found = gw.search_products(shop_a, "red saree", None, 5)
    assert [p.name for p in found] == ["Red Jamdani Saree"] and found[0].match == "name" and found[0].score == 1.0
    assert str(found[0].price) == "4800.00" and found[0].stock_count == 6
    assert [p.name for p in gw.search_products(shop_b, "red saree", None, 5)] == ["Red Silk Saree"]
    assert gw.search_products(shop_a, "blender", None, 5) == []
    assert gw.search_products(shop_a, "100%", None, 5) == []  # LIKE wildcards are not special

    # similarity is only a fallback: with a name match, other products are not mixed in
    vector = MockEmbeddingProvider(1536).embed(["red saree"])[0]
    assert [p.name for p in gw.search_products(shop_a, "red saree", vector, 5)] == ["Red Jamdani Saree"]
    fallback = gw.search_products(shop_a, "zzzz", vector, 2)
    assert fallback and all(p.match == "semantic" for p in fallback) and len(fallback) <= 2

    assert gw.check_stock(shop_a, b_product) is None  # another shop's product is invisible
    panjabi = gw.search_products(shop_a, "panjabi", None, 1)[0]
    stock = gw.check_stock(shop_a, panjabi.id, "xl", "navy")
    assert (stock.size_offered, stock.colour_offered, stock.in_stock, stock.stock_count) == (True, True, True, 24)
    assert gw.check_stock(shop_a, panjabi.id, "XXL", "Pink").size_offered is False
    assert gw.check_stock(shop_a, panjabi.id).size_offered is None

    assert gw.get_delivery_charge(shop_a, "khagan").charge == 100
    assert gw.get_delivery_charge(shop_b, "khagan").found is False  # B has no policy
    assert gw.get_delivery_charge(shop_a, "Khagan e").found is False
