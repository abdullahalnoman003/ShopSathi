"""The webhook only accepts Meta's signed requests; login and password reset are rate limited."""

import json

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.integrations.facebook.webhook import sign, verify_signature
from app.models import Message
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"
URL = f"{API}/webhooks/messenger"
SECRET = "test-app-secret"
EVENT = {"object": "page", "entry": [{"id": "nobody", "messaging": [{"sender": {"id": "1"}, "recipient": {"id": "nobody"}, "timestamp": 1, "message": {"mid": "m1", "text": "hi"}}]}]}


def post(client, body: bytes, signature: str | None):
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return client.post(URL, content=body, headers=headers)


# ------------------------------------------------------------------------------------ webhook signature


def test_the_webhook_accepts_only_a_correct_signature(client):
    body = json.dumps(EVENT).encode()
    assert post(client, body, sign(SECRET, body)).status_code == 200
    bad = {
        "no header": None,
        "empty header": "",
        "wrong secret": sign("another-secret", body),
        "sha1 instead of sha256": sign(SECRET, body).replace("sha256=", "sha1="),
        "no prefix": sign(SECRET, body).split("=", 1)[1],
        "uppercase prefix": sign(SECRET, body).replace("sha256=", "SHA256="),
        "truncated": sign(SECRET, body)[:-4],
        "signature of another body": sign(SECRET, body + b" "),
        "zeros": "sha256=" + "0" * 64,
    }
    for name, signature in bad.items():
        assert post(client, body, signature).status_code == 403, name


def test_a_changed_body_is_rejected_even_with_a_valid_signature_of_the_original(client):
    body = json.dumps(EVENT).encode()
    signature = sign(SECRET, body)
    for tampered in (body.replace(b'"hi"', b'"hello"'), body + b"\n", body.replace(b"nobody", b"somebody")):
        assert post(client, tampered, signature).status_code == 403


def test_nothing_is_stored_or_queued_for_an_unsigned_request(client, db):
    body = json.dumps(EVENT).encode()
    for _ in range(5):
        post(client, body, None)
        post(client, body, "sha256=" + "1" * 64)
    assert db.scalars(select(Message)).all() == []


def test_without_a_configured_app_secret_nothing_is_accepted(client, monkeypatch):
    monkeypatch.setenv("FB_APP_SECRET", "")
    get_settings.cache_clear()
    try:
        body = json.dumps(EVENT).encode()
        assert post(client, body, sign("", body)).status_code == 403  # an empty key signs nothing
        assert not verify_signature("", body, sign("", body))
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_the_verification_handshake_needs_the_secret_token(client):
    ok = {"hub.mode": "subscribe", "hub.verify_token": "verify-token-for-tests", "hub.challenge": "42"}
    assert client.get(URL, params=ok).status_code == 200
    for key, value in (("hub.verify_token", "wrong"), ("hub.verify_token", ""), ("hub.mode", "unsubscribe")):
        assert client.get(URL, params={**ok, key: value}).status_code == 403
    assert client.get(URL).status_code == 403


def test_the_webhook_refuses_a_huge_body(client):
    body = b'{"object":"page","pad":"' + b"x" * (2 * 1024 * 1024) + b'"}'
    assert post(client, body, sign(SECRET, body)).status_code == 413


# ------------------------------------------------------------------------------------ rate limits


def test_login_is_rate_limited_per_account(client):
    limit = get_settings().login_rate_limit
    client.post(f"{API}/auth/signup", json={"shop_name": "S", "owner_name": "O", "email": "o@example.com", "password": PASSWORD})
    codes = [client.post(f"{API}/auth/login", json={"email": "o@example.com", "password": f"wrong-password-{i}"}).status_code for i in range(limit + 3)]
    assert codes[:limit].count(401) == limit and set(codes[limit:]) == {429}
    assert client.post(f"{API}/auth/login", json={"email": "o@example.com", "password": PASSWORD}).status_code == 429  # even the right one waits


def test_login_is_rate_limited_per_address_across_accounts(client):
    limit = get_settings().login_rate_limit
    codes = [client.post(f"{API}/auth/login", json={"email": f"user{i}@example.com", "password": "wrong-password-1"}).status_code for i in range(limit + 3)]
    assert 429 in codes and codes[0] == 401  # one address trying many accounts is stopped too


def test_the_rate_limit_window_is_finite(client):
    from app.core.redis import get_redis

    client.post(f"{API}/auth/login", json={"email": "x@example.com", "password": "wrong-password-1"})
    ttls = [get_redis().ttl(k) for k in get_redis().scan_iter(match="rl:login-*")]
    assert ttls and all(0 < t <= get_settings().login_rate_window_seconds for t in ttls)


def test_password_reset_is_rate_limited_and_does_not_reveal_accounts(client, emails):
    client.post(f"{API}/auth/signup", json={"shop_name": "S", "owner_name": "O", "email": "real@example.com", "password": PASSWORD})
    known = client.post(f"{API}/auth/password-reset/request", json={"email": "real@example.com"})
    unknown = client.post(f"{API}/auth/password-reset/request", json={"email": "ghost@example.com"})
    assert known.status_code == unknown.status_code == 200 and known.json() == unknown.json()  # the same answer for both
    assert len(emails.sent) == 1
    limit = get_settings().reset_rate_limit
    codes = [client.post(f"{API}/auth/password-reset/request", json={"email": "real@example.com"}).status_code for _ in range(limit + 2)]
    assert 429 in codes
    assert len(emails.sent) <= limit  # a flood of requests does not flood the inbox


def test_password_reset_tokens_are_single_use_and_not_stored_in_clear(client, db, emails):
    from sqlalchemy import text

    client.post(f"{API}/auth/signup", json={"shop_name": "S", "owner_name": "O", "email": "real@example.com", "password": PASSWORD})
    client.post(f"{API}/auth/password-reset/request", json={"email": "real@example.com"})
    (_, link) = emails.sent[0]
    raw = link.split("token=")[1].split("&")[0]
    stored = [h for (h,) in db.execute(text("select token_hash from password_reset_tokens"))]
    assert stored and raw not in stored  # only a hash of the token is kept
    body = {"token": raw, "new_password": "brand-new-password-1"}
    assert client.post(f"{API}/auth/password-reset/confirm", json=body).status_code == 200
    assert client.post(f"{API}/auth/password-reset/confirm", json={**body, "new_password": "yet-another-password-1"}).status_code in (400, 401, 404, 410, 422)
    assert client.post(f"{API}/auth/login", json={"email": "real@example.com", "password": "brand-new-password-1"}).status_code == 200
    assert client.post(f"{API}/auth/login", json={"email": "real@example.com", "password": PASSWORD}).status_code == 401
