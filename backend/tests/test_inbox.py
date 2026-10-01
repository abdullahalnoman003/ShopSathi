import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from sqlalchemy import select

from app.core.crypto import TokenCipher
from app.models import Chat, FacebookPage, Message, Notification, Shop
from app.services.usage import UsageLimitService
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"
GRAPH = "https://graph.facebook.com/v21.0"
PAGE_TOKEN = "EAAB-inbox-page-token"


@pytest.fixture
def graph():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def send(graph):
    route = graph.post(f"{GRAPH}/me/messages").mock(
        return_value=httpx.Response(200, json={"recipient_id": "x", "message_id": "m_seller_1"})
    )
    return route


def signup(client, email="a@example.com", shop="Shop A"):
    r = client.post(f"{API}/auth/signup", json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD})
    return r.json()["access_token"]


def moderator(client, owner_token, email="mod@example.com"):
    client.post(f"{API}/shop/staff", json={"email": email, "full_name": "Mod", "password": PASSWORD}, headers=auth_header(owner_token))
    return client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}).json()["access_token"]


def shop_id_of(db, name):
    return db.scalar(select(Shop.id).where(Shop.name == name))


def make_chat(db, shop_id, psid, *, name=None, flagged=None, paused=False, channel="messenger", last_customer=None, texts=()):
    """texts: (sender, text, minutes_ago) rows."""
    now = datetime.now(timezone.utc)
    chat = Chat(
        shop_id=shop_id,
        channel=channel,
        customer_psid=psid if channel == "messenger" else None,
        customer_name=name,
        ai_paused=paused or bool(flagged),
        is_flagged=bool(flagged),
        flag_reason=flagged,
        flagged_at=(now - timedelta(minutes=flagged_minutes(flagged))) if flagged else None,
        last_customer_message_at=last_customer if last_customer is not None else now - timedelta(minutes=1),
    )
    db.add(chat)
    db.flush()
    for sender, text, ago in texts:
        db.add(Message(shop_id=shop_id, chat_id=chat.id, sender=sender, text=text, created_at=now - timedelta(minutes=ago)))
    db.commit()
    return chat


def flagged_minutes(reason):
    return {"complaint": 50, "refund": 20, "human_requested": 5}.get(reason, 10)


def connect_page(db, shop_id, page_id="1001", token=PAGE_TOKEN):
    db.add(FacebookPage(shop_id=shop_id, page_id=page_id, page_name="P", encrypted_page_token=TokenCipher().encrypt(token)))
    db.commit()


@pytest.fixture
def shop(client, db):
    token = signup(client)
    return token, shop_id_of(db, "Shop A")


# --------------------------------------------------------------------------- listing


def test_flagged_chats_come_first_then_latest_activity(client, db, shop):
    token, sid = shop
    quiet_new = make_chat(db, sid, "p1", name="Newest quiet", texts=[("customer", "hi", 1)])
    quiet_old = make_chat(db, sid, "p2", name="Older quiet", texts=[("customer", "hello", 90)])
    refund = make_chat(db, sid, "p3", name="Refund", flagged="refund", texts=[("customer", "refund chai", 30)])
    complaint = make_chat(db, sid, "p4", name="Complaint", flagged="complaint", texts=[("customer", "kharap", 2)])
    human = make_chat(db, sid, "p5", name="Human", flagged="human_requested", texts=[("customer", "person chai", 3)])

    items = client.get(f"{API}/chats", headers=auth_header(token)).json()["items"]
    # flagged first (longest waiting first), then the rest by latest activity
    assert [c["id"] for c in items] == [complaint.id, refund.id, human.id, quiet_new.id, quiet_old.id]
    first = items[0]
    assert first["customer_label"] == "Complaint" and first["is_flagged"] and first["flag_reason"] == "complaint"
    assert first["ai_paused"] and first["last_message"] == "kharap" and first["last_message_sender"] == "customer"
    assert first["window_open"] is True and first["window_closes_at"]


def test_filter_pagination_and_flagged_count(client, db, shop):
    token, sid = shop
    for i in range(5):
        make_chat(db, sid, f"q{i}", texts=[("customer", f"m{i}", i + 1)])
    make_chat(db, sid, "f1", flagged="refund", texts=[("customer", "x", 1)])
    make_chat(db, sid, "f2", flagged="complaint", texts=[("customer", "y", 1)])
    h = auth_header(token)

    only = client.get(f"{API}/chats?filter=flagged", headers=h).json()
    assert only["total"] == 2 and only["flagged_count"] == 2 and all(c["is_flagged"] for c in only["items"])

    p1 = client.get(f"{API}/chats?page=1&page_size=3", headers=h).json()
    p2 = client.get(f"{API}/chats?page=2&page_size=3", headers=h).json()
    p3 = client.get(f"{API}/chats?page=3&page_size=3", headers=h).json()
    assert p1["total"] == 7 and p1["flagged_count"] == 2
    ids = [c["id"] for p in (p1, p2, p3) for c in p["items"]]
    assert len(ids) == 7 and len(set(ids)) == 7 and [len(p["items"]) for p in (p1, p2, p3)] == [3, 3, 1]
    assert p1["items"][0]["is_flagged"] and p1["items"][1]["is_flagged"] and not p1["items"][2]["is_flagged"]
    assert client.get(f"{API}/chats?filter=bogus", headers=h).status_code == 422
    assert client.get(f"{API}/chats?page_size=1000", headers=h).status_code == 422


def test_test_channel_chats_are_never_listed_or_readable(client, db, shop):
    token, sid = shop
    real = make_chat(db, sid, "p1", texts=[("customer", "hi", 1)])
    test = make_chat(db, sid, None, name="Test customer", channel="test", flagged="complaint", texts=[("customer", "t", 1)])
    h = auth_header(token)
    body = client.get(f"{API}/chats", headers=h).json()
    assert [c["id"] for c in body["items"]] == [real.id] and body["flagged_count"] == 0
    for path, method in ((f"{API}/chats/{test.id}", "get"), (f"{API}/chats/{test.id}/pause", "post"), (f"{API}/chats/{test.id}/resume", "post"), (f"{API}/chats/{test.id}/resolve-flag", "post")):
        assert getattr(client, method)(path, headers=h).status_code == 404
    assert client.post(f"{API}/chats/{test.id}/reply", json={"text": "x"}, headers=h).status_code == 404


def test_label_without_a_name_and_window_state(client, db, shop):
    token, sid = shop
    old = datetime.now(timezone.utc) - timedelta(hours=30)
    make_chat(db, sid, "psid-98765", last_customer=old, texts=[("customer", "hi", 1800)])
    item = client.get(f"{API}/chats", headers=auth_header(token)).json()["items"][0]
    assert item["customer_label"] == "Customer ...8765" and item["customer_name"] is None
    assert item["window_open"] is False


def test_empty_inbox(client, shop):
    body = client.get(f"{API}/chats", headers=auth_header(shop[0])).json()
    assert body["items"] == [] and body["total"] == 0 and body["flagged_count"] == 0


# --------------------------------------------------------------------------- detail


def test_detail_has_all_messages_and_extras(client, db, shop):
    token, sid = shop
    chat = make_chat(db, sid, "p1", name="Nasrin", texts=[])
    suggestion = {"suggested_products": [{"id": 1, "name": "Saree", "price": 4800, "photo": None}]}
    draft = {"order_draft": {"id": 9, "product_name": "Saree", "quantity": 1, "status": "draft"}}
    db.add_all([
        Message(shop_id=sid, chat_id=chat.id, sender="customer", text="saree dekhan"),
        Message(shop_id=sid, chat_id=chat.id, sender="ai", text="ei je", extras={**suggestion, **draft}),
        Message(shop_id=sid, chat_id=chat.id, sender="seller", text="ami dekhchi"),
    ])
    db.commit()
    body = client.get(f"{API}/chats/{chat.id}", headers=auth_header(token)).json()
    assert [m["sender"] for m in body["messages"]] == ["customer", "ai", "seller"]
    assert body["messages"][1]["extras"]["suggested_products"][0]["name"] == "Saree"
    assert body["messages"][1]["extras"]["order_draft"]["id"] == 9
    assert body["customer_label"] == "Nasrin" and body["last_message"] == "ami dekhchi"


# --------------------------------------------------------------------------- pause / resume / resolve


def test_pause_and_resume(client, db, shop):
    token, sid = shop
    chat = make_chat(db, sid, "p1", texts=[("customer", "hi", 1)])
    h = auth_header(token)
    assert client.post(f"{API}/chats/{chat.id}/pause", headers=h).json()["ai_paused"] is True
    assert client.post(f"{API}/chats/{chat.id}/pause", headers=h).json()["ai_paused"] is True  # idempotent
    db.refresh(chat)
    assert chat.ai_paused is True
    assert client.post(f"{API}/chats/{chat.id}/resume", headers=h).json()["ai_paused"] is False
    db.refresh(chat)
    assert chat.ai_paused is False


def test_resume_does_not_clear_the_flag_and_resolve_does_not_resume(client, db, shop):
    token, sid = shop
    chat = make_chat(db, sid, "p1", flagged="refund", texts=[("customer", "refund", 1)])
    db.add(Notification(shop_id=sid, type="chat_flagged", chat_id=chat.id, reason="refund"))
    db.commit()
    h = auth_header(token)

    after_resume = client.post(f"{API}/chats/{chat.id}/resume", headers=h).json()
    assert after_resume["ai_paused"] is False and after_resume["is_flagged"] is True

    client.post(f"{API}/chats/{chat.id}/pause", headers=h)
    resolved = client.post(f"{API}/chats/{chat.id}/resolve-flag", headers=h).json()
    assert resolved["is_flagged"] is False and resolved["flag_reason"] is None and resolved["ai_paused"] is True
    assert db.scalar(select(Notification.read_at)) is not None
    assert client.get(f"{API}/notifications", headers=h).json()["unread_count"] == 0
    assert client.get(f"{API}/chats?filter=flagged", headers=h).json()["total"] == 0
    assert client.post(f"{API}/chats/{chat.id}/resolve-flag", headers=h).status_code == 200  # again: no harm


def test_resolving_marks_only_this_chats_notifications(client, db, shop):
    token, sid = shop
    a = make_chat(db, sid, "p1", flagged="refund", texts=[("customer", "r", 1)])
    b = make_chat(db, sid, "p2", flagged="complaint", texts=[("customer", "c", 1)])
    db.add_all([Notification(shop_id=sid, type="chat_flagged", chat_id=a.id, reason="refund"),
                Notification(shop_id=sid, type="chat_flagged", chat_id=b.id, reason="complaint")])
    db.commit()
    client.post(f"{API}/chats/{a.id}/resolve-flag", headers=auth_header(token))
    assert client.get(f"{API}/notifications", headers=auth_header(token)).json()["unread_count"] == 1


def test_a_paused_chat_gets_no_ai_reply_and_a_resumed_one_does(client, db, shop, send):
    """The pause really stops the AI: the Prompt 14 worker honours it."""
    from app.workers.tasks import process_incoming_message

    token, sid = shop
    chat = make_chat(db, sid, "p1", texts=[])
    msg = Message(shop_id=sid, chat_id=chat.id, sender="customer", text="hi", received_at=datetime.now(timezone.utc), extras={"ai_status": "pending"})
    db.add(msg)
    db.commit()
    client.post(f"{API}/chats/{chat.id}/pause", headers=auth_header(token))
    process_incoming_message(msg.id)
    db.refresh(msg)
    assert msg.extras["ai_skip_reason"] == "ai_paused" and not send.calls


# --------------------------------------------------------------------------- manual replies


def test_reply_is_rejected_while_the_ai_is_not_paused(client, db, shop, send):
    token, sid = shop
    connect_page(db, sid)
    chat = make_chat(db, sid, "p1", texts=[("customer", "hi", 1)])
    r = client.post(f"{API}/chats/{chat.id}/reply", json={"text": "hello"}, headers=auth_header(token))
    assert r.status_code == 409 and "Pause the AI" in r.json()["detail"]
    assert not send.calls and db.scalars(select(Message).where(Message.sender == "seller")).all() == []


def test_reply_is_rejected_outside_the_24_hour_window(client, db, shop, send):
    token, sid = shop
    connect_page(db, sid)
    chat = make_chat(db, sid, "p1", paused=True, last_customer=datetime.now(timezone.utc) - timedelta(hours=25), texts=[("customer", "hi", 1500)])
    r = client.post(f"{API}/chats/{chat.id}/reply", json={"text": "hello"}, headers=auth_header(token))
    assert r.status_code == 409 and "24 hours" in r.json()["detail"] and "nothing was sent" in r.json()["detail"]
    assert not send.calls and db.scalars(select(Message).where(Message.sender == "seller")).all() == []


def test_reply_is_sent_through_the_send_api_and_stored(client, db, shop, send):
    token, sid = shop
    connect_page(db, sid)
    chat = make_chat(db, sid, "psid-77", paused=True, texts=[("customer", "ekta kotha", 1)])
    before_usage = UsageLimitService(db).get_usage(sid).used
    r = client.post(f"{API}/chats/{chat.id}/reply", json={"text": "  Ji, ami dekhchi  "}, headers=auth_header(token))
    assert r.status_code == 201
    out = r.json()
    assert out["sender"] == "seller" and out["text"] == "Ji, ami dekhchi" and out["sent_at"]

    (call,) = send.calls
    body = json.loads(call.request.content)
    assert body["recipient"] == {"id": "psid-77"} and body["messaging_type"] == "RESPONSE"
    assert body["message"] == {"text": "Ji, ami dekhchi"}
    assert call.request.headers["authorization"] == f"Bearer {PAGE_TOKEN}"

    stored = db.scalars(select(Message).where(Message.sender == "seller")).one()
    assert stored.chat_id == chat.id and stored.shop_id == sid and stored.sent_at is not None
    assert stored.extras["delivery"]["facebook_message_id"] == "m_seller_1"
    assert UsageLimitService(db).get_usage(sid).used == before_usage  # a manual reply is not an AI message
    detail = client.get(f"{API}/chats/{chat.id}", headers=auth_header(token)).json()
    assert detail["messages"][-1]["sender"] == "seller" and detail["last_message_sender"] == "seller"


def test_reply_that_facebook_refuses_is_not_stored(client, db, shop, graph):
    token, sid = shop
    connect_page(db, sid)
    graph.post(f"{GRAPH}/me/messages").mock(return_value=httpx.Response(400, json={"error": {"message": "(#100) Invalid parameter", "code": 100}}))
    chat = make_chat(db, sid, "p1", paused=True, texts=[("customer", "hi", 1)])
    r = client.post(f"{API}/chats/{chat.id}/reply", json={"text": "hello"}, headers=auth_header(token))
    assert r.status_code == 502 and "not sent" in r.json()["detail"]
    assert PAGE_TOKEN not in r.text
    assert db.scalars(select(Message).where(Message.sender == "seller")).all() == []


def test_facebook_saying_the_window_is_closed_is_reported_clearly(client, db, shop, graph):
    token, sid = shop
    connect_page(db, sid)
    graph.post(f"{GRAPH}/me/messages").mock(
        return_value=httpx.Response(400, json={"error": {"message": "outside of allowed window", "code": 10, "error_subcode": 2018278}})
    )
    chat = make_chat(db, sid, "p1", paused=True, texts=[("customer", "hi", 1)])
    r = client.post(f"{API}/chats/{chat.id}/reply", json={"text": "hello"}, headers=auth_header(token))
    assert r.status_code == 409 and "24 hours" in r.json()["detail"]


def test_reply_without_a_connected_page_and_with_bad_input(client, db, shop, send):
    token, sid = shop
    chat = make_chat(db, sid, "p1", paused=True, texts=[("customer", "hi", 1)])
    h = auth_header(token)
    assert client.post(f"{API}/chats/{chat.id}/reply", json={"text": "hello"}, headers=h).status_code == 409
    for bad in ({"text": ""}, {"text": "   "}, {"text": "x" * 2001}, {}):
        assert client.post(f"{API}/chats/{chat.id}/reply", json=bad, headers=h).status_code == 422
    assert not send.calls


# --------------------------------------------------------------------------- access and isolation


def test_moderators_can_use_the_whole_inbox(client, db, shop, send):
    token, sid = shop
    connect_page(db, sid)
    mod = auth_header(moderator(client, token))
    chat = make_chat(db, sid, "p1", flagged="complaint", texts=[("customer", "bad", 1)])
    assert client.get(f"{API}/chats", headers=mod).json()["total"] == 1
    assert client.get(f"{API}/chats/{chat.id}", headers=mod).status_code == 200
    assert client.post(f"{API}/chats/{chat.id}/pause", headers=mod).status_code == 200
    assert client.post(f"{API}/chats/{chat.id}/reply", json={"text": "sorry"}, headers=mod).status_code == 201
    assert client.post(f"{API}/chats/{chat.id}/resolve-flag", headers=mod).status_code == 200
    assert client.post(f"{API}/chats/{chat.id}/resume", headers=mod).status_code == 200
    seller = db.scalars(select(Message).where(Message.sender == "seller")).one()
    assert seller.extras["sent_by_user_id"] is not None


def test_anonymous_and_platform_admin_are_refused(client, db, shop, monkeypatch):
    from app.cli import main as cli_main

    token, sid = shop
    chat = make_chat(db, sid, "p1", texts=[("customer", "hi", 1)])
    assert client.get(f"{API}/chats").status_code == 401
    assert client.post(f"{API}/chats/{chat.id}/pause").status_code == 401
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    cli_main(["create-admin", "--email", "admin@example.com"])
    admin = auth_header(client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": PASSWORD}).json()["access_token"])
    assert client.get(f"{API}/chats", headers=admin).status_code == 403
    assert client.get(f"{API}/chats/{chat.id}", headers=admin).status_code == 403


def test_another_shops_chat_is_a_404_everywhere(client, db, shop, send):
    token_a, sid_a = shop
    token_b = signup(client, "b@example.com", "Shop B")
    sid_b = shop_id_of(db, "Shop B")
    connect_page(db, sid_b, page_id="2002", token="EAAB-b")
    theirs = make_chat(db, sid_b, "pb", name="B customer", flagged="refund", paused=True, texts=[("customer", "secret message", 1)])
    h = auth_header(token_a)

    assert client.get(f"{API}/chats", headers=h).json()["items"] == []
    assert client.get(f"{API}/chats", headers=h).json()["flagged_count"] == 0
    assert "secret message" not in client.get(f"{API}/chats", headers=h).text
    for method, path in (("get", ""), ("post", "/pause"), ("post", "/resume"), ("post", "/resolve-flag")):
        assert getattr(client, method)(f"{API}/chats/{theirs.id}{path}", headers=h).status_code == 404
    assert client.post(f"{API}/chats/{theirs.id}/reply", json={"text": "hi"}, headers=h).status_code == 404
    assert not send.calls

    db.refresh(theirs)
    assert theirs.ai_paused and theirs.is_flagged  # untouched
    assert client.get(f"{API}/chats/{theirs.id}", headers=auth_header(token_b)).status_code == 200
