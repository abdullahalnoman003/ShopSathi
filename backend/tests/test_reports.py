from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.cli import main as cli_main
from app.models import Chat, HandoverEvent, Message, Order, Shop
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"
DHAKA = ZoneInfo("Asia/Dhaka")


def dhaka(y, m, d, hh=0, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=DHAKA)


def signup(client, email="a@example.com", shop="Shop A"):
    return client.post(f"{API}/auth/signup", json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD}).json()["access_token"]


def chat(db, sid, channel="messenger", psid="p"):
    c = Chat(shop_id=sid, channel=channel, customer_psid=psid if channel == "messenger" else None)
    db.add(c)
    db.flush()
    return c


def ai(db, c, at, sent=True):
    db.add(Message(shop_id=c.shop_id, chat_id=c.id, sender="ai", text="x", created_at=at, sent_at=at if sent else None))


def order(db, sid, created, confirmed=None, test=False, status=None):
    db.add(Order(shop_id=sid, product_name="P", quantity=1, unit_price=10, customer_name="N", customer_phone="01700000001", customer_address="A",
                 status=status or ("confirmed" if confirmed else "draft"), is_test=test, created_at=created, confirmed_at=confirmed))


def get(client, token, frm, to):
    return client.get(f"{API}/reports/summary?from={frm}&to={to}", headers=auth_header(token))


@pytest.fixture
def shop(client, db):
    token = signup(client)
    return token, db.scalar(select(Shop.id))


def numbers(r):
    b = r.json()
    return (b["messages_handled_by_ai"], b["chats_handed_to_humans"], b["orders_drafted"], b["orders_confirmed"])


def test_every_metric_at_the_range_boundaries(client, db, shop):
    token, sid = shop
    c = chat(db, sid)
    # range: 2026-03-10 .. 2026-03-12 in Dhaka  = [03-10 00:00, 03-13 00:00)
    for at, expected_in in [
        (dhaka(2026, 3, 9, 23, 59, 59), False), (dhaka(2026, 3, 10, 0, 0, 0), True),
        (dhaka(2026, 3, 12, 23, 59, 59), True), (dhaka(2026, 3, 13, 0, 0, 0), False),
    ]:
        ai(db, c, at)
        db.add(HandoverEvent(shop_id=sid, chat_id=chat(db, sid, psid=f"h{at}").id, reason="refund", created_at=at))
        order(db, sid, created=at, confirmed=at)
    db.commit()
    assert numbers(get(client, token, "2026-03-10", "2026-03-12")) == (2, 2, 2, 2)
    assert numbers(get(client, token, "2026-03-10", "2026-03-10")) == (1, 1, 1, 1)  # a single day
    assert numbers(get(client, token, "2026-03-13", "2026-03-13")) == (1, 1, 1, 1)  # 00:00:00 belongs to the new day
    assert numbers(get(client, token, "2026-03-14", "2026-03-20")) == (0, 0, 0, 0)
    assert numbers(get(client, token, "2026-03-09", "2026-03-13")) == (4, 4, 4, 4)


def test_days_are_dhaka_days_not_utc_days(client, db, shop):
    token, sid = shop
    c = chat(db, sid)
    at = datetime(2026, 3, 10, 19, 0, tzinfo=timezone.utc)  # 2026-03-11 01:00 in Dhaka
    ai(db, c, at)
    db.commit()
    assert numbers(get(client, token, "2026-03-11", "2026-03-11"))[0] == 1
    assert numbers(get(client, token, "2026-03-10", "2026-03-10"))[0] == 0


def test_messages_handled_counts_only_ai_messages_that_were_sent(client, db, shop):
    token, sid = shop
    c = chat(db, sid)
    at = dhaka(2026, 3, 10, 12)
    ai(db, c, at)
    ai(db, c, at)
    ai(db, c, at, sent=False)  # written but never delivered
    db.add(Message(shop_id=sid, chat_id=c.id, sender="customer", text="q", created_at=at, sent_at=at))
    db.add(Message(shop_id=sid, chat_id=c.id, sender="seller", text="s", created_at=at, sent_at=at))
    db.commit()
    assert numbers(get(client, token, "2026-03-10", "2026-03-10"))[0] == 2


def test_chats_handed_over_are_counted_once_per_chat(client, db, shop):
    token, sid = shop
    c = chat(db, sid)
    for h in (9, 11, 15):  # the same chat handed over three times
        db.add(HandoverEvent(shop_id=sid, chat_id=c.id, reason="complaint", created_at=dhaka(2026, 3, 10, h)))
    other = chat(db, sid, psid="q")
    db.add(HandoverEvent(shop_id=sid, chat_id=other.id, reason="refund", created_at=dhaka(2026, 3, 10, 10)))
    db.commit()
    assert numbers(get(client, token, "2026-03-10", "2026-03-10"))[1] == 2


def test_orders_drafted_and_confirmed_are_counted_by_their_own_dates(client, db, shop):
    token, sid = shop
    order(db, sid, created=dhaka(2026, 3, 9, 10), confirmed=dhaka(2026, 3, 10, 10))  # drafted before, confirmed in range
    order(db, sid, created=dhaka(2026, 3, 10, 10), confirmed=dhaka(2026, 3, 11, 10))  # drafted in range, confirmed after
    order(db, sid, created=dhaka(2026, 3, 10, 11))  # still a draft
    order(db, sid, created=dhaka(2026, 3, 10, 12), status="cancelled")  # drafted, then cancelled: still drafted
    db.commit()
    assert numbers(get(client, token, "2026-03-10", "2026-03-10")) == (0, 0, 3, 1)


def test_test_chat_data_is_excluded_everywhere(client, db, shop):
    token, sid = shop
    t = chat(db, sid, channel="test")
    at = dhaka(2026, 3, 10, 12)
    ai(db, t, at)
    db.add(HandoverEvent(shop_id=sid, chat_id=t.id, reason="complaint", created_at=at))
    order(db, sid, created=at, confirmed=at, test=True)
    db.commit()
    assert numbers(get(client, token, "2026-03-10", "2026-03-10")) == (0, 0, 0, 0)


def test_other_shops_are_excluded(client, db, shop):
    token, sid = shop
    other_token = signup(client, "b@example.com", "Shop B")
    other = db.scalar(select(Shop.id).where(Shop.name == "Shop B"))
    at = dhaka(2026, 3, 10, 12)
    c = chat(db, other)
    ai(db, c, at)
    db.add(HandoverEvent(shop_id=other, chat_id=c.id, reason="refund", created_at=at))
    order(db, other, created=at, confirmed=at)
    db.commit()
    assert numbers(get(client, token, "2026-03-10", "2026-03-10")) == (0, 0, 0, 0)
    assert numbers(get(client, other_token, "2026-03-10", "2026-03-10")) == (1, 1, 1, 1)


def test_range_validation(client, shop, monkeypatch):
    token = shop[0]
    assert get(client, token, "2026-03-12", "2026-03-10").status_code == 422
    assert get(client, token, "2026-03-10", "2026-03-10").status_code == 200
    assert get(client, token, "2025-03-09", "2026-03-10").status_code == 422  # 367 days
    assert get(client, token, "2025-03-10", "2026-03-10").status_code == 200  # 366 days: the maximum
    assert get(client, token, "nope", "2026-03-10").status_code == 422
    assert client.get(f"{API}/reports/summary", headers=auth_header(token)).status_code == 422
    from app.core.config import get_settings

    monkeypatch.setenv("REPORT_MAX_RANGE_DAYS", "7")
    get_settings.cache_clear()
    try:
        assert get(client, token, "2026-03-01", "2026-03-07").status_code == 200
        r = get(client, token, "2026-03-01", "2026-03-08")
        assert r.status_code == 422 and "at most 7 days" in r.json()["detail"]
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_owner_only(client, db, shop, monkeypatch):
    token, sid = shop
    client.post(f"{API}/shop/staff", json={"email": "mod@example.com", "full_name": "Mod", "password": PASSWORD}, headers=auth_header(token))
    mod = client.post(f"{API}/auth/login", json={"email": "mod@example.com", "password": PASSWORD}).json()["access_token"]
    assert get(client, mod, "2026-03-10", "2026-03-10").status_code == 403
    assert client.get(f"{API}/reports/summary?from=2026-03-10&to=2026-03-10").status_code == 401
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    cli_main(["create-admin", "--email", "admin@example.com"])
    admin = client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": PASSWORD}).json()["access_token"]
    assert get(client, admin, "2026-03-10", "2026-03-10").status_code == 403
    assert get(client, token, "2026-03-10", "2026-03-10").status_code == 200


def test_demo_history_seed_feeds_the_report_and_is_idempotent(db, client, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "demo-password-1")
    assert cli_main(["seed"]) == 0
    chats = db.scalars(select(Chat).where(Chat.customer_psid.like("hist-%"))).all()
    assert len(chats) == 32 and all(c.channel == "messenger" for c in chats)
    orders = db.scalars(select(Order).where(Order.customer_phone.like("0170000%"))).all()
    assert {o.status for o in orders} == {"draft", "confirmed", "cancelled"} and all(not o.is_test for o in orders)
    assert cli_main(["seed"]) == 0
    assert len(db.scalars(select(Chat).where(Chat.customer_psid.like("hist-%"))).all()) == 32
    assert len(db.scalars(select(Order).where(Order.customer_phone.like("0170000%"))).all()) == len(orders)

    token = client.post(f"{API}/auth/login", json={"email": "rina.demo@example.com", "password": "demo-password-1"}).json()["access_token"]
    today = datetime.now(DHAKA).date()
    r = get(client, token, (today - timedelta(days=60)).isoformat(), today.isoformat())
    assert r.status_code == 200
    n = numbers(r)
    assert n[0] > 20 and n[1] >= 6 and n[2] >= 11 and 0 < n[3] <= n[2]  # nothing is in the future
