"""NFR-03 and the login basics: passwords are bcrypt hashes, tokens are really verified, logout revokes."""

import base64
import json
import time

import bcrypt
import jwt
import pytest
from sqlalchemy import select, text

from app.core.config import get_settings
from app.models import Shop, User
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"


def b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).rstrip(b"=").decode()


def make_owner(client, email="owner@example.com", shop="Shop A"):
    r = client.post(f"{API}/auth/signup", json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD})
    assert r.status_code == 201
    return r.json()["access_token"]


def me(client, token):
    return client.get(f"{API}/auth/me", headers=auth_header(token))


# ------------------------------------------------------------------------------------ passwords


def test_passwords_are_stored_as_bcrypt_hashes_never_as_text(client, db):
    make_owner(client, "a@example.com", "Shop A")
    make_owner(client, "b@example.com", "Shop B")
    hashes = [h for (h,) in db.execute(text("select password_hash from users order by id"))]
    for h in hashes:
        assert h.startswith("$2") and len(h) == 60 and PASSWORD not in h
        assert bcrypt.checkpw(PASSWORD.encode(), h.encode())
        assert not bcrypt.checkpw(b"another-password-1", h.encode())
    assert hashes[0] != hashes[1]  # salted: the same password gives a different hash
    assert int(hashes[0].split("$")[2]) >= 10


def test_no_response_contains_a_password_or_its_hash(client, db):
    token = make_owner(client)
    client.post(f"{API}/shop/staff", json={"email": "mod@example.com", "full_name": "Mod", "password": "moderator-pass-1"}, headers=auth_header(token))
    h = db.scalar(select(User.password_hash).where(User.email == "owner@example.com"))
    bodies = [
        client.post(f"{API}/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).text,
        client.post(f"{API}/auth/login", json={"email": "owner@example.com", "password": "wrong-password-1"}).text,
        me(client, token).text,
        client.get(f"{API}/shop/staff", headers=auth_header(token)).text,
    ]
    for body in bodies:
        assert h not in body and "$2b$" not in body and PASSWORD not in body and "moderator-pass-1" not in body and "password_hash" not in body


def test_login_does_not_reveal_whether_an_account_exists(client):
    make_owner(client)
    wrong_pw = client.post(f"{API}/auth/login", json={"email": "owner@example.com", "password": "wrong-password-1"})
    unknown = client.post(f"{API}/auth/login", json={"email": "nobody@example.com", "password": "wrong-password-1"})
    assert wrong_pw.status_code == unknown.status_code == 401 and wrong_pw.json() == unknown.json()


# ------------------------------------------------------------------------------------ tokens


def claims(token):
    return jwt.decode(token, options={"verify_signature": False})


def test_a_valid_token_is_signed_hs256_and_carries_no_secrets(client):
    token = make_owner(client)
    assert jwt.get_unverified_header(token)["alg"] == "HS256"
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    assert set(payload) >= {"sub", "role", "shop_id", "jti", "exp", "iat"}
    assert not ({"password", "password_hash", "email"} & set(payload))
    assert payload["exp"] - payload["iat"] == get_settings().access_token_expire_minutes * 60


def test_tampered_forged_and_expired_tokens_are_rejected(client):
    token = make_owner(client)
    header, payload, signature = token.split(".")
    good = claims(token)
    secret = get_settings().jwt_secret

    forged = {
        "role changed to admin, signature kept": f"{header}.{b64({**good, 'role': 'platform_admin', 'shop_id': None})}.{signature}",
        "signature bit flipped": f"{header}.{payload}.{signature[:-2]}{'A' if signature[-2] != 'A' else 'B'}{signature[-1]}",
        "signature removed": f"{header}.{payload}.",
        "alg none": f"{b64({'alg': 'none', 'typ': 'JWT'})}.{payload}.",
        "alg none with a role of admin": f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({**good, 'role': 'platform_admin', 'shop_id': None})}.",
        "signed with another secret": jwt.encode(good, "not-the-secret-not-the-secret-123456", algorithm="HS256"),
        "another algorithm, right secret (HS512)": jwt.encode(good, secret, algorithm="HS512"),
        "expired an hour ago": jwt.encode({**good, "exp": int(time.time()) - 3600}, secret, algorithm="HS256"),
        "no expiry": jwt.encode({k: v for k, v in good.items() if k != "exp"}, secret, algorithm="HS256"),
        "no subject": jwt.encode({k: v for k, v in good.items() if k != "sub"}, secret, algorithm="HS256"),
        "no id": jwt.encode({k: v for k, v in good.items() if k != "jti"}, secret, algorithm="HS256"),
        "garbage": "not.a.token",
        "empty": "",
        "two parts": f"{header}.{payload}",
    }
    for name, bad in forged.items():
        r = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401, f"{name}: {r.status_code}"
    assert me(client, token).status_code == 200  # the real one still works
    assert client.get(f"{API}/auth/me", headers={"Authorization": token}).status_code == 401  # not a Bearer header
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Basic {token}"}).status_code == 401


def test_a_token_for_a_user_that_no_longer_exists_or_is_disabled_is_rejected(client, db):
    token = make_owner(client)
    db.execute(text("update users set is_active = false"))
    db.commit()
    assert me(client, token).status_code == 401
    db.execute(text("update users set is_active = true"))
    db.commit()
    assert me(client, token).status_code == 200
    db.execute(text("delete from users"))
    db.commit()
    assert me(client, token).status_code == 401


def test_the_role_comes_from_the_database_not_from_the_token(client, db):
    """A token whose role claim says admin but whose user is an owner must not become an admin (the claim is only a copy)."""
    token = make_owner(client)
    good = claims(token)
    signed_with_admin_claim = jwt.encode({**good, "role": "platform_admin"}, get_settings().jwt_secret, algorithm="HS256")
    assert client.get(f"{API}/admin/shops", headers=auth_header(signed_with_admin_claim)).status_code == 403


def test_logout_revokes_the_token_but_not_the_other_sessions(client):
    first = make_owner(client)
    second = client.post(f"{API}/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).json()["access_token"]
    assert me(client, first).status_code == 200 and me(client, second).status_code == 200
    assert client.post(f"{API}/auth/logout", headers=auth_header(first)).status_code == 200
    assert me(client, first).status_code == 401
    assert client.get(f"{API}/products", headers=auth_header(first)).status_code == 401  # every endpoint, not only /me
    assert me(client, second).status_code == 200
    assert client.post(f"{API}/auth/logout", headers=auth_header(first)).status_code == 401  # a revoked token cannot do anything


def test_a_suspended_shop_loses_access_with_its_existing_tokens(client, db):
    token = make_owner(client)
    db.execute(text("update shops set status = 'suspended'"))
    db.commit()
    assert me(client, token).status_code == 403
    assert client.post(f"{API}/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).status_code == 403


def test_the_jwt_secret_is_required_and_not_a_placeholder():
    secret = get_settings().jwt_secret
    assert len(secret) >= 32, "JWT_SECRET should be a long random string (python -c \"import secrets; print(secrets.token_urlsafe(48))\")"
    assert secret.lower() not in {"change-me", "changeme", "secret", "jwt_secret", "your-secret-here"}
