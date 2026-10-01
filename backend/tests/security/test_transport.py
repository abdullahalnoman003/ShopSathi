"""NFR-03 transport: production runs behind an HTTPS reverse proxy (Prompt 23). The backend must trust that proxy's
X-Forwarded-* headers (and nobody else's) and only let the frontend's origin call it from a browser."""

import importlib

import pytest
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.redis import get_redis
from tests.conftest import PASSWORD

API = "/api/v1"
FRONTEND = "http://localhost:3000"


def cors_config():
    from app.main import app

    return next(m for m in app.user_middleware if m.cls is CORSMiddleware).kwargs


def test_cors_is_limited_to_the_frontend_origin():
    cfg = cors_config()
    assert cfg["allow_origins"] == [get_settings().frontend_origin] and "*" not in cfg["allow_origins"]
    assert cfg["allow_credentials"] is True  # so "*" would be dangerous; it must never be combined with it


def test_a_browser_from_another_site_gets_no_cors_permission(client):
    ask = {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"}
    ok = client.options(f"{API}/auth/me", headers={"Origin": get_settings().frontend_origin, **ask})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == get_settings().frontend_origin
    for evil in ("https://evil.example", "http://localhost:3001", "http://localhost:3000.evil.example", "null", "https://localhost:3000"):
        r = client.options(f"{API}/auth/me", headers={"Origin": evil, **ask})
        assert "access-control-allow-origin" not in r.headers, evil
        g = client.get(f"{API}/health", headers={"Origin": evil})
        assert "access-control-allow-origin" not in g.headers, evil


def fresh_app(monkeypatch, trusted: str):
    """The application as it is built for a given TRUSTED_PROXIES (the setting is read when the app is created)."""
    monkeypatch.setenv("TRUSTED_PROXIES", trusted)
    get_settings.cache_clear()
    import app.main

    return importlib.reload(app.main).app


@pytest.fixture
def restore_app():
    yield
    get_settings.cache_clear()
    import app.main

    importlib.reload(app.main)


def test_forwarded_headers_from_a_trusted_proxy_are_believed(monkeypatch, restore_app):
    app = fresh_app(monkeypatch, "testclient")  # the test client's address plays the proxy
    with TestClient(app) as c:
        r = c.post(f"{API}/auth/login", json={"email": "x@example.com", "password": "wrong-password-1"}, headers={"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Proto": "https"})
        assert r.status_code == 401
        keys = {k.decode() for k in get_redis().scan_iter(match="rl:login-ip:*")}
        assert keys == {"rl:login-ip:203.0.113.7"}  # the rate limit counts the real client, not the proxy
        redirect = c.get(f"{API}/shop/", headers={"X-Forwarded-Proto": "https"}, follow_redirects=False)
        assert redirect.status_code in (307, 308) and redirect.headers["location"].startswith("https://")  # URLs stay https


def test_forwarded_headers_from_anyone_else_are_ignored(monkeypatch, restore_app):
    app = fresh_app(monkeypatch, "10.9.9.9")  # not the test client
    with TestClient(app) as c:
        c.post(f"{API}/auth/login", json={"email": "x@example.com", "password": "wrong-password-1"}, headers={"X-Forwarded-For": "203.0.113.7", "X-Forwarded-Proto": "https"})
        keys = {k.decode() for k in get_redis().scan_iter(match="rl:login-ip:*")}
        assert keys == {"rl:login-ip:testclient"}  # a spoofed address does not choose the rate-limit bucket
        redirect = c.get(f"{API}/shop/", headers={"X-Forwarded-Proto": "https"}, follow_redirects=False)
        assert redirect.headers["location"].startswith("http://")


def test_a_client_cannot_dodge_the_login_limit_by_changing_a_forged_header(client):
    limit = get_settings().login_rate_limit
    codes = [client.post(f"{API}/auth/login", json={"email": f"u{i}@example.com", "password": "wrong-password-1"}, headers={"X-Forwarded-For": f"198.51.100.{i}"}).status_code for i in range(limit + 3)]
    assert 429 in codes


def test_trusted_proxies_has_a_safe_default_and_is_documented():
    import re
    from pathlib import Path

    example = (Path(__file__).resolve().parents[2] / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^TRUSTED_PROXIES=127\.0\.0\.1$", example, re.MULTILINE)
    from app.core.config import Settings

    assert Settings.model_fields["trusted_proxies"].default == "127.0.0.1"  # nothing is trusted by default but the local machine
