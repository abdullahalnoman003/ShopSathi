"""Shop deletion and the privacy rules (section 5.3, FR-02, NFR-04): what deleting a shop removes, that no shop can
reach another shop's data through any endpoint, and that personal data and secrets stay out of the logs."""

import json
import logging
from datetime import date, datetime, timezone

import httpx
import pytest
import respx
from fastapi.routing import APIRoute
from sqlalchemy import func, select, text

from app.core.crypto import TokenCipher
from app.core.database import Base
from app.core.log_masking import mask
from app.core.redis import get_redis
from app.integrations.facebook.webhook import sign
from app.main import app
from app.models import AdminAction, AiUsageLog, Chat, EmbeddingChunk, FacebookPage, HandoverEvent, Message, Notification, Order, Product, Shop, User, WeeklyInsight
from app.services.storage import StorageService
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"
GRAPH = "https://graph.facebook.com/v21.0"
PHONES = {"A": "01799990001", "B": "01799990002"}
WEEKS = {"A": date(2026, 3, 2), "B": date(2026, 3, 9)}  # each shop has an insight for its own week
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def signup(client, email, shop, plan="free"):
    r = client.post(f"{API}/auth/signup", json={"shop_name": shop, "owner_name": "Owner " + shop, "email": email, "password": PASSWORD, "plan_code": plan, "simulated_payment_confirmed": plan != "free"})
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def build_shop(client, db, tag: str, email: str):
    """A shop with data in every table that holds shop data. `tag` makes its customer details recognisable."""
    shop_name = f"Shop {tag}"
    token = signup(client, email, shop_name, plan="basic")
    h = auth_header(token)
    sid = db.scalar(select(Shop.id).where(Shop.name == shop_name))
    mod = client.post(f"{API}/shop/staff", json={"email": f"mod-{email}", "full_name": "Mod", "password": PASSWORD}, headers=h)
    assert mod.status_code == 201
    mod_token = client.post(f"{API}/auth/login", json={"email": f"mod-{email}", "password": PASSWORD}).json()["access_token"]
    product = client.post(f"{API}/products", json={"name": f"Saree {tag}", "description": "d", "price": 100, "sizes": ["M"], "colours": ["Red"], "stock_count": 5}, headers=h).json()
    photo = client.post(f"{API}/products/{product['id']}/photos", files=[("files", ("a.png", PNG, "image/png"))], headers=h)
    assert photo.status_code == 200, photo.text
    assert client.put(f"{API}/shop/policy", json={"delivery_time": "1 day", "return_rules": "3 days", "payment_options": "COD", "delivery_areas": [{"area_name": "Dhaka", "charge": 60}]}, headers=h).status_code == 200
    db.add(FacebookPage(shop_id=sid, page_id=f"page-{tag}", page_name=f"Page {tag}", encrypted_page_token=TokenCipher().encrypt(f"EAAB-secret-token-{tag}")))
    chat = Chat(shop_id=sid, channel="messenger", customer_psid=f"psid-{tag}", customer_name=f"Customer {tag}", is_flagged=True, flag_reason="refund", last_customer_message_at=datetime.now(timezone.utc))
    test_chat = Chat(shop_id=sid, channel="test", customer_name="Test customer")
    db.add_all([chat, test_chat])
    db.flush()
    db.add_all([
        Message(shop_id=sid, chat_id=chat.id, sender="customer", text=f"my phone 017{tag}0000 {tag}-secret-question", extras={"ai_status": "replied"}),
        Message(shop_id=sid, chat_id=chat.id, sender="ai", text="reply"),
        Message(shop_id=sid, chat_id=test_chat.id, sender="customer", text="test message"),
        HandoverEvent(shop_id=sid, chat_id=chat.id, reason="refund"),
        Notification(shop_id=sid, chat_id=chat.id, reason="refund"),
        Order(shop_id=sid, chat_id=chat.id, product_id=product["id"], product_name=f"Saree {tag}", quantity=1, unit_price=100, customer_name=f"Customer {tag}", customer_phone=PHONES[tag], customer_address=f"{tag} Road, secret address"),
        AiUsageLog(shop_id=sid, operation="chat_reply", provider="p", model="m", input_tokens=10, output_tokens=5),
        WeeklyInsight(shop_id=sid, week_start=WEEKS[tag], top_questions=[{"question": "q", "count": 1}], missing_products=[]),
    ])
    db.commit()
    client.post(f"{API}/auth/password-reset/request", json={"email": email})
    r = get_redis()
    r.rpush(f"chatmem:{sid}:{chat.id}", "turn")
    r.set(f"chatlock:{sid}:{chat.id}", 1, ex=60)
    r.set(f"ingest:{sid}:psid-{tag}", 1, ex=60)
    r.set(f"fb:pages:{sid}", "pending", ex=60)
    r.set(f"fb:name_tried:{chat.id}", 1, ex=60)
    return dict(token=token, mod_token=mod_token, shop_id=sid, name=shop_name, product=product["id"], chat=chat.id, test_chat=test_chat.id, tag=tag, email=email)


def snapshot(db) -> dict[str, int]:
    """Row counts of every table that belongs to a shop (directly or through users/chats)."""
    db.expire_all()
    return {t.name: db.scalar(select(func.count()).select_from(t)) for t in Base.metadata.sorted_tables if t.name not in ("plans", "shops", "alembic_version")}


def redis_keys(sid: int) -> list[str]:
    r = get_redis()
    keys: list[str] = []
    for p in ("chatmem", "chatlock", "chatmsgs", "ingest"):
        keys += [k.decode() for k in r.scan_iter(match=f"{p}:{sid}:*")]
    keys += [k.decode() for k in r.scan_iter(match=f"fb:pages:{sid}")]
    return keys


@pytest.fixture
def graph():
    with respx.mock(assert_all_called=False) as mock:
        yield mock


def delete(client, user, password=PASSWORD, name=None):
    return client.request("DELETE", f"{API}/shop", json={"password": password, "shop_name": user["name"] if name is None else name}, headers=auth_header(user["token"]))


# ============================================================================== deleting a shop


def test_deleting_a_shop_removes_all_its_rows_files_and_keys_and_leaves_the_other_shop_alone(client, db, graph):
    a = build_shop(client, db, "A", "a@example.com")
    b = build_shop(client, db, "B", "b@example.com")
    unsub = graph.delete(f"{GRAPH}/page-A/subscribed_apps").mock(return_value=httpx.Response(200, json={"success": True}))
    storage = StorageService()
    a_folder, b_folder = storage.root / "shops" / str(a["shop_id"]), storage.root / "shops" / str(b["shop_id"])
    assert any(a_folder.rglob("*.png")) and any(b_folder.rglob("*.png"))
    assert redis_keys(a["shop_id"]) and redis_keys(b["shop_id"])
    user_ids_a = list(db.scalars(select(User.id).where(User.shop_id == a["shop_id"])))
    assert len(user_ids_a) == 2  # owner + moderator

    before = snapshot(db)
    r = delete(client, a)
    assert r.status_code == 200 and "deleted" in r.json()["message"]

    db.expire_all()
    # the shop and every table that holds its data, checked one by one
    assert db.get(Shop, a["shop_id"]) is None
    for table in Base.metadata.sorted_tables:
        if "shop_id" in table.c and table.name != "admin_actions":
            assert db.scalar(select(func.count()).select_from(table).where(table.c.shop_id == a["shop_id"])) == 0, table.name
    assert db.scalar(select(func.count()).select_from(Message).where(Message.chat_id.in_([a["chat"], a["test_chat"]]))) == 0
    assert db.scalar(select(func.count()).select_from(text("password_reset_tokens")).where(text(f"user_id in ({','.join(map(str, user_ids_a))})"))) == 0
    assert db.scalars(select(User).where(User.id.in_(user_ids_a))).all() == []
    assert db.scalar(select(func.count()).select_from(EmbeddingChunk).where(EmbeddingChunk.shop_id == a["shop_id"])) == 0
    # files and Redis keys
    assert not a_folder.exists() and any(b_folder.rglob("*.png"))
    assert redis_keys(a["shop_id"]) == [] and get_redis().exists(f"fb:name_tried:{a['chat']}") == 0
    # Facebook was told to stop
    assert unsub.called and unsub.calls[0].request.headers["authorization"] == "Bearer EAAB-secret-token-A"

    # the other shop is untouched: every table lost exactly shop A's rows
    after = snapshot(db)
    for t in before:
        assert after[t] <= before[t]
    assert db.scalar(select(func.count()).select_from(Product).where(Product.shop_id == b["shop_id"])) == 1
    assert db.scalar(select(func.count()).select_from(Order).where(Order.shop_id == b["shop_id"])) == 1
    assert db.scalar(select(func.count()).select_from(Message).where(Message.shop_id == b["shop_id"])) == 3
    assert db.scalar(select(func.count()).select_from(FacebookPage).where(FacebookPage.shop_id == b["shop_id"])) == 1
    assert len(db.scalars(select(User).where(User.shop_id == b["shop_id"])).all()) == 2
    assert redis_keys(b["shop_id"]) != [] and get_redis().exists(f"fb:name_tried:{b['chat']}") == 1
    assert client.get(f"{API}/products", headers=auth_header(b["token"])).json()["total"] == 1
    assert client.get(f"{API}/orders", headers=auth_header(b["token"])).json()["total"] == 1


def test_after_deletion_nobody_from_the_shop_can_get_in_and_the_current_token_is_revoked(client, db, graph):
    a = build_shop(client, db, "A", "a@example.com")
    graph.delete(f"{GRAPH}/page-A/subscribed_apps").mock(return_value=httpx.Response(200, json={"success": True}))
    assert delete(client, a).status_code == 200
    assert client.get(f"{API}/auth/me", headers=auth_header(a["token"])).status_code == 401  # revoked / user gone
    assert client.get(f"{API}/products", headers=auth_header(a["mod_token"])).status_code == 401  # the moderator's token too
    for email in (a["email"], f"mod-{a['email']}"):
        assert client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    assert client.post(f"{API}/auth/signup", json={"shop_name": "Shop A", "owner_name": "New", "email": a["email"], "password": PASSWORD}).status_code == 201  # the e-mail is free again


def test_the_audit_log_of_the_admin_keeps_no_shop_data(client, db, graph, monkeypatch):
    a = build_shop(client, db, "A", "a@example.com")
    db.add(AdminAction(admin_user_id=None, shop_id=a["shop_id"], action="suspend", detail={}))
    db.commit()
    graph.delete(f"{GRAPH}/page-A/subscribed_apps").mock(return_value=httpx.Response(200, json={"success": True}))
    assert delete(client, a).status_code == 200
    row = db.scalars(select(AdminAction)).one()
    assert row.shop_id is None and row.detail == {}  # only the fact that an action happened remains


def test_a_deleted_shops_page_no_longer_receives_events(client, db, graph):
    a = build_shop(client, db, "A", "a@example.com")
    graph.delete(f"{GRAPH}/page-A/subscribed_apps").mock(return_value=httpx.Response(200, json={"success": True}))
    delete(client, a)
    event = {"object": "page", "entry": [{"id": "page-A", "messaging": [{"sender": {"id": "psid-new"}, "recipient": {"id": "page-A"}, "timestamp": 1, "message": {"mid": "m_1", "text": "hello"}}]}]}
    raw = json.dumps(event).encode()
    r = client.post(f"{API}/webhooks/messenger", content=raw, headers={"X-Hub-Signature-256": sign("test-app-secret", raw)})
    assert r.status_code == 200 and r.json()["received"] == 0
    assert db.scalars(select(Chat).where(Chat.customer_psid == "psid-new")).all() == []


def test_a_facebook_or_storage_failure_does_not_block_the_deletion(client, db, graph, monkeypatch):
    a = build_shop(client, db, "A", "a@example.com")
    graph.delete(f"{GRAPH}/page-A/subscribed_apps").mock(return_value=httpx.Response(500, json={"error": {"message": "down", "code": 2}}))

    def boom(self, shop_id):
        raise OSError("disk error")

    monkeypatch.setattr(StorageService, "delete_shop_files", boom)
    assert delete(client, a).status_code == 200
    assert db.get(Shop, a["shop_id"]) is None


def test_a_shop_without_a_page_or_files_can_be_deleted(client, db):
    token = signup(client, "solo@example.com", "Solo Shop")
    r = client.request("DELETE", f"{API}/shop", json={"password": PASSWORD, "shop_name": "Solo Shop"}, headers=auth_header(token))
    assert r.status_code == 200 and db.scalar(select(func.count()).select_from(Shop)) == 0


# ============================================================================== who may delete, and the confirmation


def test_wrong_password_or_wrong_name_deletes_nothing(client, db, graph):
    a = build_shop(client, db, "A", "a@example.com")
    before = snapshot(db)
    assert delete(client, a, password="wrong-password-1").status_code == 403
    assert delete(client, a, name="shop a").status_code == 422  # exact, case-sensitive
    assert delete(client, a, name="Shop A ").status_code == 422
    assert delete(client, a, name="Other shop").status_code == 422
    for bad in ({}, {"password": PASSWORD}, {"shop_name": "Shop A"}, {"password": "", "shop_name": "Shop A"}):
        assert client.request("DELETE", f"{API}/shop", json=bad, headers=auth_header(a["token"])).status_code == 422
    assert snapshot(db) == before and db.get(Shop, a["shop_id"]) is not None
    assert client.get(f"{API}/auth/me", headers=auth_header(a["token"])).status_code == 200  # still logged in


def test_password_guessing_is_rate_limited(client, db):
    a = build_shop(client, db, "A", "a@example.com")
    codes = [delete(client, a, password=f"guess-number-{i}").status_code for i in range(12)]
    assert codes[0] == 403 and 429 in codes
    assert delete(client, a).status_code == 429  # even the right password waits: the window has not passed
    assert db.get(Shop, a["shop_id"]) is not None


def test_only_the_owner_may_delete_the_shop(client, db, monkeypatch):
    a = build_shop(client, db, "A", "a@example.com")
    body = {"password": PASSWORD, "shop_name": "Shop A"}
    assert client.request("DELETE", f"{API}/shop", json=body, headers=auth_header(a["mod_token"])).status_code == 403
    assert client.request("DELETE", f"{API}/shop", json=body).status_code == 401
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    from app.cli import main as cli_main

    cli_main(["create-admin", "--email", "admin@example.com"])
    admin = client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": PASSWORD}).json()["access_token"]
    assert client.request("DELETE", f"{API}/shop", json=body, headers=auth_header(admin)).status_code == 403
    assert db.get(Shop, a["shop_id"]) is not None


def test_an_owner_cannot_delete_another_shop_by_naming_it(client, db):
    a = build_shop(client, db, "A", "a@example.com")
    b = build_shop(client, db, "B", "b@example.com")
    r = client.request("DELETE", f"{API}/shop", json={"password": PASSWORD, "shop_name": "Shop B"}, headers=auth_header(a["token"]))
    assert r.status_code == 422
    assert db.get(Shop, b["shop_id"]) is not None and db.get(Shop, a["shop_id"]) is not None


# ============================================================================== cross-tenant sweep


def sweep_requests(a: dict, a_week: str, a_notification: int, a_order: int):
    """Every shop-scoped endpoint that takes an id, aimed at SHOP A's resources. method, path, extra kwargs."""
    pid, cid, tid = a["product"], a["chat"], a["test_chat"]
    product_body = {"name": "x", "description": "", "price": 10, "sizes": [], "colours": [], "stock_count": 1}
    return [
        ("GET", f"/products/{pid}", {}),
        ("PUT", f"/products/{pid}", {"json": product_body}),
        ("DELETE", f"/products/{pid}", {}),
        ("POST", f"/products/{pid}/photos", {"files": [("files", ("a.png", PNG, "image/png"))]}),
        ("DELETE", f"/products/{pid}/photos/0", {}),
        ("GET", f"/orders/{a_order}", {}),
        ("PATCH", f"/orders/{a_order}", {"json": {"quantity": 2}}),
        ("POST", f"/orders/{a_order}/confirm", {}),
        ("POST", f"/orders/{a_order}/cancel", {}),
        ("GET", f"/chats/{cid}", {}),
        ("POST", f"/chats/{cid}/pause", {}),
        ("POST", f"/chats/{cid}/resume", {}),
        ("POST", f"/chats/{cid}/resolve-flag", {}),
        ("POST", f"/chats/{cid}/reply", {"json": {"text": "hello"}}),
        ("POST", f"/notifications/{a_notification}/read", {}),
        ("GET", f"/test-chat/sessions/{tid}/messages", {}),
        ("POST", f"/test-chat/sessions/{tid}/messages", {"json": {"text": "hello"}}),
        ("GET", f"/reports/weekly-insights/{a_week}", {}),
    ]


def test_every_endpoint_that_takes_an_id_is_covered_by_the_sweep():
    """A new id-taking endpoint must be added to the sweep (and so be checked for tenant isolation)."""
    from tests.test_privacy import sweep_requests as table

    covered = {(m, p.split("/", 2)[1], p.count("/")) for m, p, _ in table({"product": 1, "chat": 1, "test_chat": 1}, "2026-03-09", 1, 1)}
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/v1/") or "{" not in route.path:
            continue
        rest = route.path[len("/api/v1/"):]
        if rest.startswith(("admin/", "webhooks/")):
            continue  # the platform admin's endpoints are admin-only (tested separately); the webhook is signature-protected
        for method in route.methods - {"HEAD", "OPTIONS"}:
            segs = rest.split("/")
            if (method, segs[0], len(segs)) not in covered:
                missing.append((method, route.path))
    assert missing == [], f"add these to sweep_requests: {missing}"


def test_cross_tenant_sweep_shop_b_cannot_reach_shop_a(client, db):
    a = build_shop(client, db, "A", "a@example.com")
    b = build_shop(client, db, "B", "b@example.com")
    order_a = db.scalar(select(Order.id).where(Order.shop_id == a["shop_id"]))
    note_a = db.scalar(select(Notification.id).where(Notification.shop_id == a["shop_id"]))
    before = snapshot(db)
    hb, hmod = auth_header(b["token"]), auth_header(b["mod_token"])
    for method, path, kw in sweep_requests(a, "2026-03-02", note_a, order_a):
        for who, h in (("owner B", hb), ("moderator B", hmod)):
            r = client.request(method, f"{API}{path}", headers=h, **kw)
            assert r.status_code in (403, 404), f"{who}: {method} {path} -> {r.status_code}"
            assert "secret" not in r.text and PHONES["A"] not in r.text, f"{method} {path} leaked data"
    db.expire_all()
    assert snapshot(db) == before  # nothing of A was changed or deleted
    assert db.get(Product, a["product"]).name == "Saree A"
    assert db.get(Order, order_a).status == "draft" and db.get(Order, order_a).quantity == 1
    assert db.get(Chat, a["chat"]).ai_paused is False and db.get(Chat, a["chat"]).is_flagged is True
    assert db.scalar(select(Notification.read_at).where(Notification.id == note_a)) is None


def test_cross_tenant_sweep_lists_and_summaries_show_only_the_callers_data(client, db):
    a = build_shop(client, db, "A", "a@example.com")
    b = build_shop(client, db, "B", "b@example.com")
    db.add(Order(shop_id=a["shop_id"], product_name="Saree A", quantity=1, unit_price=100, customer_name="Customer A", customer_phone=PHONES["A"], customer_address="A Road, secret address", status="confirmed", confirmed_at=datetime.now(timezone.utc)))
    db.commit()
    endpoints = [
        "/products", "/products?q=Saree", "/orders?status=draft", "/orders?status=confirmed", "/orders?status=cancelled", "/orders/export", "/orders/product-options",
        "/chats", "/chats?filter=flagged", "/notifications", "/test-chat/sessions", "/shop/staff", "/shop/policy", "/shop/plan", "/facebook/page",
        "/reports/summary?from=2026-01-01&to=2026-12-31", "/reports/weekly-insights",
    ]
    for who in (b["token"], b["mod_token"]):
        for path in endpoints:
            r = client.get(f"{API}{path}", headers=auth_header(who))
            if r.status_code == 403:  # owner-only endpoints refuse the moderator
                continue
            assert r.status_code == 200, (path, r.status_code)
            for marker in ("Saree A", "Customer A", "psid-A", "A-secret-question", PHONES["A"], "A Road", "Page A", "mod-a@example.com", "a@example.com", "EAAB-secret-token-A"):
                assert marker not in r.text, f"{path} showed shop A's {marker!r} to shop B"
    # and shop A's own view does contain its data (the markers are real)
    assert "Customer A" in client.get(f"{API}/orders?status=draft", headers=auth_header(a["token"])).text


def test_customer_details_are_not_in_any_response_to_another_role_than_the_shops_users(client, db):
    """The platform admin sees counts and costs only: never a customer's name, phone or address (NFR-04)."""
    from app.cli import main as cli_main

    a = build_shop(client, db, "A", "a@example.com")
    import os

    os.environ["ADMIN_PASSWORD"] = PASSWORD
    try:
        cli_main(["create-admin", "--email", "admin@example.com"])
    finally:
        os.environ.pop("ADMIN_PASSWORD", None)
    admin = auth_header(client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": PASSWORD}).json()["access_token"])
    for path in ("/admin/shops", f"/admin/shops/{a['shop_id']}", "/admin/plans", "/admin/ai-usage?from=2026-01-01&to=2026-12-31", "/admin/system-health"):
        text_ = client.get(f"{API}{path}", headers=admin).text
        for marker in ("Customer A", "psid-A", "secret-question", PHONES["A"], "secret address"):
            assert marker not in text_, f"{path} showed {marker!r} to the platform admin"


# ============================================================================== logs


def test_masking_removes_secrets_and_personal_numbers():
    jwt_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop"
    cases = [
        (f"token {jwt_token} seen", jwt_token),
        ("Authorization: Bearer abc123.def-456", "abc123.def-456"),
        ("page token EAABsbCS1iHgBAexampleexampleexample123", "EAABsbCS1iHgBAexample"),
        ("password=hunter2hunter2&x=1", "hunter2"),
        ('{"password": "my secret pw"}', "my"),
        ("GET /api/v1/facebook/callback?code=AQD123&state=eyJabc HTTP/1.1", "AQD123"),
        ("hub.verify_token=verify-me-please", "verify-me-please"),
        ("customer rahim@example.com wrote", "rahim@example.com"),
        ("phone 01712345678 and +880 1712-345678", "01712345678"),
        ("phone ০১৭১২৩৪৫৬৭৮", "০১৭১২৩৪৫৬৭৮"),
        ("psid 5550001234567", "5550001234567"),
        ("stored gAAAAABmEXAMPLEencryptedTokenValue12345==", "gAAAAABmEXAMPLE"),
    ]
    for line, secret in cases:
        masked = mask(line)
        assert secret not in masked, (line, masked)
    assert mask("shop 7 chat 12 took 6583 ms on 2026-10-01") == "shop 7 chat 12 took 6583 ms on 2026-10-01"  # ordinary lines stay readable


def test_log_records_are_masked_including_tracebacks_and_uvicorn_style_args(caplog):
    caplog.set_level(logging.DEBUG)
    log = logging.getLogger("shopsathi.test_masking")
    log.info("user %s phone %s", "rahim@example.com", "01712345678")
    log.warning("GET %s", "/x?access_token=EAAB1234567890abcdef")
    try:
        raise ValueError("INSERT INTO messages (text) VALUES ('call 01712345678')")
    except ValueError:
        log.exception("failed")
    for secret in ("rahim@example.com", "01712345678", "EAAB1234567890"):
        assert secret not in caplog.text, secret
    assert "[email]" in caplog.text and "[number]" in caplog.text


def test_the_local_mail_log_is_only_for_local_runs(caplog, monkeypatch):
    from app.core.config import get_settings
    from app.services.email import EmailService

    caplog.set_level(logging.DEBUG)
    EmailService().send_password_reset("reset@example.com", "http://localhost:3000/reset-password?token=abc123def456")
    assert "reset@example.com" in caplog.text and "abc123def456" in caplog.text  # local run: the link can be tried without SMTP
    caplog.clear()
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        EmailService().send_password_reset("reset@example.com", "http://localhost:3000/reset-password?token=abc123def456")
        assert "reset@example.com" not in caplog.text and "abc123def456" not in caplog.text
        assert "SMTP is not configured" in caplog.text
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_a_full_conversation_and_login_write_no_customer_data_password_or_token_to_the_logs(client, db, caplog, graph):
    """Run the whole pipeline (webhook -> worker -> AI -> send) and a login with the log level at DEBUG."""
    caplog.set_level(logging.DEBUG)
    a = build_shop(client, db, "A", "a@example.com")
    sid = a["shop_id"]
    secret_token = "EAAB-secret-token-A"
    graph.post(f"{GRAPH}/me/messages").mock(return_value=httpx.Response(200, json={"message_id": "m_1"}))
    graph.get(url__regex=rf"{GRAPH}/\d+(\?.*)?$").mock(return_value=httpx.Response(200, json={"first_name": "Nasrin", "last_name": "Sultana"}))
    graph.post(f"{GRAPH}/me/messages")  # (the same mock; kept for clarity)
    customer_text = "Saree A price? amar nam Nasrin Sultana, phone 01712345678, address House 5 Road 3 Dhanmondi"
    event = {"object": "page", "entry": [{"id": "page-A", "messaging": [{"sender": {"id": "7770001"}, "recipient": {"id": "page-A"}, "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000), "message": {"mid": "m_priv_1", "text": customer_text}}]}]}
    raw = json.dumps(event).encode()
    assert client.post(f"{API}/webhooks/messenger", content=raw, headers={"X-Hub-Signature-256": sign("test-app-secret", raw)}).status_code == 200
    client.post(f"{API}/auth/login", json={"email": a["email"], "password": PASSWORD})
    client.post(f"{API}/auth/login", json={"email": a["email"], "password": "definitely-wrong-1"})
    client.get(f"{API}/products", headers=auth_header(a["token"]))
    assert db.scalars(select(Message).where(Message.external_message_id == "m_priv_1")).one().text.startswith("Saree A")  # it really ran
    text_ = caplog.text
    for secret in ("01712345678", "Nasrin", "Sultana", "Dhanmondi", "House 5", "7770001", PASSWORD, "definitely-wrong-1", secret_token, a["token"], "test-app-secret", "Saree A price"):
        assert secret not in text_, f"{secret!r} was written to the logs"
