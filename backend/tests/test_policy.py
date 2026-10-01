from decimal import Decimal

import pytest
from sqlalchemy import select

from app.cli import main as cli_main
from app.models import DeliveryArea, Shop, ShopPolicy
from app.services import policy as policy_module
from app.services.policy import PolicyService
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"
URL = f"{API}/shop/policy"


def signup(client, email="a@example.com", shop="Shop A"):
    r = client.post(
        f"{API}/auth/signup",
        json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD},
    )
    return r.json()["access_token"]


@pytest.fixture
def token(client):
    return signup(client)


def body(**over):
    data = {
        "delivery_time": "1-2 days inside Dhaka",
        "return_rules": "Return within 3 days",
        "payment_options": "COD, bKash",
        "delivery_areas": [
            {"area_name": "Inside Dhaka", "charge": 60},
            {"area_name": "Khagan", "charge": 100},
        ],
    }
    data.update(over)
    return data


def put(client, token, **over):
    return client.put(URL, json=body(**over), headers=auth_header(token))


def test_get_returns_empty_defaults(client, token):
    r = client.get(URL, headers=auth_header(token))
    assert r.status_code == 200
    assert r.json() == {
        "delivery_time": "",
        "return_rules": "",
        "payment_options": "",
        "delivery_areas": [],
        "updated_at": None,
    }


def test_save_then_update(client, token, db):
    h = auth_header(token)
    r = put(client, token)
    assert r.status_code == 200
    saved = r.json()
    assert saved["delivery_time"] == "1-2 days inside Dhaka" and saved["updated_at"] is not None
    assert saved["delivery_areas"] == [
        {"area_name": "Inside Dhaka", "charge": 60.0},
        {"area_name": "Khagan", "charge": 100.0},
    ]
    assert client.get(URL, headers=h).json() == saved  # persisted

    r = put(
        client,
        token,
        return_rules="No returns",
        delivery_areas=[{"area_name": "Khagan", "charge": "110.50"}, {"area_name": "Savar", "charge": 0}],
    )
    assert r.status_code == 200
    got = client.get(URL, headers=h).json()
    assert got["return_rules"] == "No returns" and got["delivery_time"] == "1-2 days inside Dhaka"
    assert got["delivery_areas"] == [{"area_name": "Khagan", "charge": 110.5}, {"area_name": "Savar", "charge": 0.0}]
    # still exactly one policy row and the replaced area list for this shop
    assert len(db.scalars(select(ShopPolicy)).all()) == 1
    assert len(db.scalars(select(DeliveryArea)).all()) == 2

    assert put(client, token, delivery_areas=[]).json()["delivery_areas"] == []  # areas can be cleared


@pytest.mark.parametrize(
    "areas,fragment",
    [
        ([{"area_name": "Khagan", "charge": 1}, {"area_name": "khagan", "charge": 2}], "Duplicate area"),
        ([{"area_name": "Inside Dhaka", "charge": 1}, {"area_name": " inside   DHAKA ", "charge": 2}], "Duplicate area"),
        ([{"area_name": "Mirpur-1", "charge": 1}, {"area_name": "mirpur 1", "charge": 2}], "Duplicate area"),
        ([{"area_name": "Khagan", "charge": -1}], "charge"),
        ([{"area_name": "Khagan", "charge": 10.123}], "charge"),
        ([{"area_name": "", "charge": 5}], "area_name"),
        ([{"area_name": "   ", "charge": 5}], "required"),
        ([{"area_name": "x" * 101, "charge": 5}], "area_name"),
        ([{"area_name": "Khagan"}], "charge"),
    ],
)
def test_invalid_areas_rejected(client, token, areas, fragment):
    r = put(client, token, delivery_areas=areas)
    assert r.status_code == 422
    assert fragment in str(r.json()["detail"])
    assert client.get(URL, headers=auth_header(token)).json()["delivery_areas"] == []  # nothing saved


def test_text_length_limits(client, token):
    assert put(client, token, return_rules="x" * 2001).status_code == 422
    assert put(client, token, payment_options="x" * 2000).status_code == 200
    too_many = [{"area_name": f"Area {i}", "charge": 1} for i in range(101)]
    assert put(client, token, delivery_areas=too_many).status_code == 422


def test_text_is_trimmed(client, token):
    r = put(client, token, delivery_time="  2 days  ", delivery_areas=[{"area_name": "  Inside   Dhaka ", "charge": 1}])
    assert r.json()["delivery_time"] == "2 days"
    assert r.json()["delivery_areas"][0]["area_name"] == "Inside Dhaka"


def test_get_delivery_charge_found_and_not_found(client, token, db):
    put(
        client,
        token,
        delivery_areas=[
            {"area_name": "Inside Dhaka", "charge": 60},
            {"area_name": "Khagan", "charge": 100},
            {"area_name": "Mirpur-10", "charge": 65.5},
        ],
    )
    shop_id = db.scalar(select(Shop.id))
    svc = PolicyService(db, shop_id)

    for text in ["Khagan", "khagan", "  KHAGAN ", "Inside Dhaka", "inside  dhaka", "inside-dhaka", "Mirpur 10"]:
        res = svc.get_delivery_charge(text)
        assert res.found is True, text
    assert svc.get_delivery_charge("Khagan").charge == Decimal("100.00")
    assert svc.get_delivery_charge("mirpur 10").area_name == "Mirpur-10"
    assert svc.get_delivery_charge("mirpur 10").charge == Decimal("65.50")

    # no guessing: partial, extra words, unknown, empty
    for text in ["Khag", "Khagan e", "Khagan e delivery charge koto?", "Dhaka", "Savar", "", "   ", "!!!"]:
        res = svc.get_delivery_charge(text)
        assert (res.found, res.area_name, res.charge) == (False, None, None), text


def test_get_delivery_charge_for_shop_without_policy(client, token, db):
    assert PolicyService(db, db.scalar(select(Shop.id))).get_delivery_charge("Khagan").found is False


def test_tenant_isolation(client, db):
    a = signup(client, "a@example.com", "Shop A")
    b = signup(client, "b@example.com", "Shop B")
    put(client, a, delivery_areas=[{"area_name": "Khagan", "charge": 100}, {"area_name": "Only A", "charge": 1}])
    put(client, b, delivery_areas=[{"area_name": "Khagan", "charge": 250}], return_rules="B rules")

    got_a = client.get(URL, headers=auth_header(a)).json()
    got_b = client.get(URL, headers=auth_header(b)).json()
    assert [x["area_name"] for x in got_a["delivery_areas"]] == ["Khagan", "Only A"]
    assert got_b["delivery_areas"] == [{"area_name": "Khagan", "charge": 250.0}]
    assert got_b["return_rules"] == "B rules" and got_a["return_rules"] != "B rules"

    shop_a, shop_b = db.scalars(select(Shop.id).order_by(Shop.id)).all()
    assert PolicyService(db, shop_a).get_delivery_charge("Khagan").charge == Decimal("100.00")
    assert PolicyService(db, shop_b).get_delivery_charge("Khagan").charge == Decimal("250.00")
    assert PolicyService(db, shop_b).get_delivery_charge("Only A").found is False

    # updating B does not touch A
    put(client, b, delivery_areas=[])
    assert len(client.get(URL, headers=auth_header(a)).json()["delivery_areas"]) == 2


def test_moderator_403_and_anonymous_401(client, token):
    client.post(
        f"{API}/shop/staff",
        json={"email": "mod@example.com", "full_name": "Mod", "password": PASSWORD},
        headers=auth_header(token),
    )
    mod = client.post(f"{API}/auth/login", json={"email": "mod@example.com", "password": PASSWORD}).json()["access_token"]
    assert client.get(URL, headers=auth_header(mod)).status_code == 403
    assert put(client, mod).status_code == 403
    assert client.get(URL).status_code == 401
    assert client.put(URL, json=body()).status_code == 401


def test_policy_changed_hook_called_on_save(client, token, monkeypatch):
    calls = []
    monkeypatch.setattr(policy_module.policy_hooks, "policy_changed", lambda shop_id: calls.append(shop_id))
    client.get(URL, headers=auth_header(token))
    assert calls == []
    put(client, token)
    put(client, token, delivery_time="x")
    assert len(calls) == 2


def test_seed_creates_demo_policies_idempotently(db, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "demo-password-1")
    assert cli_main(["seed"]) == 0
    policies = db.scalars(select(ShopPolicy)).all()
    assert len(policies) == 2
    areas = db.scalars(select(DeliveryArea)).all()
    assert any(a.area_name == "Inside Dhaka" for a in areas)
    assert any(a.area_name == "Outside Dhaka" for a in areas)
    assert any(a.area_name == "Khagan" for a in areas)
    assert cli_main(["seed"]) == 0
    db.expire_all()
    assert len(db.scalars(select(ShopPolicy)).all()) == 2
    assert len(db.scalars(select(DeliveryArea)).all()) == len(areas)
