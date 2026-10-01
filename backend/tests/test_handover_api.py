import pytest
from sqlalchemy import select

from app.cli import main as cli_main
from app.core.config import get_settings
from app.models import AiUsageLog, Chat, HandoverEvent, Message, Notification, Shop
from app.services.conversation import ConversationService
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"

REASON_CASES = [
    ("complaint", "product ta kharap chilo"),
    ("refund", "I want a refund for my order"),
    ("abusive_language", "tui harami"),
    ("human_requested", "I want to talk to a person"),
    ("off_topic", "who won the cricket match?"),
    ("low_confidence", "???"),
    ("not_in_shop_data", "Blender price koto?"),
]


def signup(client, email="a@example.com", shop="Rina Fashion House"):
    r = client.post(
        f"{API}/auth/signup",
        json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD},
    )
    return r.json()["access_token"]


def add_product(client, token, name, price, stock):
    r = client.post(
        f"{API}/products",
        json={"name": name, "description": "", "price": price, "sizes": [], "colours": [], "stock_count": stock},
        headers=auth_header(token),
    )
    assert r.status_code == 201, r.text


@pytest.fixture
def shop(client):
    token = signup(client)
    add_product(client, token, "Red Jamdani Saree", 4800, 6)
    return token


def start(client, token):
    return client.post(f"{API}/test-chat/sessions", headers=auth_header(token)).json()["id"]


def send(client, token, sid, text):
    r = client.post(f"{API}/test-chat/sessions/{sid}/messages", json={"text": text}, headers=auth_header(token))
    assert r.status_code == 200, r.text
    return r.json()


def messenger_chat(db, shop_id, psid="psid-1", name="Nasrin"):
    chat = Chat(shop_id=shop_id, channel="messenger", customer_psid=psid, customer_name=name)
    db.add(chat)
    db.commit()
    return chat


def events(db):
    db.expire_all()
    return list(db.scalars(select(HandoverEvent).order_by(HandoverEvent.id)))


def notifications(db):
    db.expire_all()
    return list(db.scalars(select(Notification).order_by(Notification.id)))


# ----------------------------------------------------------------- flag, pause, record


@pytest.mark.parametrize("reason,message", REASON_CASES)
def test_each_reason_flags_the_test_chat_pauses_the_ai_and_records_an_event(client, shop, db, reason, message):
    sid = start(client, shop)
    res = send(client, shop, sid, message)

    assert res["handover"] == {"needed": True, "reason": reason}
    assert res["ai_message"] is not None  # a short holding reply
    assert res["ai_message"]["extras"]["handover"]["reason"] == reason
    assert res["chat"] == {"is_flagged": True, "flag_reason": reason, "ai_paused": True}

    db.expire_all()
    chat = db.get(Chat, sid)
    assert (chat.is_flagged, chat.flag_reason, chat.ai_paused) == (True, reason, True) and chat.flagged_at is not None
    (event,) = events(db)
    assert (event.shop_id, event.chat_id, event.reason) == (chat.shop_id, sid, reason) and event.created_at is not None
    assert notifications(db) == []  # test-chat flags are shown in the test chat window only

    listed = client.get(f"{API}/test-chat/sessions", headers=auth_header(shop)).json()[0]
    assert (listed["is_flagged"], listed["flag_reason"], listed["ai_paused"]) == (True, reason, True)


def test_a_normal_message_is_not_flagged(client, shop, db):
    sid = start(client, shop)
    res = send(client, shop, sid, "Red Jamdani Saree price koto?")
    assert res["handover"] == {"needed": False, "reason": None}
    assert res["chat"] == {"is_flagged": False, "flag_reason": None, "ai_paused": False}
    assert events(db) == [] and notifications(db) == []


def test_the_holding_reply_is_polite_in_the_customers_style_and_promises_nothing(client, shop):
    english = send(client, shop, start(client, shop), "I want a refund for my order")["ai_message"]["text"]
    banglish = send(client, shop, start(client, shop), "ami refund chai")["ai_message"]["text"]
    bangla = send(client, shop, start(client, shop), "আমি টাকা ফেরত চাই")["ai_message"]["text"]
    assert "someone from the shop will reply" in english
    assert "shop-er kew shigroi apnake reply korbe" in banglish
    assert "দোকানের কেউ শীঘ্রই আপনাকে উত্তর দেবে" in bangla
    for text in (english, banglish, bangla):
        assert "discount" not in text.lower() and "will refund" not in text.lower()
        assert not any(ch.isdigit() for ch in text.split("\n\n")[-1])


def test_the_first_ai_reply_can_be_a_flag_and_still_carries_the_disclosure(client, shop):
    text = send(client, shop, start(client, shop), "I want to talk to a person")["ai_message"]["text"]
    assert text.startswith("Hi! I'm the automatic assistant") and text.endswith("Please wait a little.")


# ----------------------------------------------------------------- paused chats


def test_a_paused_chat_stores_the_customers_message_but_writes_no_ai_reply(client, shop, db):
    sid = start(client, shop)
    send(client, shop, sid, "product ta kharap chilo")
    usage_before = len(db.scalars(select(AiUsageLog)).all())

    res = send(client, shop, sid, "Red Jamdani Saree price koto?")
    assert res["ai_message"] is None and res["handover"] == {"needed": False, "reason": None}
    assert res["chat"]["ai_paused"] is True and res["customer_message"]["text"] == "Red Jamdani Saree price koto?"

    db.expire_all()
    senders = [m.sender for m in db.scalars(select(Message).where(Message.chat_id == sid).order_by(Message.id))]
    assert senders == ["customer", "ai", "customer"]  # the new customer message is kept, nothing answered it
    assert len(db.scalars(select(AiUsageLog)).all()) == usage_before  # the AI was not even called
    assert len(events(db)) == 1  # not flagged a second time

    again = send(client, shop, sid, "hello?")
    assert again["ai_message"] is None
    assert [m.sender for m in db.scalars(select(Message).where(Message.chat_id == sid))].count("ai") == 1


def test_resuming_the_ai_is_possible_by_clearing_the_pause(client, shop, db):
    """Prompt 15 adds the button; the service only needs ai_paused to be false again."""
    sid = start(client, shop)
    send(client, shop, sid, "product ta kharap chilo")
    chat = db.get(Chat, sid)
    chat.ai_paused = False
    db.commit()
    res = send(client, shop, sid, "Red Jamdani Saree price koto?")
    assert res["ai_message"] is not None and "4800" in res["ai_message"]["text"]


# ----------------------------------------------------------------- Messenger notifications


@pytest.mark.parametrize("reason,message", REASON_CASES)
def test_messenger_chats_create_a_notification_for_every_reason(client, shop, db, reason, message):
    shop_id = db.scalar(select(Shop.id))
    chat = messenger_chat(db, shop_id)
    result = ConversationService(db).handle_customer_message(chat, message)

    assert result.engine_result.handover.reason == reason and result.ai_message is not None
    (note,) = notifications(db)
    assert (note.shop_id, note.type, note.chat_id, note.reason) == (shop_id, "chat_flagged", chat.id, reason)
    assert note.read_at is None and note.created_at is not None
    (event,) = events(db)
    assert (event.chat_id, event.reason) == (chat.id, reason)
    db.expire_all()
    flagged = db.get(Chat, chat.id)
    assert (flagged.is_flagged, flagged.flag_reason, flagged.ai_paused) == (True, reason, True)


def test_a_paused_messenger_chat_gets_no_reply_and_no_second_notification(client, shop, db):
    chat = messenger_chat(db, db.scalar(select(Shop.id)))
    service = ConversationService(db)
    service.handle_customer_message(chat, "product ta kharap chilo")
    second = service.handle_customer_message(chat, "hello? anyone?")
    assert second.ai_message is None and second.engine_result is None
    assert len(notifications(db)) == 1 and len(events(db)) == 1


def test_the_confidence_threshold_comes_from_settings(client, shop, db, monkeypatch):
    monkeypatch.setenv("AI_CONFIDENCE_THRESHOLD", "0.95")
    get_settings.cache_clear()
    try:
        res = send(client, shop, start(client, shop), "Red Jamdani Saree price koto?")
        assert res["handover"] == {"needed": True, "reason": "low_confidence"}
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
    assert get_settings().ai_confidence_threshold == 0.5  # the documented default


# ----------------------------------------------------------------- notifications API


def seed_notifications(client, db):
    """Shop A: 3 flagged Messenger chats (the middle one already read). Shop B: 1."""
    a = signup(client, "a2@example.com", "Shop A2")
    b = signup(client, "b@example.com", "Shop B")
    shop_a, shop_b = db.scalars(select(Shop.id).where(Shop.name.in_(["Shop A2", "Shop B"])).order_by(Shop.id)).all()
    service = ConversationService(db)
    for i, (message, name) in enumerate([("product ta kharap", "Nasrin"), ("I want a refund", "Arif"), ("tui harami", "Rahim")]):
        service.handle_customer_message(messenger_chat(db, shop_a, f"a-{i}", name), message)
    service.handle_customer_message(messenger_chat(db, shop_b, "b-0", "Sumi"), "I want to talk to a person")
    mid = db.scalars(select(Notification).where(Notification.shop_id == shop_a).order_by(Notification.id)).all()[1]
    return a, b, shop_a, shop_b, mid.id


def test_notifications_are_listed_unread_first_and_shop_scoped(client, db):
    a, b, shop_a, shop_b, mid_id = seed_notifications(client, db)
    client.post(f"{API}/notifications/{mid_id}/read", headers=auth_header(a))

    body = client.get(f"{API}/notifications", headers=auth_header(a)).json()
    assert body["unread_count"] == 2 and len(body["items"]) == 3
    assert [i["read_at"] is None for i in body["items"]] == [True, True, False]  # unread first
    assert [i["reason"] for i in body["items"]] == ["abusive_language", "complaint", "refund"]  # newest unread first
    assert {i["customer_name"] for i in body["items"]} == {"Nasrin", "Arif", "Rahim"}
    assert all(i["type"] == "chat_flagged" and i["chat_id"] for i in body["items"])

    other = client.get(f"{API}/notifications", headers=auth_header(b)).json()
    assert other["unread_count"] == 1 and [i["reason"] for i in other["items"]] == ["human_requested"]


def test_mark_one_and_mark_all_read(client, db):
    a, b, shop_a, shop_b, mid_id = seed_notifications(client, db)
    ha, hb = auth_header(a), auth_header(b)
    first = client.get(f"{API}/notifications", headers=ha).json()["items"][0]["id"]

    r = client.post(f"{API}/notifications/{first}/read", headers=ha)
    assert r.status_code == 200 and r.json()["read_at"] is not None
    assert client.post(f"{API}/notifications/{first}/read", headers=ha).status_code == 200  # idempotent
    assert client.get(f"{API}/notifications", headers=ha).json()["unread_count"] == 2

    assert client.post(f"{API}/notifications/{first}/read", headers=hb).status_code == 404  # not B's
    assert client.post(f"{API}/notifications/999999/read", headers=ha).status_code == 404
    assert client.get(f"{API}/notifications", headers=hb).json()["unread_count"] == 1  # B untouched

    assert client.post(f"{API}/notifications/read-all", headers=ha).json() == {"marked": 2}
    assert client.get(f"{API}/notifications", headers=ha).json()["unread_count"] == 0
    assert client.post(f"{API}/notifications/read-all", headers=ha).json() == {"marked": 0}
    assert client.get(f"{API}/notifications", headers=hb).json()["unread_count"] == 1  # still B's own


def test_moderators_can_use_notifications_but_anonymous_and_admin_cannot(client, db, monkeypatch):
    a, _, _, _, _ = seed_notifications(client, db)
    client.post(f"{API}/shop/staff", json={"email": "mod@example.com", "full_name": "Mod", "password": PASSWORD}, headers=auth_header(a))
    mod = auth_header(client.post(f"{API}/auth/login", json={"email": "mod@example.com", "password": PASSWORD}).json()["access_token"])
    assert client.get(f"{API}/notifications", headers=mod).json()["unread_count"] == 3
    assert client.post(f"{API}/notifications/read-all", headers=mod).json() == {"marked": 3}

    assert client.get(f"{API}/notifications").status_code == 401
    assert client.post(f"{API}/notifications/read-all").status_code == 401
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    cli_main(["create-admin", "--email", "admin@example.com"])
    admin = auth_header(client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": PASSWORD}).json()["access_token"])
    assert client.get(f"{API}/notifications", headers=admin).status_code == 403


# ----------------------------------------------------------------- seeded demo data


def test_seed_creates_flagged_messenger_chats_with_notifications_idempotently(db, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "demo-password-1")
    assert cli_main(["seed"]) == 0
    chats = db.scalars(select(Chat).where(Chat.channel == "messenger")).all()
    flagged = [c for c in chats if c.is_flagged]
    assert len(chats) == 4 and len(flagged) == 3 and all(c.ai_paused for c in flagged)
    assert sorted(c.flag_reason for c in flagged) == ["complaint", "human_requested", "refund"]
    assert len(events(db)) == 3
    notes = notifications(db)
    assert len(notes) == 3 and sum(n.read_at is None for n in notes) == 2
    assert cli_main(["seed"]) == 0
    assert len(db.scalars(select(Chat).where(Chat.channel == "messenger")).all()) == 4 and len(notifications(db)) == 3
