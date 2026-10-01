"""Who may call what: every endpoint of the API against anonymous, owner, moderator and platform admin.

The endpoint list is generated from the application itself (its OpenAPI schema), so a new endpoint that is not classified
below fails the test until someone decides who may use it (access matrix: docs/CONVENTIONS.md)."""

import pytest

from app.cli import main as cli_main
from app.main import app
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"
ANON, OWNER, MOD, ADMIN = "anonymous", "owner", "moderator", "platform_admin"
ROLES = (ANON, OWNER, MOD, ADMIN)

PUBLIC = {"/health", "/plans", "/auth/signup", "/auth/login", "/auth/password-reset/request", "/auth/password-reset/confirm"}
SIGNED = {"/webhooks/messenger"}  # protected by Meta's signature, tested in test_webhook_and_limits.py
ANY_LOGGED_IN = {"/auth/me", "/auth/logout"}
OWNER_ONLY_PREFIXES = ("/products", "/shop/staff", "/shop/policy", "/shop/plan/change", "/facebook", "/test-chat", "/reports")
SHOP_USER_PREFIXES = ("/chats", "/orders", "/notifications")


def allowed_roles(method: str, path: str) -> set[str]:
    """The access matrix as code. Raises for an endpoint nobody classified."""
    if path in PUBLIC or path in SIGNED:
        return set(ROLES)
    if path in ANY_LOGGED_IN:
        return {OWNER, MOD, ADMIN}
    if path.startswith("/admin/") or path == "/admin":
        return {ADMIN}
    if method == "DELETE" and path == "/shop":
        return {OWNER}  # deleting the shop
    if path == "/shop/plan" and method == "GET":
        return {OWNER, MOD}  # the shop's own plan and usage
    if path.startswith(OWNER_ONLY_PREFIXES):
        return {OWNER}
    if path.startswith(SHOP_USER_PREFIXES):
        return {OWNER, MOD}
    raise AssertionError(f"{method} {path} is not classified in the role matrix: decide who may use it")


def all_endpoints() -> list[tuple[str, str]]:
    paths = app.openapi()["paths"]  # the app nests its routers, so app.routes does not list them
    return sorted((m.upper(), p[len(API):]) for p, ops in paths.items() if p.startswith(API + "/") for m in ops)


def fill(path: str) -> str:
    return path.replace("{week_start}", "2026-03-09").replace("{index}", "0")


def concrete(path: str) -> str:
    out = fill(path)
    while "{" in out:
        start = out.index("{")
        out = out[:start] + "999999" + out[out.index("}") + 1 :]
    return out


@pytest.fixture
def identities(client, monkeypatch):
    owner = client.post(f"{API}/auth/signup", json={"shop_name": "Shop A", "owner_name": "Owner", "email": "owner@example.com", "password": PASSWORD}).json()["access_token"]
    client.post(f"{API}/shop/staff", json={"email": "mod@example.com", "full_name": "Mod", "password": PASSWORD}, headers=auth_header(owner))
    mod = client.post(f"{API}/auth/login", json={"email": "mod@example.com", "password": PASSWORD}).json()["access_token"]
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    cli_main(["create-admin", "--email", "admin@example.com"])
    admin = client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": PASSWORD}).json()["access_token"]
    return {ANON: {}, OWNER: auth_header(owner), MOD: auth_header(mod), ADMIN: auth_header(admin)}


def test_the_endpoint_list_is_really_generated_from_the_router():
    endpoints = all_endpoints()
    assert len(endpoints) >= 55, "the list looks too short: the matrix test would check nothing"
    assert ("DELETE", "/shop") in endpoints and ("POST", "/admin/shops/{shop_id}/suspend") in endpoints and ("GET", "/chats/{chat_id}") in endpoints


def test_every_endpoint_is_classified():
    for method, path in all_endpoints():
        allowed_roles(method, path)


def test_every_endpoint_gives_every_role_the_right_answer(client, identities):
    wrong: list[str] = []
    for method, path in all_endpoints():
        if path == "/auth/logout":
            continue  # revokes the token it is called with: tested in test_auth_security.py
        allowed = allowed_roles(method, path)
        for role in ROLES:
            kwargs = {"headers": identities[role]}
            if method in ("POST", "PUT", "PATCH", "DELETE"):
                kwargs["json"] = {}  # an empty body: a call that is allowed fails validation (422) instead of changing anything
            r = client.request(method, API + concrete(path), **kwargs)
            if path in SIGNED:
                continue
            if role in allowed:
                if r.status_code in (401, 403):
                    wrong.append(f"{role} should be allowed {method} {path} but got {r.status_code}")
            else:
                expected = 401 if role == ANON else 403
                if r.status_code != expected:
                    wrong.append(f"{role} must get {expected} for {method} {path} but got {r.status_code}")
    assert wrong == [], "\n" + "\n".join(wrong)


def test_logout_needs_a_login(client, identities):
    assert client.post(f"{API}/auth/logout").status_code == 401
    assert client.post(f"{API}/auth/logout", headers=identities[MOD]).status_code == 200


def test_the_matrix_agrees_with_the_documented_access_table(client, identities):
    """The rows of the table in docs/CONVENTIONS.md, spot-checked with real calls."""
    rows = [
        ("GET", "/shop/staff", {OWNER}), ("GET", "/shop/plan", {OWNER, MOD}), ("GET", "/facebook/page", {OWNER}), ("GET", "/products", {OWNER}),
        ("GET", "/shop/policy", {OWNER}), ("GET", "/test-chat/sessions", {OWNER}), ("GET", "/reports/weekly-insights", {OWNER}),
        ("GET", "/chats", {OWNER, MOD}), ("GET", "/orders", {OWNER, MOD}), ("GET", "/orders/export", {OWNER, MOD}), ("GET", "/notifications", {OWNER, MOD}),
        ("GET", "/admin/shops", {ADMIN}), ("GET", "/admin/system-health", {ADMIN}),
    ]
    for method, path, ok in rows:
        for role in (OWNER, MOD, ADMIN):
            code = client.request(method, API + path, headers=identities[role]).status_code
            assert (code != 403) == (role in ok), f"{role} {method} {path} -> {code}"
