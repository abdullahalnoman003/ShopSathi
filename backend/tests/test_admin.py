import json
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from sqlalchemy import select

from app.cli import main as cli_main
from app.core.crypto import TokenCipher
from app.core.redis import get_redis
from app.integrations.facebook.webhook import sign
from app.models import AdminAction, AiUsageLog, Chat, FacebookPage, Message, Order, Plan, Product, Shop, SimulatedPayment, User
from app.services.usage import UsageLimitService
from app.workers.tasks import process_incoming_message
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"
DHAKA = ZoneInfo("Asia/Dhaka")
GRAPH = "https://graph.facebook.com/v21.0"


def signup(client, email="a@example.com", shop="Shop A"):
    r = client.post(f"{API}/auth/signup", json={"shop_name": shop, "owner_name": "Owner " + shop, "email": email, "password": PASSWORD})
    return r.json()["access_token"]


@pytest.fixture
def admin(client, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    cli_main(["create-admin", "--email", "admin@example.com"])
    token = client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": PASSWORD}).json()["access_token"]
    return auth_header(token)


def shop_id(db, name):
    return db.scalar(select(Shop.id).where(Shop.name == name))


ADMIN_ENDPOINTS = [
    ("get", "/admin/shops"), ("get", "/admin/shops/1"), ("post", "/admin/shops/1/suspend"), ("post", "/admin/shops/1/reactivate"),
    ("post", "/admin/shops/1/plan"), ("get", "/admin/plans"), ("put", "/admin/plans/free"),
    ("get", "/admin/ai-usage?from=2026-03-01&to=2026-03-02"), ("get", "/admin/system-health"),
]


def call(client, method, path, headers=None):
    body = {"plan_code": "pro"} if path.endswith("/plan") and method == "post" else {"monthly_message_limit": 5, "monthly_price": 0} if method == "put" else None
    return getattr(client, method)(f"{API}{path}", headers=headers or {}, **({"json": body} if body else {}))


# ----------------------------------------------------------------------- access


def test_only_the_platform_admin_may_use_the_admin_endpoints(client, db, admin):
    owner = signup(client)
    client.post(f"{API}/shop/staff", json={"email": "mod@example.com", "full_name": "Mod", "password": PASSWORD}, headers=auth_header(owner))
    mod = client.post(f"{API}/auth/login", json={"email": "mod@example.com", "password": PASSWORD}).json()["access_token"]
    for method, path in ADMIN_ENDPOINTS:
        assert call(client, method, path).status_code == 401, path
        assert call(client, method, path, auth_header(owner)).status_code == 403, path
        assert call(client, method, path, auth_header(mod)).status_code == 403, path
        assert call(client, method, path, admin).status_code != 403, path


def test_the_admin_cannot_use_shop_endpoints_or_read_chats(client, db, admin):
    signup(client)
    sid = shop_id(db, "Shop A")
    db.add(Chat(shop_id=sid, channel="messenger", customer_psid="p"))
    db.commit()
    for path in ("/chats", "/orders", "/products", "/reports/summary?from=2026-03-01&to=2026-03-02", "/notifications"):
        assert client.get(f"{API}{path}", headers=admin).status_code == 403, path


# ----------------------------------------------------------------------- shops


def test_shop_list_has_everything_the_admin_needs(client, db, admin):
    signup(client, "a@example.com", "Rina Fashion")
    signup(client, "b@example.com", "Karim Gadgets")
    a = shop_id(db, "Rina Fashion")
    db.add(FacebookPage(shop_id=a, page_id="1001", page_name="Rina Page", encrypted_page_token=TokenCipher().encrypt("tok")))
    db.commit()
    for _ in range(3):
        UsageLimitService(db).record_ai_reply(a)
    body = client.get(f"{API}/admin/shops", headers=admin).json()
    assert body["total"] == 2
    first, second = body["items"]  # newest first
    assert first["name"] == "Karim Gadgets" and first["connected_page_name"] is None and first["ai_messages_used"] == 0
    assert second["name"] == "Rina Fashion" and second["owner_email"] == "a@example.com" and second["owner_name"] == "Owner Rina Fashion"
    assert second["plan"] == {"code": "free", "name": "Free"} and second["status"] == "active" and second["created_at"]
    assert second["connected_page_name"] == "Rina Page"
    assert second["ai_messages_used"] == 3 and second["ai_messages_limit"] == db.scalar(select(Plan.monthly_message_limit).where(Plan.code == "free"))
    assert "password" not in json.dumps(body) and "token" not in json.dumps(body).lower()


def test_search_by_shop_name_or_owner_email_and_pagination(client, db, admin):
    for i, (email, name) in enumerate([("rina@example.com", "Rina Fashion"), ("karim@gadgets.example", "Karim Gadgets"), ("x@example.com", "100% Cotton_House")]):
        signup(client, email, name)
    h = admin

    def names(q):
        return [s["name"] for s in client.get(f"{API}/admin/shops", params={"q": q}, headers=h).json()["items"]]

    assert names("rina") == ["Rina Fashion"] and names("GADGETS") == ["Karim Gadgets"]  # the owner e-mail matches too
    assert names("karim@") == ["Karim Gadgets"]
    assert names("100%") == ["100% Cotton_House"] and names("%") == ["100% Cotton_House"]  # wildcards are literal
    assert names("nothing") == []
    p1 = client.get(f"{API}/admin/shops?page=1&page_size=2", headers=h).json()
    p2 = client.get(f"{API}/admin/shops?page=2&page_size=2", headers=h).json()
    assert p1["total"] == 3 and len(p1["items"]) == 2 and len(p2["items"]) == 1
    assert client.get(f"{API}/admin/shops?page_size=500", headers=h).status_code == 422


def test_shop_detail_adds_counts_without_test_data(client, db, admin):
    token = signup(client)
    sid = shop_id(db, "Shop A")
    for i in range(2):
        db.add(Product(shop_id=sid, name=f"P{i}", price=10, stock_count=1))
    db.add(Chat(shop_id=sid, channel="messenger", customer_psid="a"))
    db.add(Chat(shop_id=sid, channel="messenger", customer_psid="b"))
    db.add(Chat(shop_id=sid, channel="test"))
    for test in (False, False, True):
        db.add(Order(shop_id=sid, product_name="P", quantity=1, unit_price=10, customer_name="N", customer_phone="01700000001", customer_address="A", is_test=test))
    db.commit()
    body = client.get(f"{API}/admin/shops/{sid}", headers=admin).json()
    assert (body["product_count"], body["chat_count"], body["order_count"]) == (2, 2, 2)
    assert client.get(f"{API}/admin/shops/9999", headers=admin).status_code == 404


# ----------------------------------------------------------------------- suspend / reactivate


def test_suspend_blocks_the_shops_users_and_reactivate_restores_them(client, db, admin):
    owner = signup(client, "owner@example.com", "Shop A")
    sid = shop_id(db, "Shop A")
    client.post(f"{API}/shop/staff", json={"email": "mod@example.com", "full_name": "Mod", "password": PASSWORD}, headers=auth_header(owner))
    mod_token = client.post(f"{API}/auth/login", json={"email": "mod@example.com", "password": PASSWORD}).json()["access_token"]
    other = signup(client, "other@example.com", "Shop B")

    r = client.post(f"{API}/admin/shops/{sid}/suspend", headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    for email in ("owner@example.com", "mod@example.com"):
        login = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
        assert login.status_code == 403 and "suspended" in login.json()["detail"].lower()
    assert client.get(f"{API}/products", headers=auth_header(owner)).status_code == 403  # a token from before is refused too
    assert client.get(f"{API}/chats", headers=auth_header(mod_token)).status_code == 403
    assert client.get(f"{API}/products", headers=auth_header(other)).status_code == 200  # other shops are not affected

    r = client.post(f"{API}/admin/shops/{sid}/reactivate", headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert client.post(f"{API}/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).status_code == 200
    assert client.get(f"{API}/products", headers=auth_header(owner)).status_code == 200


def test_a_suspended_shops_messenger_customers_get_no_ai_reply_until_it_is_reactivated(client, db, admin):
    signup(client, "owner@example.com", "Shop A")
    sid = shop_id(db, "Shop A")
    db.add(FacebookPage(shop_id=sid, page_id="1001", page_name="P", encrypted_page_token=TokenCipher().encrypt("tok")))
    chat = Chat(shop_id=sid, channel="messenger", customer_psid="777", last_customer_message_at=datetime.now(timezone.utc))
    db.add(chat)
    db.flush()

    def pending(text):
        m = Message(shop_id=sid, chat_id=chat.id, sender="customer", text=text, received_at=datetime.now(timezone.utc), extras={"ai_status": "pending"})
        db.add(m)
        db.commit()
        return m

    client.post(f"{API}/admin/shops/{sid}/suspend", headers=admin)
    with respx.mock(assert_all_called=False) as graph:
        send = graph.post(f"{GRAPH}/me/messages").mock(return_value=httpx.Response(200, json={"message_id": "m_1"}))
        graph.get(url__regex=rf"{GRAPH}/\d+(\?.*)?$").mock(return_value=httpx.Response(200, json={"first_name": "A", "last_name": "B"}))
        first = pending("price koto?")
        process_incoming_message(first.id)
        db.refresh(first)
        assert first.extras["ai_status"] == "skipped" and first.extras["ai_skip_reason"] == "shop_suspended"
        assert not send.calls and db.scalars(select(Message).where(Message.sender == "ai")).all() == []

        client.post(f"{API}/admin/shops/{sid}/reactivate", headers=admin)
        second = pending("delivery charge koto?")
        process_incoming_message(second.id)
        db.refresh(second)
        assert second.extras["ai_status"] == "replied" and len(send.calls) == 1
        assert json.loads(send.calls[0].request.content)["recipient"] == {"id": "777"}


def test_suspending_twice_is_harmless_and_logged_once(client, db, admin):
    signup(client)
    sid = shop_id(db, "Shop A")
    for _ in range(2):
        assert client.post(f"{API}/admin/shops/{sid}/suspend", headers=admin).json()["status"] == "suspended"
    assert client.post(f"{API}/admin/shops/{sid}/reactivate", headers=admin).json()["status"] == "active"
    assert client.post(f"{API}/admin/shops/{sid}/reactivate", headers=admin).json()["status"] == "active"
    assert [a.action for a in db.scalars(select(AdminAction).order_by(AdminAction.id))] == ["suspend", "reactivate"]
    assert client.post(f"{API}/admin/shops/9999/suspend", headers=admin).status_code == 404


# ----------------------------------------------------------------------- plan change and plan editing


def test_admin_plan_change_updates_the_limit_without_a_payment_record(client, db, admin):
    signup(client)
    sid = shop_id(db, "Shop A")
    free = db.scalar(select(Plan.monthly_message_limit).where(Plan.code == "free"))
    pro = db.scalar(select(Plan.monthly_message_limit).where(Plan.code == "pro"))
    assert UsageLimitService(db).get_usage(sid).limit == free
    r = client.post(f"{API}/admin/shops/{sid}/plan", json={"plan_code": "pro"}, headers=admin)
    assert r.status_code == 200 and r.json()["plan"]["code"] == "pro" and r.json()["ai_messages_limit"] == pro
    db.expire_all()
    assert UsageLimitService(db).get_usage(sid).limit == pro
    assert db.scalars(select(SimulatedPayment).where(SimulatedPayment.shop_id == sid)).all() == []  # a paid plan, but no payment
    assert client.post(f"{API}/admin/shops/{sid}/plan", json={"plan_code": "gold"}, headers=admin).status_code == 404
    assert client.post(f"{API}/admin/shops/{sid}/plan", json={}, headers=admin).status_code == 422
    # the owner sees the new plan
    owner = client.post(f"{API}/auth/login", json={"email": "a@example.com", "password": PASSWORD}).json()["access_token"]
    assert client.get(f"{API}/shop/plan", headers=auth_header(owner)).json()["plan"]["code"] == "pro"


def test_editing_a_plan_changes_the_limit_for_every_shop_on_it(client, db, admin):
    signup(client, "a@example.com", "Shop A")
    signup(client, "b@example.com", "Shop B")
    a, b = shop_id(db, "Shop A"), shop_id(db, "Shop B")
    for _ in range(3):
        UsageLimitService(db).record_ai_reply(a)
    assert UsageLimitService(db).can_send_ai_reply(a)
    r = client.put(f"{API}/admin/plans/free", json={"monthly_message_limit": 3, "monthly_price": 0}, headers=admin)
    assert r.status_code == 200 and r.json() == {"code": "free", "name": "Free", "monthly_message_limit": 3, "monthly_price": 0}
    db.expire_all()
    assert UsageLimitService(db).get_usage(a).limit == 3 and UsageLimitService(db).get_usage(b).limit == 3
    assert not UsageLimitService(db).can_send_ai_reply(a) and UsageLimitService(db).can_send_ai_reply(b)  # a is at its new limit
    plans = {p["code"]: p for p in client.get(f"{API}/admin/plans", headers=admin).json()}
    assert set(plans) == {"free", "basic", "pro"} and plans["free"]["monthly_message_limit"] == 3
    assert client.put(f"{API}/admin/plans/basic", json={"monthly_message_limit": 500, "monthly_price": 399}, headers=admin).json()["monthly_price"] == 399
    for bad in ({"monthly_message_limit": 0, "monthly_price": 0}, {"monthly_message_limit": 5, "monthly_price": -1}, {"monthly_message_limit": "x", "monthly_price": 0}, {"monthly_price": 0}):
        assert client.put(f"{API}/admin/plans/free", json=bad, headers=admin).status_code == 422
    assert client.put(f"{API}/admin/plans/gold", json={"monthly_message_limit": 5, "monthly_price": 0}, headers=admin).status_code == 404
    # the public plan list (signup page) shows the new values
    assert {p["code"]: p["monthly_message_limit"] for p in client.get(f"{API}/plans").json()}["free"] == 3


def test_every_shop_change_is_logged_with_the_admin_and_the_time(client, db, admin):
    signup(client)
    sid = shop_id(db, "Shop A")
    client.post(f"{API}/admin/shops/{sid}/suspend", headers=admin)
    client.post(f"{API}/admin/shops/{sid}/reactivate", headers=admin)
    client.post(f"{API}/admin/shops/{sid}/plan", json={"plan_code": "basic"}, headers=admin)
    client.put(f"{API}/admin/plans/pro", json={"monthly_message_limit": 9000, "monthly_price": 999}, headers=admin)
    client.get(f"{API}/admin/shops", headers=admin)  # reads are not logged
    admin_id = db.scalar(select(User.id).where(User.email == "admin@example.com"))
    actions = list(db.scalars(select(AdminAction).order_by(AdminAction.id)))
    assert [a.action for a in actions] == ["suspend", "reactivate", "change_plan", "update_plan"]
    assert all(a.admin_user_id == admin_id and a.created_at is not None for a in actions)
    assert [a.shop_id for a in actions] == [sid, sid, sid, None]
    assert actions[2].detail == {"from": "free", "to": "basic"} and actions[3].detail["after"] == {"monthly_message_limit": 9000, "monthly_price": 999}


# ----------------------------------------------------------------------- AI usage and cost


def log(db, sid, op, tin, tout, cost, at, model="gpt-4o-mini"):
    db.add(AiUsageLog(shop_id=sid, operation=op, provider="openai", model=model, input_tokens=tin, output_tokens=tout, estimated_cost=Decimal(cost), created_at=at))


def test_ai_cost_totals_match_the_logs(client, db, admin):
    signup(client, "a@example.com", "Shop A")
    signup(client, "b@example.com", "Shop B")
    signup(client, "c@example.com", "Shop C")
    a, b, c = (shop_id(db, n) for n in ("Shop A", "Shop B", "Shop C"))
    d = lambda y, m, dd, hh=12, mm=0: datetime(y, m, dd, hh, mm, tzinfo=DHAKA)
    log(db, a, "chat_reply", 1000, 200, "0.000270", d(2026, 3, 10))
    log(db, a, "chat_reply", 500, 100, "0.000135", d(2026, 3, 11))
    log(db, a, "embedding", 300, 0, "0.000006", d(2026, 3, 11))
    log(db, b, "weekly_insights", 2000, 400, "0.000540", d(2026, 3, 12))
    log(db, b, "chat_reply", 100, 10, "0.000021", d(2026, 3, 10, 0, 0))  # first minute of the range: included
    log(db, a, "chat_reply", 9999, 999, "9.000000", d(2026, 3, 9, 23, 59))  # before the range
    log(db, c, "chat_reply", 9999, 999, "9.000000", d(2026, 3, 13, 0, 0))  # after the range
    db.commit()
    body = client.get(f"{API}/admin/ai-usage?from=2026-03-10&to=2026-03-12", headers=admin).json()
    shops = {s["shop_name"]: s for s in body["shops"]}
    assert set(shops) == {"Shop A", "Shop B"}  # Shop C has no usage in the range
    assert shops["Shop A"]["calls"] == 3 and shops["Shop A"]["input_tokens"] == 1800 and shops["Shop A"]["output_tokens"] == 300
    assert shops["Shop A"]["estimated_cost"] == pytest.approx(0.000411)
    assert shops["Shop A"]["by_operation"]["chat_reply"] == {"calls": 2, "input_tokens": 1500, "output_tokens": 300, "estimated_cost": pytest.approx(0.000405)}
    assert shops["Shop A"]["by_operation"]["embedding"]["input_tokens"] == 300
    assert shops["Shop B"]["estimated_cost"] == pytest.approx(0.000561)
    assert [s["shop_name"] for s in body["shops"]] == ["Shop B", "Shop A"]  # most expensive first
    assert body["total"] == {"calls": 5, "input_tokens": 3900, "output_tokens": 710, "estimated_cost": pytest.approx(0.000972)}
    assert body["total"]["estimated_cost"] == pytest.approx(sum(s["estimated_cost"] for s in body["shops"]))
    assert body["by_operation"]["chat_reply"]["calls"] == 3 and body["by_operation"]["weekly_insights"]["calls"] == 1
    assert body["from_date"] == "2026-03-10" and body["to_date"] == "2026-03-12"


def test_ai_usage_validation_and_empty_range(client, admin, monkeypatch):
    empty = client.get(f"{API}/admin/ai-usage?from=2026-03-10&to=2026-03-12", headers=admin).json()
    assert empty["shops"] == [] and empty["total"]["calls"] == 0 and empty["total"]["estimated_cost"] == 0
    assert client.get(f"{API}/admin/ai-usage?from=2026-03-12&to=2026-03-10", headers=admin).status_code == 422
    assert client.get(f"{API}/admin/ai-usage?from=2020-01-01&to=2026-03-10", headers=admin).status_code == 422
    assert client.get(f"{API}/admin/ai-usage?from=2026-03-10", headers=admin).status_code == 422


# ----------------------------------------------------------------------- system health


def test_system_health_reports_every_component(client, admin):
    get_redis().delete("celery")
    get_redis().rpush("celery", "job1", "job2", "job3")
    body = client.get(f"{API}/admin/system-health", headers=admin).json()
    assert body["status"] == "ok"
    for part in ("api", "database", "redis", "celery_worker"):
        assert body[part]["status"] == "ok", part
    assert body["celery_queue_length"] == 3
    get_redis().delete("celery")


def test_a_missing_worker_is_reported_as_degraded(client, admin, monkeypatch):
    from app.workers import celery_app as module

    monkeypatch.setattr(module.celery_app.conf, "task_always_eager", False)

    class Dead:
        def get(self, timeout):
            raise TimeoutError("nobody answered")

    monkeypatch.setattr(module.ping, "apply_async", lambda *a, **k: Dead())
    body = client.get(f"{API}/admin/system-health", headers=admin).json()
    assert body["status"] == "degraded" and body["celery_worker"]["status"] == "error" and "worker" in body["celery_worker"]["detail"]
    assert body["database"]["status"] == body["redis"]["status"] == "ok"

    class Alive:
        def get(self, timeout):
            return "pong"

    monkeypatch.setattr(module.ping, "apply_async", lambda *a, **k: Alive())
    assert client.get(f"{API}/admin/system-health", headers=admin).json()["status"] == "ok"
