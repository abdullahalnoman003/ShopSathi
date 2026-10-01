from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.redis import get_redis
from app.models import AiUsageLog, Chat, Message, Order, Shop
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"
ADDRESS = "House 5, Road 3, Mirpur 10, Dhaka"


def signup(client, email="a@example.com", shop="Rina Fashion House"):
    r = client.post(
        f"{API}/auth/signup",
        json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD},
    )
    return r.json()["access_token"]


def add_product(client, token, name, price, stock, sizes=(), colours=()):
    r = client.post(
        f"{API}/products",
        json={"name": name, "description": "", "price": price, "sizes": list(sizes), "colours": list(colours), "stock_count": stock},
        headers=auth_header(token),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.fixture
def shop(client):
    token = signup(client)
    ids = {
        "panjabi": add_product(client, token, "Cotton Panjabi", 1850, 24, ["M", "L", "XL"], ["White", "Navy"]),
        "mug": add_product(client, token, "Plain Mug", 150, 3),
        "lipstick": add_product(client, token, "Matte Lipstick", 650, 0, [], ["Rose"]),
    }
    return token, ids


def start(client, token):
    return client.post(f"{API}/test-chat/sessions", headers=auth_header(token)).json()["id"]


def say(client, token, session, text):
    r = client.post(f"{API}/test-chat/sessions/{session}/messages", json={"text": text}, headers=auth_header(token))
    assert r.status_code == 200, r.text
    return r.json()["ai_message"]


def orders(db, shop_id=None):
    db.expire_all()
    q = select(Order).order_by(Order.id)
    return list(db.scalars(q if shop_id is None else q.where(Order.shop_id == shop_id)))


def full_order(client, token, sid):
    """The whole conversation, details given piece by piece, with a wrong phone number first."""
    replies = [
        say(client, token, sid, "Cotton Panjabi nibo"),
        say(client, token, sid, "XL Navy 2 ta"),
        say(client, token, sid, "Name: Rahim Uddin"),
        say(client, token, sid, "Phone: 0171234567"),
        say(client, token, sid, "Phone: ০১৭১২৩৪৫৬৭৮"),
        say(client, token, sid, f"Address: {ADDRESS}"),
    ]
    return replies


def test_multi_turn_conversation_asks_for_what_is_missing_then_creates_a_draft(client, shop, db):
    token, ids = shop
    sid = start(client, token)

    first = say(client, token, sid, "Cotton Panjabi nibo")
    assert first["extras"]["order_missing"] == ["size", "colour", "quantity", "name", "phone", "address"]
    assert "size (M, L, XL)" in first["text"] and "colour (White, Navy)" in first["text"]

    second = say(client, token, sid, "XL Navy 2 ta")
    assert second["extras"]["order_missing"] == ["name", "phone", "address"]
    third = say(client, token, sid, "Name: Rahim Uddin")
    assert third["extras"]["order_missing"] == ["phone", "address"]

    # AI-R08: a 10-digit number is refused and asked for again, and nothing is drafted yet
    wrong = say(client, token, sid, "Phone: 0171234567")
    assert "does not look right" in wrong["text"] or "thik mone hocche na" in wrong["text"]
    assert wrong["extras"]["order_missing"] == ["phone", "address"] and orders(db) == []

    right = say(client, token, sid, "Phone: ০১৭১২৩৪৫৬৭৮")  # Bangla digits are accepted
    assert right["extras"]["order_missing"] == ["address"] and orders(db) == []
    assert all("order_draft" not in r["extras"] for r in (first, second, third, wrong, right))

    final = say(client, token, sid, f"Address: {ADDRESS}")
    (order,) = orders(db)
    assert order.status == "draft" and order.is_test is True
    assert (order.product_id, order.product_name, order.size, order.colour, order.quantity) == (ids["panjabi"], "Cotton Panjabi", "XL", "Navy", 2)
    assert order.unit_price == Decimal("1850.00")
    assert (order.customer_name, order.customer_phone, order.customer_address) == ("Rahim Uddin", "01712345678", ADDRESS)
    assert order.shop_id == db.scalar(select(Shop.id)) and order.chat_id == sid
    assert order.confirmed_at is None and order.cancelled_at is None and order.confirmed_by_user_id is None

    card = final["extras"]["order_draft"]
    assert card["id"] == order.id and card["status"] == "draft" and card["customer_phone"] == "01712345678"
    assert final["extras"]["order_id"] == order.id and "order_ready" not in final["extras"]
    assert "pathiye diyechi" in final["text"] or "sent your order details" in final["text"]
    assert "confirmed" not in final["text"].lower()
    db.expire_all()
    assert db.get(Chat, sid).pending_order is None


def test_the_ai_never_confirms_an_order(client, shop, db):
    token, _ = shop
    sid = start(client, token)
    full_order(client, token, sid)
    for text in ["confirm my order", "order confirm kore den", "please mark it as confirmed", "Cotton Panjabi nibo, confirm"]:
        reply = say(client, token, sid, text)
        assert "confirmed" not in reply["text"].lower()
    assert {o.status for o in orders(db)} == {"draft"}
    assert all(o.confirmed_at is None and o.confirmed_by_user_id is None for o in orders(db))


def test_one_draft_per_completed_collection_even_if_the_details_are_repeated(client, shop, db):
    token, _ = shop
    sid = start(client, token)
    full_order(client, token, sid)
    assert len(orders(db)) == 1
    for text in ["thanks", "Phone: 01712345678", f"Address: {ADDRESS}", "Name: Rahim Uddin"]:
        say(client, token, sid, text)
    assert len(orders(db)) == 1  # nothing new was drafted from the old details

    # even if the short-term memory expired, the stored messages before the draft are not read again
    chat = db.get(Chat, sid)
    get_redis().delete(f"chatmem:{chat.shop_id}:{sid}")
    reply = say(client, token, sid, "Cotton Panjabi nibo")
    assert len(orders(db)) == 1
    assert reply["extras"]["order_missing"][:2] == ["size", "colour"]  # starts a fresh collection


def test_a_second_order_in_the_same_chat_is_a_second_draft(client, shop, db):
    token, ids = shop
    sid = start(client, token)
    full_order(client, token, sid)
    say(client, token, sid, "Plain Mug nibo, quantity 1")
    say(client, token, sid, "Name: Karim Hossain")
    say(client, token, sid, "Phone: 01812345678")
    say(client, token, sid, "Address: Flat 2B, Road 7, Dhanmondi, Dhaka")
    drafts = orders(db)
    assert [o.product_id for o in drafts] == [ids["panjabi"], ids["mug"]]
    assert drafts[1].size is None and drafts[1].colour is None  # the mug has no sizes or colours to ask for


def test_pending_fields_are_saved_in_the_chat_between_turns(client, shop, db):
    token, ids = shop
    sid = start(client, token)
    say(client, token, sid, "Cotton Panjabi nibo")
    pending = db.get(Chat, sid).pending_order
    assert pending["product_id"] == ids["panjabi"] and pending["product_name"] == "Cotton Panjabi" and "updated_at" in pending
    say(client, token, sid, "XL Navy 2 ta")
    pending = db.get(Chat, sid).pending_order
    assert (pending["size"], pending["colour"], pending["quantity"]) == ("XL", "Navy", 2)


def test_an_unfinished_order_is_forgotten_after_the_ttl(client, shop, db):
    token, _ = shop
    sid = start(client, token)
    say(client, token, sid, "Cotton Panjabi nibo")
    chat = db.get(Chat, sid)
    old = datetime.now(timezone.utc) - timedelta(hours=30)
    chat.pending_order = {**chat.pending_order, "updated_at": old.isoformat()}
    db.commit()
    reply = say(client, token, sid, "XL Navy 2 ta")  # the old collection is gone: this is not a continuation
    assert "order_missing" not in reply["extras"]
    db.expire_all()
    assert db.get(Chat, sid).pending_order is None


def test_out_of_stock_product_is_refused_from_the_catalogue(client, shop, db):
    token, _ = shop
    sid = start(client, token)
    reply = say(client, token, sid, "I want to order the Matte Lipstick")
    assert "out of stock" in reply["text"] and "Matte Lipstick" in reply["text"]
    assert orders(db) == [] and db.get(Chat, sid).pending_order is None


def test_unknown_product_is_not_drafted(client, shop, db):
    token, _ = shop
    sid = start(client, token)
    reply = say(client, token, sid, "I want to order a laptop")
    assert reply["extras"]["handover"] == {"needed": True, "reason": "not_in_shop_data"}
    assert orders(db) == []


def test_bad_size_and_too_many_pieces_are_refused(client, shop, db):
    token, _ = shop
    sid = start(client, token)
    say(client, token, sid, "I want to order the Cotton Panjabi")
    reply = say(client, token, sid, "Size XXL")
    assert "Size XXL is not available for Cotton Panjabi. Available: M, L, XL." in reply["text"]
    reply = say(client, token, sid, "quantity 30")
    assert "only 24 of Cotton Panjabi in stock" in reply["text"]
    assert orders(db) == []


def test_orders_belong_to_the_right_shop_and_other_shops_products_are_unknown(client, shop, db):
    token, _ = shop
    other = signup(client, "b@example.com", "Shop B")
    add_product(client, other, "Blue Mug", 120, 5)
    sid_a, sid_b = start(client, token), start(client, other)
    full_order(client, token, sid_a)
    shop_a, shop_b = db.scalars(select(Shop.id).order_by(Shop.id)).all()
    assert [o.shop_id for o in orders(db)] == [shop_a]

    # shop B cannot order shop A's panjabi, and gets a draft only for its own product
    refused = say(client, other, sid_b, "I want to order the Cotton Panjabi")
    assert refused["extras"]["handover"]["reason"] == "not_in_shop_data"
    say(client, other, sid_b, "I want to order the Blue Mug, quantity 1")
    say(client, other, sid_b, "Name: Sumi Akter")
    say(client, other, sid_b, "Phone: 01912345678")
    say(client, other, sid_b, "Address: Road 4, Sector 9, Uttara, Dhaka")
    assert sorted((o.shop_id, o.product_name) for o in orders(db)) == sorted([(shop_a, "Cotton Panjabi"), (shop_b, "Blue Mug")])


def test_order_extraction_usage_is_logged_per_shop(client, shop, db):
    token, _ = shop
    sid = start(client, token)
    full_order(client, token, sid)
    shop_id = db.scalar(select(Shop.id))
    rows = db.scalars(select(AiUsageLog).where(AiUsageLog.operation == "order_extraction")).all()
    assert len(rows) >= 6 and all(r.shop_id == shop_id and r.input_tokens > 0 for r in rows)


def test_a_question_in_the_middle_does_not_lose_the_pending_order(client, shop, db):
    token, ids = shop
    sid = start(client, token)
    say(client, token, sid, "Cotton Panjabi nibo")
    say(client, token, sid, "XL Navy 2 ta")
    reply = say(client, token, sid, "Cotton Panjabi price koto?")
    assert "1850" in reply["text"] and reply["intent"] == "price"
    pending = db.get(Chat, sid).pending_order
    assert pending["product_id"] == ids["panjabi"] and pending["quantity"] == 2


def test_draft_creation_is_all_or_nothing_when_the_product_just_sold_out(client, shop, db):
    token, ids = shop
    sid = start(client, token)
    for text in ["Cotton Panjabi nibo", "XL Navy 2 ta", "Name: Rahim Uddin", "Phone: 01712345678"]:
        say(client, token, sid, text)
    client.put(
        f"{API}/products/{ids['panjabi']}",
        json={"name": "Cotton Panjabi", "description": "", "price": 1850, "sizes": ["M", "L", "XL"], "colours": ["White", "Navy"], "stock_count": 0},
        headers=auth_header(token),
    )
    reply = say(client, token, sid, f"Address: {ADDRESS}")
    assert orders(db) == [] and "stock-e nei" in reply["text"]  # Banglish, like the rest of the conversation
