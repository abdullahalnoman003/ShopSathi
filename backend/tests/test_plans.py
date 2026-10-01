from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Plan, Shop, ShopMessageUsage, SimulatedPayment, User
from app.services.usage import UsageLimitService, current_period
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"


def signup(client, plan_code=None, confirmed=None, email="a@example.com", shop="Shop A"):
    body = {"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD}
    if plan_code is not None:
        body["plan_code"] = plan_code
    if confirmed is not None:
        body["simulated_payment_confirmed"] = confirmed
    return client.post(f"{API}/auth/signup", json=body)


def test_plans_listed_publicly(client):
    r = client.get(f"{API}/plans")
    assert r.status_code == 200
    plans = r.json()
    assert [p["code"] for p in plans] == ["free", "basic", "pro"]
    assert plans[0]["monthly_price"] == 0
    assert all(p["monthly_message_limit"] > 0 for p in plans)


def test_signup_with_free_plan_needs_no_payment(client, db):
    r = signup(client, "free")
    assert r.status_code == 201
    shop = db.scalar(select(Shop))
    assert shop.plan.code == "free"
    assert db.scalar(select(SimulatedPayment.id)) is None


def test_signup_without_plan_code_defaults_to_free(client, db):
    assert signup(client).status_code == 201
    assert db.scalar(select(Shop)).plan.code == "free"


@pytest.mark.parametrize("code", ["basic", "pro"])
def test_signup_with_paid_plan_records_simulated_payment(client, db, code):
    r = signup(client, code, confirmed=True)
    assert r.status_code == 201
    shop = db.scalar(select(Shop))
    assert shop.plan.code == code
    pay = db.scalar(select(SimulatedPayment))
    assert (pay.shop_id, pay.plan_id, pay.status) == (shop.id, shop.plan_id, "simulated_success")
    assert pay.amount == shop.plan.monthly_price


def test_paid_plan_without_confirmation_is_rejected(client, db):
    for confirmed in (None, False):
        r = signup(client, "pro", confirmed=confirmed)
        assert r.status_code == 400
    assert db.scalar(select(User.id)) is None  # nothing was created
    assert db.scalar(select(SimulatedPayment.id)) is None


def test_unknown_plan_rejected(client):
    assert signup(client, "platinum", confirmed=True).status_code == 400


def test_shop_plan_endpoint_shows_plan_and_usage(client, db):
    token = signup(client, "free").json()["access_token"]
    assert client.get(f"{API}/shop/plan").status_code == 401
    body = client.get(f"{API}/shop/plan", headers=auth_header(token)).json()
    limit = db.scalar(select(Plan.monthly_message_limit).where(Plan.code == "free"))
    assert body["plan"]["code"] == "free"
    assert body["usage"] == {"period": current_period(), "used": 0, "limit": limit, "remaining": limit}

    shop_id = db.scalar(select(Shop.id))
    UsageLimitService(db).record_ai_reply(shop_id)
    body = client.get(f"{API}/shop/plan", headers=auth_header(token)).json()
    assert body["usage"]["used"] == 1 and body["usage"]["remaining"] == limit - 1


def test_change_plan_creates_simulated_payment(client, db):
    token = signup(client, "free").json()["access_token"]
    h = auth_header(token)
    # paid plan without confirmation
    r = client.post(f"{API}/shop/plan/change", json={"plan_code": "basic"}, headers=h)
    assert r.status_code == 400
    assert db.scalar(select(SimulatedPayment.id)) is None

    r = client.post(f"{API}/shop/plan/change", json={"plan_code": "basic", "simulated_payment_confirmed": True}, headers=h)
    assert r.status_code == 200
    assert r.json()["plan"]["code"] == "basic"
    pay = db.scalar(select(SimulatedPayment))
    assert pay.status == "simulated_success" and pay.amount > 0

    # same plan again is rejected; downgrade to free needs no payment and records none
    assert client.post(f"{API}/shop/plan/change", json={"plan_code": "basic", "simulated_payment_confirmed": True}, headers=h).status_code == 400
    r = client.post(f"{API}/shop/plan/change", json={"plan_code": "free"}, headers=h)
    assert r.status_code == 200 and r.json()["plan"]["code"] == "free"
    db.expire_all()
    assert len(db.scalars(select(SimulatedPayment)).all()) == 1


def test_only_owner_can_change_plan(client, db):
    signup(client, "free")
    shop_id = db.scalar(select(Shop.id))
    db.add(User(email="mod@example.com", password_hash=hash_password(PASSWORD), full_name="Mod", role="moderator", shop_id=shop_id))
    db.commit()
    token = client.post(f"{API}/auth/login", json={"email": "mod@example.com", "password": PASSWORD}).json()["access_token"]
    h = auth_header(token)
    assert client.get(f"{API}/shop/plan", headers=h).status_code == 200  # can view
    r = client.post(f"{API}/shop/plan/change", json={"plan_code": "basic", "simulated_payment_confirmed": True}, headers=h)
    assert r.status_code == 403
    assert client.post(f"{API}/shop/plan/change", json={"plan_code": "basic", "simulated_payment_confirmed": True}).status_code == 401


# ---- UsageLimitService ----

@pytest.fixture
def shop_id(client, db):
    signup(client, "free")
    return db.scalar(select(Shop.id))


def test_usage_increments_and_blocks_exactly_at_limit(db, shop_id):
    db.scalar(select(Plan).where(Plan.code == "free")).monthly_message_limit = 3
    db.commit()
    svc = UsageLimitService(db)
    assert svc.get_usage(shop_id).used == 0
    for expected in (1, 2, 3):
        assert svc.can_send_ai_reply(shop_id) is True
        assert svc.record_ai_reply(shop_id) == expected
    usage = svc.get_usage(shop_id)
    assert (usage.used, usage.limit, usage.remaining) == (3, 3, 0)
    assert svc.can_send_ai_reply(shop_id) is False


def test_new_month_starts_at_zero(db, shop_id):
    db.scalar(select(Plan).where(Plan.code == "free")).monthly_message_limit = 1
    db.commit()
    svc = UsageLimitService(db)
    dhaka = ZoneInfo("Asia/Dhaka")
    oct_ = datetime(2026, 10, 15, 12, tzinfo=dhaka)
    nov = datetime(2026, 11, 1, 0, 0, 1, tzinfo=dhaka)
    svc.record_ai_reply(shop_id, oct_)
    assert svc.can_send_ai_reply(shop_id, oct_) is False
    assert svc.get_usage(shop_id, nov).used == 0
    assert svc.can_send_ai_reply(shop_id, nov) is True
    assert len(db.scalars(select(ShopMessageUsage)).all()) == 1  # only October has a row so far


def test_month_boundary_uses_dhaka_time():
    utc = ZoneInfo("UTC")
    # 20:00 UTC on 31 Oct is already 1 Nov in Dhaka (UTC+6)
    assert current_period(datetime(2026, 10, 31, 20, tzinfo=utc)) == "2026-11"
    assert current_period(datetime(2026, 10, 31, 17, tzinfo=utc)) == "2026-10"


def test_usage_is_per_shop(client, db):
    signup(client, "free", email="a@example.com", shop="A")
    signup(client, "free", email="b@example.com", shop="B")
    a, b = db.scalars(select(Shop.id).order_by(Shop.id)).all()
    svc = UsageLimitService(db)
    svc.record_ai_reply(a)
    svc.record_ai_reply(a)
    assert svc.get_usage(a).used == 2
    assert svc.get_usage(b).used == 0
