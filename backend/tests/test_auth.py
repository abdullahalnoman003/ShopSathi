from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.cli import main as cli_main
from app.core.security import hash_reset_token
from app.models import PasswordResetToken, Shop, User
from tests.conftest import PASSWORD, auth_header

API = "/api/v1/auth"


def login(client, email="a@example.com", password=PASSWORD):
    return client.post(f"{API}/login", json={"email": email, "password": password})


def test_signup_creates_shop_and_owner(signup, db):
    r = signup()
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["role"] == "owner"
    assert body["shop"]["name"] == "Shop A"
    assert body["shop"]["status"] == "active"
    assert body["user"]["shop_id"] == body["shop"]["id"]
    assert body["access_token"]
    assert db.scalar(select(Shop.id)) is not None


def test_password_is_stored_hashed(signup, db):
    signup()
    user = db.scalar(select(User))
    assert user.password_hash != PASSWORD
    assert user.password_hash.startswith("$2")


def test_signup_validation(signup):
    assert signup(email="a@example.com").status_code == 201
    assert signup(email="A@Example.com").status_code == 409  # duplicate, case-insensitive
    assert signup(email="not-an-email").status_code == 422
    short = signup(email="b@example.com", password="short")
    assert short.status_code == 422
    assert "at least" in str(short.json()["detail"])


def test_login_success_and_failure(signup, client):
    signup()
    ok = login(client)
    assert ok.status_code == 200
    assert ok.json()["access_token"]
    assert login(client, password="wrong-password").status_code == 401
    assert login(client, email="nobody@example.com").status_code == 401


def test_me_requires_token(signup, client):
    token = signup().json()["access_token"]
    assert client.get(f"{API}/me").status_code == 401
    r = client.get(f"{API}/me", headers=auth_header(token))
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "a@example.com"
    assert r.json()["shop"]["name"] == "Shop A"


def test_logout_revokes_token(signup, client):
    token = signup().json()["access_token"]
    h = auth_header(token)
    assert client.post(f"{API}/logout", headers=h).status_code == 200
    r = client.get(f"{API}/me", headers=h)
    assert r.status_code == 401
    assert "revoked" in r.json()["detail"]


def test_password_reset_flow(signup, client, emails, db):
    signup()
    r = client.post(f"{API}/password-reset/request", json={"email": "a@example.com"})
    assert r.status_code == 200
    assert len(emails.sent) == 1
    to, link = emails.sent[0]
    assert to == "a@example.com"
    token = link.split("token=")[1]
    # only the hash is stored
    assert db.scalar(select(PasswordResetToken.token_hash)) == hash_reset_token(token)

    new_pw = "brand-new-pass-2"
    assert client.post(f"{API}/password-reset/confirm", json={"token": token, "new_password": new_pw}).status_code == 200
    assert login(client, password=new_pw).status_code == 200
    assert login(client).status_code == 401
    # single use
    again = client.post(f"{API}/password-reset/confirm", json={"token": token, "new_password": "another-pass-3"})
    assert again.status_code == 400


def test_password_reset_request_same_response_for_unknown_email(signup, client, emails):
    signup()
    known = client.post(f"{API}/password-reset/request", json={"email": "a@example.com"})
    unknown = client.post(f"{API}/password-reset/request", json={"email": "ghost@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert len(emails.sent) == 1


def test_password_reset_token_expires(signup, client, emails, db):
    signup()
    client.post(f"{API}/password-reset/request", json={"email": "a@example.com"})
    token = emails.sent[0][1].split("token=")[1]
    row = db.scalar(select(PasswordResetToken))
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    r = client.post(f"{API}/password-reset/confirm", json={"token": token, "new_password": "another-pass-3"})
    assert r.status_code == 400
    assert client.post(f"{API}/password-reset/confirm", json={"token": "bogus", "new_password": "another-pass-3"}).status_code == 400


def test_suspended_shop_cannot_log_in_or_use_api(signup, client, db):
    token = signup().json()["access_token"]
    db.scalar(select(Shop)).status = "suspended"
    db.commit()
    r = login(client)
    assert r.status_code == 403
    assert r.json()["detail"] == "Shop suspended"
    # an already-issued token stops working too
    r = client.get(f"{API}/me", headers=auth_header(token))
    assert r.status_code == 403
    assert r.json()["detail"] == "Shop suspended"


def test_login_rate_limit(signup, client, monkeypatch):
    monkeypatch.setenv("LOGIN_RATE_LIMIT", "3")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        signup()
        codes = [login(client, password="bad-password").status_code for _ in range(5)]
        assert codes == [401, 401, 401, 429, 429]
    finally:
        monkeypatch.delenv("LOGIN_RATE_LIMIT")
        get_settings.cache_clear()


def test_create_admin_cli(db, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-password-1")
    assert cli_main(["create-admin", "--email", "Admin@Example.com"]) == 0
    admin = db.scalar(select(User).where(User.email == "admin@example.com"))
    assert admin.role == "platform_admin" and admin.shop_id is None
    assert cli_main(["create-admin", "--email", "admin@example.com"]) == 1  # duplicate


def test_seed_is_idempotent(db, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "demo-password-1")
    assert cli_main(["seed"]) == 0
    n = len(db.scalars(select(User)).all())
    assert n >= 1
    assert cli_main(["seed"]) == 0
    db.expire_all()
    assert len(db.scalars(select(User)).all()) == n
