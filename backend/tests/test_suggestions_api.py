import pytest
from sqlalchemy import select, update

from app.models import AiUsageLog, Message, Product
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


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
        "budget": add_product(client, token, "Budget Panjabi", 1200, 5, ["M", "L"], ["White"]),
        "eid": add_product(client, token, "Eid Panjabi", 900, 3, ["L", "XL"], ["Navy"]),
        "sold_out": add_product(client, token, "Premium Panjabi", 1400, 0, ["M", "L", "XL"], ["Navy"]),
        "silk": add_product(client, token, "Silk Panjabi", 2500, 9, ["M"], ["White"]),
        "saree": add_product(client, token, "Red Jamdani Saree", 4800, 6, [], ["Red"]),
    }
    return token, ids


def ask(client, token, session, text):
    r = client.post(f"{API}/test-chat/sessions/{session}/messages", json={"text": text}, headers=auth_header(token))
    assert r.status_code == 200, r.text
    return r.json()["ai_message"]


def start(client, token):
    return client.post(f"{API}/test-chat/sessions", headers=auth_header(token)).json()["id"]


def card_ids(message):
    return [c["id"] for c in message["extras"].get("suggested_products", [])]


def test_proposal_example_returns_matching_in_stock_products_with_price(client, shop, db):
    token, ids = shop
    sid = start(client, token)
    msg = ask(client, token, sid, "eid er jonno 1500 er moddhe panjabi")
    assert msg["intent"] == "suggestion"
    cards = msg["extras"]["suggested_products"]
    assert {c["id"] for c in cards} == {ids["budget"], ids["eid"]}  # in stock and <= 1500; not Premium (0), not Silk (2500)
    assert 1 <= len(cards) <= 3
    prices = {c["name"]: c["price"] for c in cards}
    assert prices == {"Budget Panjabi": 1200.0, "Eid Panjabi": 900.0}
    assert "Budget Panjabi" in msg["text"] and "1200" in msg["text"]
    assert msg["extras"]["needs"]["budget_max"] == 1500.0 and msg["extras"]["needs"]["occasion"] == "eid"

    stored = db.scalar(select(Message).where(Message.chat_id == sid, Message.sender == "ai"))
    assert [c["id"] for c in stored.extras["suggested_products"]] == card_ids(msg)  # kept in the AI message extras
    listed = client.get(f"{API}/test-chat/sessions/{sid}/messages", headers=auth_header(token)).json()
    assert card_ids(listed[-1]) == card_ids(msg)  # and returned when the conversation is loaded

    ops = {r.operation for r in db.scalars(select(AiUsageLog))}
    assert {"intent", "suggestion_needs", "chat_reply", "embedding"} <= ops


def test_a_zero_stock_product_is_never_suggested(client, shop):
    token, ids = shop
    sid = start(client, token)
    seen: set[int] = set()
    for text in [
        "panjabi dekhan",
        "Premium Panjabi dekhan",
        "Show me a panjabi under 2000",
        "1500 er moddhe panjabi dekhan",
        "navy panjabi dekhan",
        "kichu dekhan 2000 taka er moddhe",
    ]:
        seen |= set(card_ids(ask(client, token, sid, text)))
    assert seen and ids["sold_out"] not in seen


def test_stock_is_read_live_not_from_embeddings(client, shop, db):
    token, ids = shop
    sid = start(client, token)
    assert ids["eid"] in card_ids(ask(client, token, sid, "1500 er moddhe panjabi dekhan"))
    # the last piece is sold; this bypasses the product service, so no embedding job runs
    db.execute(update(Product).where(Product.id == ids["eid"]).values(stock_count=0))
    db.commit()
    assert ids["eid"] not in card_ids(ask(client, token, sid, "1500 er moddhe panjabi dekhan"))


@pytest.mark.parametrize(
    "text,style",
    [
        ("Show me a panjabi under 1500", "english"),
        ("1500 er moddhe panjabi dekhan", "banglish"),
        ("panjabi দেখান ১৫০০ টাকার মধ্যে", "bangla"),
    ],
)
def test_suggestions_in_english_banglish_and_bangla(client, shop, text, style):
    token, ids = shop
    msg = ask(client, token, start(client, token), text)
    assert msg["language_style"] == style
    assert set(card_ids(msg)) == {ids["budget"], ids["eid"]}


def test_no_match_is_honest_and_has_no_cards(client, shop):
    token, _ = shop
    sid = start(client, token)
    english = ask(client, token, sid, "Show me a laptop under 1000")
    assert card_ids(english) == [] and "could not find an in-stock product" in english["text"]
    bangla = ask(client, token, sid, "laptop দেখান ১০০০ টাকার মধ্যে")
    assert card_ids(bangla) == [] and "দুঃখিত" in bangla["text"]
    too_cheap = ask(client, token, sid, "panjabi dekhan 100 taka er moddhe")
    assert card_ids(too_cheap) == [] and too_cheap["extras"]["handover"]["needed"] is False


def test_at_most_three_cards(client, shop):
    token, _ = shop
    for i in range(5):
        add_product(client, token, f"Cotton Panjabi {i}", 700 + i * 10, 4)
    cards = card_ids(ask(client, token, start(client, token), "panjabi dekhan"))
    assert 1 <= len(cards) <= 3


def test_cards_carry_the_first_photo_url(client, shop):
    token, ids = shop
    files = [("files", (f"p{i}.png", PNG, "image/png")) for i in range(2)]
    photos = client.post(f"{API}/products/{ids['eid']}/photos", files=files, headers=auth_header(token)).json()["photos"]
    msg = ask(client, token, start(client, token), "1500 er moddhe panjabi dekhan")
    by_id = {c["id"]: c for c in msg["extras"]["suggested_products"]}
    assert by_id[ids["eid"]]["photo"] == photos[0] and photos[0].startswith("http")
    assert by_id[ids["budget"]]["photo"] is None  # no photo uploaded


def test_other_shops_products_are_never_suggested(client, shop):
    token, ids = shop
    other = signup(client, "b@example.com", "Shop B")
    cheap = add_product(client, other, "Cheap Panjabi", 500, 20)
    mine = card_ids(ask(client, token, start(client, token), "panjabi dekhan"))
    assert mine and cheap not in mine
    theirs = card_ids(ask(client, other, start(client, other), "panjabi dekhan"))
    assert theirs == [cheap]
