"""NFR-09 and FR-15 under concurrency: many chats are answered at the same moment, as in the load test. The 24-hour window
and the monthly limit must hold when the worker handles many messages in parallel, not only one at a time."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx
from sqlalchemy import func, select, update

from app.core.crypto import TokenCipher
from app.models import Chat, FacebookPage, Message, Plan, Shop
from app.services.usage import UsageLimitService
from app.workers.tasks import process_incoming_message
from tests.conftest import PASSWORD

API = "/api/v1"
GRAPH = "https://graph.facebook.com/v21.0"


@pytest.fixture
def graph():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


class Sends:
    """A Send API that takes a little time (like Facebook) and records every message."""

    def __init__(self, graph, delay=0.05):
        self.delay, self.recipients = delay, []
        self.lock = threading.Lock()
        graph.post(f"{GRAPH}/me/messages").mock(side_effect=self._answer)
        graph.get(url__regex=rf"{GRAPH}/[^/]+(\?.*)?$").mock(return_value=httpx.Response(200, json={"first_name": "A", "last_name": "B"}))

    def _answer(self, request: httpx.Request) -> httpx.Response:
        time.sleep(self.delay)  # the time between "checked the limit" and "recorded the reply" that a race needs
        with self.lock:
            self.recipients.append(json.loads(request.content)["recipient"]["id"])
        return httpx.Response(200, json={"message_id": f"m_{len(self.recipients)}"})


def make_shop(client, db, name="Shop A", email="a@example.com", limit=None):
    token = client.post(f"{API}/auth/signup", json={"shop_name": name, "owner_name": "O", "email": email, "password": PASSWORD}).json()["access_token"]
    client.post(f"{API}/products", json={"name": "Cotton Panjabi", "description": "d", "price": 1850, "sizes": ["M"], "colours": ["Navy"], "stock_count": 9}, headers={"Authorization": f"Bearer {token}"})
    shop = db.scalar(select(Shop).where(Shop.name == name))
    db.add(FacebookPage(shop_id=shop.id, page_id=f"page-{shop.id}", page_name="P", encrypted_page_token=TokenCipher().encrypt("tok")))
    if limit is not None:
        db.execute(update(Plan).where(Plan.id == shop.plan_id).values(monthly_message_limit=limit))
    db.commit()
    return shop.id


def pending_messages(db, shop_id, n, *, last_customer_hours_ago=0.1, text="Cotton Panjabi er dam koto?"):
    """n customers, one chat each, each with one waiting message."""
    ids = []
    when = datetime.now(timezone.utc) - timedelta(hours=last_customer_hours_ago)
    for i in range(n):
        chat = Chat(shop_id=shop_id, channel="messenger", customer_psid=f"psid-{shop_id}-{i}-{last_customer_hours_ago}", customer_name="X", last_customer_message_at=when)
        db.add(chat)
        db.flush()
        m = Message(shop_id=shop_id, chat_id=chat.id, sender="customer", text=text, received_at=when, extras={"ai_status": "pending"})
        db.add(m)
        db.flush()
        ids.append(m.id)
    db.commit()
    return ids


def run_together(ids):
    """The worker handling every message at the same moment (a start barrier makes the overlap real)."""
    barrier = threading.Barrier(len(ids))

    def work(message_id):
        barrier.wait()
        process_incoming_message(message_id)

    with ThreadPoolExecutor(len(ids)) as pool:
        list(pool.map(work, ids))


def test_the_monthly_limit_holds_when_many_chats_are_answered_at_once(client, db, graph):
    sid = make_shop(client, db, limit=5)
    sends = Sends(graph)
    run_together(pending_messages(db, sid, 24))
    db.expire_all()
    used = UsageLimitService(db).get_usage(sid)
    replied = db.scalar(select(func.count()).select_from(Message).where(Message.shop_id == sid, Message.sender == "ai", Message.sent_at.is_not(None)))
    assert used.used <= used.limit == 5, f"the limit of 5 was passed: {used.used} replies counted"
    assert len(sends.recipients) <= 5 and replied == len(sends.recipients) == used.used  # what was sent, stored and counted agree
    states = [m.extras.get("ai_skip_reason") for m in db.scalars(select(Message).where(Message.shop_id == sid, Message.sender == "customer")) if m.extras.get("ai_status") != "replied"]
    assert states and set(states) == {"limit_reached"}  # the others were kept for the seller, nothing was lost
    assert len(set(sends.recipients)) == len(sends.recipients)  # nobody got two replies


def test_a_limit_of_zero_left_sends_nothing_under_load(client, db, graph):
    sid = make_shop(client, db, limit=3)
    for _ in range(3):
        UsageLimitService(db).record_ai_reply(sid)
    sends = Sends(graph)
    run_together(pending_messages(db, sid, 12))
    assert sends.recipients == [] and UsageLimitService(db).get_usage(sid).used == 3


def test_one_shops_limit_does_not_stop_another_shop_under_load(client, db, graph):
    a = make_shop(client, db, "Shop A", "a@example.com", limit=None)
    b = make_shop(client, db, "Shop B", "b@example.com")
    for _ in range(100):  # shop A is at its (free plan) limit
        UsageLimitService(db).record_ai_reply(a)
    db.execute(update(Plan).where(Plan.id == db.get(Shop, a).plan_id).values(monthly_message_limit=100))
    db.commit()
    sends = Sends(graph)
    ids_a, ids_b = pending_messages(db, a, 6), pending_messages(db, b, 6)
    run_together(ids_a + ids_b)
    db.expire_all()
    assert len(sends.recipients) == 6 and all(r.startswith(f"psid-{b}-") for r in sends.recipients)


def test_the_24_hour_window_holds_under_load(client, db, graph):
    sid = make_shop(client, db)
    sends = Sends(graph)
    fresh = pending_messages(db, sid, 10, last_customer_hours_ago=2)
    old = pending_messages(db, sid, 10, last_customer_hours_ago=25)
    edge = pending_messages(db, sid, 4, last_customer_hours_ago=24.5)
    run_together(fresh + old + edge)
    db.expire_all()
    assert len(sends.recipients) == 10 and all(r.endswith("-2") for r in sends.recipients)  # only the chats written to 2 hours ago
    for mid in old + edge:
        m = db.get(Message, mid)
        assert m.extras["ai_status"] == "skipped" and m.extras["ai_skip_reason"] == "outside_window"
    sent_to_old = [r for r in sends.recipients if r.endswith("-25") or r.endswith("-24.5")]
    assert sent_to_old == []
    assert UsageLimitService(db).get_usage(sid).used == 10  # only what was really sent was counted


def test_suspending_a_shop_stops_the_replies_that_are_still_waiting(client, db, graph):
    sid = make_shop(client, db)
    sends = Sends(graph)
    ids = pending_messages(db, sid, 12)
    db.execute(update(Shop).where(Shop.id == sid).values(status="suspended"))
    db.commit()
    run_together(ids)
    assert sends.recipients == []
    assert {db.get(Message, i).extras["ai_skip_reason"] for i in ids} == {"shop_suspended"}


def test_many_messages_of_one_chat_are_answered_once_each_and_in_order(client, db, graph):
    sid = make_shop(client, db)
    sends = Sends(graph, delay=0.01)
    chat = Chat(shop_id=sid, channel="messenger", customer_psid="same-customer", customer_name="X", last_customer_message_at=datetime.now(timezone.utc))
    db.add(chat)
    db.flush()
    ids = []
    for i in range(8):
        m = Message(shop_id=sid, chat_id=chat.id, sender="customer", text="Cotton Panjabi er dam koto?", received_at=datetime.now(timezone.utc), extras={"ai_status": "pending"})
        db.add(m)
        db.flush()
        ids.append(m.id)
    db.commit()
    with ThreadPoolExecutor(8) as pool:  # the same chat's tasks arrive together (retries, a fast typist)
        list(pool.map(process_incoming_message, ids))
    db.expire_all()
    replies = list(db.scalars(select(Message).where(Message.chat_id == chat.id, Message.sender == "ai").order_by(Message.id)))
    in_reply_to = [m.extras["in_reply_to"] for m in replies]
    assert len(replies) == 8 and in_reply_to == ids  # one reply per message, in the order the customer wrote
    assert len(sends.recipients) == 8
