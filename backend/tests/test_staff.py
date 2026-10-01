from sqlalchemy import select

from app.api.deps import require_owner, require_shop_user
from app.models import User
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"


def signup(client, email, shop):
    r = client.post(f"{API}/auth/signup", json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD})
    assert r.status_code == 201
    return r.json()


def add_mod(client, token, email="mod@example.com", name="Mona Moderator", password=PASSWORD):
    return client.post(f"{API}/shop/staff", json={"email": email, "full_name": name, "password": password}, headers=auth_header(token))


def login(client, email, password=PASSWORD):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


def test_owner_can_add_and_list_moderators(client, db):
    a = signup(client, "a@example.com", "Shop A")
    r = add_mod(client, a["access_token"])
    assert r.status_code == 201
    body = r.json()
    assert body["role"] == "moderator" and body["email"] == "mod@example.com"
    assert "password" not in body and "password_hash" not in body
    user = db.scalar(select(User).where(User.email == "mod@example.com"))
    assert user.shop_id == a["shop"]["id"] and user.password_hash != PASSWORD

    add_mod(client, a["access_token"], email="mod2@example.com", name="Second")
    listed = client.get(f"{API}/shop/staff", headers=auth_header(a["access_token"])).json()
    assert [u["email"] for u in listed] == ["mod@example.com", "mod2@example.com"]  # owner not listed


def test_staff_email_must_be_unique_and_valid(client):
    a = signup(client, "a@example.com", "Shop A")
    t = a["access_token"]
    assert add_mod(client, t).status_code == 201
    assert add_mod(client, t, email="MOD@example.com").status_code == 409
    assert add_mod(client, t, email="a@example.com").status_code == 409  # owner's email
    assert add_mod(client, t, email="bad", name="x").status_code == 422
    assert add_mod(client, t, email="new@example.com", password="short").status_code == 422


def test_moderator_can_log_in_and_sees_own_shop(client):
    a = signup(client, "a@example.com", "Shop A")
    add_mod(client, a["access_token"])
    r = login(client, "mod@example.com")
    assert r.status_code == 200
    me = client.get(f"{API}/auth/me", headers=auth_header(r.json()["access_token"])).json()
    assert me["user"]["role"] == "moderator"
    assert me["shop"]["id"] == a["shop"]["id"]


def test_moderator_forbidden_on_staff_and_plan_change(client):
    a = signup(client, "a@example.com", "Shop A")
    add_mod(client, a["access_token"])
    h = auth_header(login(client, "mod@example.com").json()["access_token"])
    assert client.get(f"{API}/shop/staff", headers=h).status_code == 403
    assert add_mod(client, h["Authorization"].split()[1], email="x@example.com").status_code == 403
    r = client.post(f"{API}/shop/plan/change", json={"plan_code": "basic", "simulated_payment_confirmed": True}, headers=h)
    assert r.status_code == 403


def test_staff_endpoints_need_authentication(client):
    assert client.get(f"{API}/shop/staff").status_code == 401
    assert client.post(f"{API}/shop/staff", json={}).status_code == 401


def test_owner_of_shop_a_cannot_see_shop_b_staff(client):
    a = signup(client, "a@example.com", "Shop A")
    b = signup(client, "b@example.com", "Shop B")
    add_mod(client, b["access_token"], email="bmod@example.com")
    assert client.get(f"{API}/shop/staff", headers=auth_header(a["access_token"])).json() == []
    # a moderator created by A belongs to A only
    add_mod(client, a["access_token"], email="amod@example.com")
    listed_b = [u["email"] for u in client.get(f"{API}/shop/staff", headers=auth_header(b["access_token"])).json()]
    assert listed_b == ["bmod@example.com"]


def test_role_dependencies_exclude_platform_admin(client, db, monkeypatch):
    from app.cli import main as cli_main

    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    cli_main(["create-admin", "--email", "admin@example.com"])
    token = login(client, "admin@example.com").json()["access_token"]
    h = auth_header(token)
    assert client.get(f"{API}/shop/staff", headers=h).status_code == 403
    assert client.get(f"{API}/shop/plan", headers=h).status_code == 403  # not a shop user
    assert callable(require_owner) and callable(require_shop_user)
