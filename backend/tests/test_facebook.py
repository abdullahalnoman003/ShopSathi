import logging
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
import respx
from sqlalchemy import select

from app.core.config import get_settings
from app.core.crypto import CipherError, TokenCipher
from app.core.redis import get_redis
from app.integrations.facebook.graph_client import GraphAPIError, GraphClient
from app.models import FacebookPage, Shop
from app.services.facebook import _state_key, make_state
from tests.conftest import PASSWORD, auth_header

API = "/api/v1"
GRAPH = "https://graph.facebook.com/v21.0"
FRONTEND = "http://localhost:3000/dashboard/facebook"

SHORT_TOKEN = "SHORT-user-token-aaa111"
LONG_TOKEN = "LONG-user-token-bbb222"
PAGE_TOKEN = "EAAB-page-token-SECRET-ccc333"
OTHER_PAGE_TOKEN = "EAAB-other-page-token-ddd444"
PAGES = [
    {"id": "1001", "name": "Rina Fashion House", "access_token": PAGE_TOKEN},
    {"id": "1002", "name": "Rina Cosmetics", "access_token": OTHER_PAGE_TOKEN},
]
ALL_PERMISSIONS = [{"permission": p, "status": "granted"} for p in ("pages_show_list", "pages_messaging", "pages_manage_metadata", "public_profile")]
SECRETS = (SHORT_TOKEN, LONG_TOKEN, PAGE_TOKEN, OTHER_PAGE_TOKEN)


@pytest.fixture
def graph():
    """Facebook's Graph API, mocked. Nothing in the test suite reaches the real Facebook."""
    with respx.mock(assert_all_called=False) as mock:
        yield mock


def mock_login(graph, pages=PAGES, permissions=ALL_PERMISSIONS):
    def token_endpoint(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        assert form["client_id"] == ["1234567890"] and form["client_secret"] == ["test-app-secret"]
        if form.get("grant_type") == ["fb_exchange_token"]:
            assert form["fb_exchange_token"] == [SHORT_TOKEN]
            return httpx.Response(200, json={"access_token": LONG_TOKEN, "token_type": "bearer"})
        assert form["code"] == ["the-code"] and form["redirect_uri"] == ["http://testserver/api/v1/facebook/callback"]
        return httpx.Response(200, json={"access_token": SHORT_TOKEN, "token_type": "bearer"})

    graph.post(f"{GRAPH}/oauth/access_token").mock(side_effect=token_endpoint)
    graph.get(f"{GRAPH}/me/permissions").mock(return_value=httpx.Response(200, json={"data": permissions}))
    graph.get(f"{GRAPH}/me/accounts").mock(return_value=httpx.Response(200, json={"data": pages}))
    subscribe = graph.post(url__regex=rf"{re.escape(GRAPH)}/\d+/subscribed_apps").mock(return_value=httpx.Response(200, json={"success": True}))
    unsubscribe = graph.delete(url__regex=rf"{re.escape(GRAPH)}/\d+/subscribed_apps").mock(return_value=httpx.Response(200, json={"success": True}))
    return subscribe, unsubscribe


def signup(client, email="a@example.com", shop="Rina Fashion House"):
    r = client.post(
        f"{API}/auth/signup",
        json={"shop_name": shop, "owner_name": "Owner", "email": email, "password": PASSWORD},
    )
    return r.json()["access_token"]


class Recorder:
    """Calls the API and keeps every response body, to prove no token is ever returned."""

    def __init__(self, client):
        self.client, self.bodies = client, []

    def request(self, method, url, **kw):
        r = self.client.request(method, f"{API}{url}", **kw)
        self.bodies.append(r.text)
        return r


def login(rec: Recorder, token: str, code="the-code") -> httpx.Response:
    url = rec.request("GET", "/facebook/connect-url", headers=auth_header(token)).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    return rec.request("GET", "/facebook/callback", params={"code": code, "state": state}, follow_redirects=False)


def connect_flow(rec, token, page_id="1001"):
    assert login(rec, token).headers["location"] == f"{FRONTEND}?status=select"
    return rec.request("POST", "/facebook/pages/connect", json={"page_id": page_id}, headers=auth_header(token))


@pytest.fixture
def owner(client):
    return signup(client)


# --------------------------------------------------------------------- the full flow


def test_full_connect_flow_stores_the_page_token_encrypted(client, owner, graph, db):
    subscribe, _ = mock_login(graph)
    rec, h = Recorder(client), auth_header(owner)

    status = rec.request("GET", "/facebook/page", headers=h).json()
    assert status == {"connected": False, "page": None}

    # 1. the OAuth URL: right app, right redirect, the Messenger permissions, a signed state bound to the shop
    url = rec.request("GET", "/facebook/connect-url", headers=h).json()["url"]
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://www.facebook.com/v21.0/dialog/oauth"
    assert query["client_id"] == ["1234567890"] and query["response_type"] == ["code"]
    assert query["redirect_uri"] == ["http://testserver/api/v1/facebook/callback"]
    assert set(query["scope"][0].split(",")) == {"pages_show_list", "pages_messaging", "pages_manage_metadata"}
    shop_id = db.scalar(select(Shop.id))
    claims = jwt.decode(query["state"][0], _state_key(), algorithms=["HS256"])
    assert claims["sid"] == shop_id and claims["purpose"] == "fb_connect" and claims["exp"] > claims["iat"]

    # 2. Facebook sends the browser back: tokens exchanged, Pages kept short-term, redirect to the selection page
    back = rec.request("GET", "/facebook/callback", params={"code": "the-code", "state": query["state"][0]}, follow_redirects=False)
    assert back.status_code == 302 and back.headers["location"] == f"{FRONTEND}?status=select"
    raw = get_redis().get(f"fb:pages:{shop_id}")
    assert raw and PAGE_TOKEN.encode() not in raw  # even the short-term copy is encrypted
    assert 0 < get_redis().ttl(f"fb:pages:{shop_id}") <= 600

    # 3. the Pages to pick from: names and ids only
    pages = rec.request("GET", "/facebook/pages/available", headers=h).json()
    assert pages == [{"id": "1001", "name": "Rina Fashion House", "in_use": False}, {"id": "1002", "name": "Rina Cosmetics", "in_use": False}]

    # 4. connect one: subscribed to the Page's messages webhook with the Page's own token
    connected = rec.request("POST", "/facebook/pages/connect", json={"page_id": "1001"}, headers=h)
    assert connected.status_code == 200 and connected.json()["id"] == "1001" and connected.json()["name"] == "Rina Fashion House"
    (call,) = subscribe.calls
    assert call.request.url.path.endswith("/1001/subscribed_apps")
    assert parse_qs(call.request.content.decode()) == {"subscribed_fields": ["messages"]}
    assert call.request.headers["authorization"] == f"Bearer {PAGE_TOKEN}"
    assert PAGE_TOKEN not in str(call.request.url)  # tokens are never put in a URL

    # 5. stored encrypted: the raw column is not the token, but decrypts to it
    db.expire_all()
    row = db.scalars(select(FacebookPage)).one()
    assert (row.shop_id, row.page_id, row.page_name) == (shop_id, "1001", "Rina Fashion House") and row.connected_at is not None
    assert row.encrypted_page_token != PAGE_TOKEN and PAGE_TOKEN not in row.encrypted_page_token
    assert TokenCipher().decrypt(row.encrypted_page_token) == PAGE_TOKEN

    # 6. status shows the Page; the pending list (with the other Page's token) is gone
    status = rec.request("GET", "/facebook/page", headers=h).json()
    assert status["connected"] is True and status["page"]["name"] == "Rina Fashion House" and set(status["page"]) == {"id", "name", "connected_at"}
    assert rec.request("GET", "/facebook/pages/available", headers=h).status_code == 404
    assert get_redis().get(f"fb:pages:{shop_id}") is None

    # no response ever contained a token
    for body in rec.bodies:
        assert not any(secret in body for secret in SECRETS)


def test_tokens_are_never_logged(client, owner, graph, caplog):
    mock_login(graph)
    caplog.set_level(logging.DEBUG)
    rec = Recorder(client)
    connect_flow(rec, owner)
    rec.request("POST", "/facebook/page/disconnect", headers=auth_header(owner))
    assert not any(secret in caplog.text for secret in SECRETS)
    assert "test-app-secret" not in caplog.text


def test_disconnect_unsubscribes_and_deletes_the_stored_token(client, owner, graph, db):
    _, unsubscribe = mock_login(graph)
    rec, h = Recorder(client), auth_header(owner)
    connect_flow(rec, owner)

    r = rec.request("POST", "/facebook/page/disconnect", headers=h)
    assert r.status_code == 200 and r.json() == {"disconnected": True}
    (call,) = unsubscribe.calls
    assert call.request.url.path.endswith("/1001/subscribed_apps") and call.request.headers["authorization"] == f"Bearer {PAGE_TOKEN}"
    db.expire_all()
    assert db.scalars(select(FacebookPage)).all() == []  # the encrypted token is gone with the row
    assert rec.request("GET", "/facebook/page", headers=h).json() == {"connected": False, "page": None}
    assert rec.request("POST", "/facebook/page/disconnect", headers=h).status_code == 404


def test_disconnect_still_works_when_facebook_refuses_to_unsubscribe(client, owner, graph, db):
    _, unsubscribe = mock_login(graph)
    connect_flow(Recorder(client), owner)
    unsubscribe.mock(return_value=httpx.Response(400, json={"error": {"message": "Invalid OAuth access token.", "code": 190}}))
    assert client.post(f"{API}/facebook/page/disconnect", headers=auth_header(owner)).status_code == 200
    db.expire_all()
    assert db.scalars(select(FacebookPage)).all() == []


def test_a_disconnected_shop_can_connect_again(client, owner, graph, db):
    mock_login(graph)
    rec = Recorder(client)
    connect_flow(rec, owner)
    rec.request("POST", "/facebook/page/disconnect", headers=auth_header(owner))
    assert connect_flow(rec, owner, "1002").json()["name"] == "Rina Cosmetics"


# ------------------------------------------------------------------ one Page, one shop


def test_a_page_connected_to_another_shop_is_rejected(client, owner, graph, db):
    subscribe, _ = mock_login(graph)
    connect_flow(Recorder(client), owner)
    other = signup(client, "b@example.com", "Shop B")
    rec = Recorder(client)
    assert login(rec, other).headers["location"] == f"{FRONTEND}?status=select"
    listed = rec.request("GET", "/facebook/pages/available", headers=auth_header(other)).json()
    assert {p["id"]: p["in_use"] for p in listed} == {"1001": True, "1002": False}

    subscribed_before = subscribe.call_count
    r = rec.request("POST", "/facebook/pages/connect", json={"page_id": "1001"}, headers=auth_header(other))
    assert r.status_code == 409 and "already connected to another shop" in r.json()["detail"]
    assert subscribe.call_count == subscribed_before  # Facebook was not even asked
    db.expire_all()
    assert [p.page_id for p in db.scalars(select(FacebookPage))] == ["1001"]
    # but shop B can take the other Page
    assert rec.request("POST", "/facebook/pages/connect", json={"page_id": "1002"}, headers=auth_header(other)).status_code == 200


def test_a_shop_can_only_have_one_page(client, owner, graph):
    mock_login(graph)
    rec = Recorder(client)
    connect_flow(rec, owner)
    login(rec, owner)
    r = rec.request("POST", "/facebook/pages/connect", json={"page_id": "1002"}, headers=auth_header(owner))
    assert r.status_code == 409 and "Disconnect it first" in r.json()["detail"]


def test_shops_cannot_see_or_touch_each_others_connection(client, owner, graph, db):
    mock_login(graph)
    connect_flow(Recorder(client), owner)
    other = signup(client, "b@example.com", "Shop B")
    hb = auth_header(other)
    assert client.get(f"{API}/facebook/page", headers=hb).json() == {"connected": False, "page": None}
    assert client.post(f"{API}/facebook/page/disconnect", headers=hb).status_code == 404
    assert client.get(f"{API}/facebook/pages/available", headers=hb).status_code == 404  # B has no pending list
    assert client.post(f"{API}/facebook/pages/connect", json={"page_id": "1001"}, headers=hb).status_code == 404
    db.expire_all()
    assert len(db.scalars(select(FacebookPage)).all()) == 1


def test_a_page_that_was_not_in_the_list_cannot_be_connected(client, owner, graph):
    mock_login(graph)
    rec = Recorder(client)
    login(rec, owner)
    r = rec.request("POST", "/facebook/pages/connect", json={"page_id": "999999"}, headers=auth_header(owner))
    assert r.status_code == 404 and "not in your list" in r.json()["detail"]


def test_facebook_refusing_the_webhook_subscription_connects_nothing(client, owner, graph, db):
    subscribe, _ = mock_login(graph)
    subscribe.mock(return_value=httpx.Response(400, json={"error": {"message": "(#200) Requires pages_manage_metadata", "code": 200}}))
    rec = Recorder(client)
    r = connect_flow(rec, owner)
    assert r.status_code == 502 and "pages_manage_metadata" in r.json()["detail"]
    db.expire_all()
    assert db.scalars(select(FacebookPage)).all() == []


# ------------------------------------------------------------------- the OAuth state


def test_invalid_expired_reused_and_foreign_states_are_rejected(client, owner, graph):
    mock_login(graph)
    rec = Recorder(client)

    def callback(state, **extra):
        return rec.request("GET", "/facebook/callback", params={"code": "the-code", "state": state, **extra}, follow_redirects=False).headers["location"]

    good = make_state(1, 1)
    assert callback("not-a-jwt") == f"{FRONTEND}?error=state_invalid"
    assert callback(good[:-3] + "xyz") == f"{FRONTEND}?error=state_invalid"  # tampered signature
    assert rec.request("GET", "/facebook/callback", params={"code": "the-code"}, follow_redirects=False).headers["location"] == f"{FRONTEND}?error=state_invalid"

    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode({"purpose": "fb_connect", "sid": 1, "uid": 1, "nonce": "n1", "exp": past}, _state_key(), algorithm="HS256")
    assert callback(expired) == f"{FRONTEND}?error=state_expired"

    # a normal login token is not a valid state, and a state signed for another purpose is refused
    assert callback(owner) == f"{FRONTEND}?error=state_invalid"
    other_purpose = jwt.encode({"purpose": "x", "sid": 1, "nonce": "n2", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, _state_key(), algorithm="HS256")
    assert callback(other_purpose) == f"{FRONTEND}?error=state_invalid"

    assert callback(good) == f"{FRONTEND}?status=select"
    assert callback(good) == f"{FRONTEND}?error=state_invalid"  # a state works once


def test_nothing_is_stored_when_the_state_is_bad(client, owner, graph):
    mock_login(graph)
    client.get(f"{API}/facebook/callback", params={"code": "the-code", "state": "bad"}, follow_redirects=False)
    assert client.get(f"{API}/facebook/pages/available", headers=auth_header(owner)).status_code == 404
    assert not graph.calls  # Facebook was not contacted with an unverified request


# ------------------------------------------------------------------ errors on the way


def test_denied_login(client, owner, graph):
    mock_login(graph)
    state = parse_qs(urlparse(client.get(f"{API}/facebook/connect-url", headers=auth_header(owner)).json()["url"]).query)["state"][0]
    r = client.get(f"{API}/facebook/callback", params={"error": "access_denied", "error_reason": "user_denied", "state": state}, follow_redirects=False)
    assert r.headers["location"] == f"{FRONTEND}?error=denied"
    assert not graph.calls


def test_missing_permissions(client, owner, graph):
    declined = [{"permission": "pages_show_list", "status": "granted"}, {"permission": "pages_messaging", "status": "declined"}, {"permission": "pages_manage_metadata", "status": "granted"}]
    mock_login(graph, permissions=declined)
    assert login(Recorder(client), owner).headers["location"] == f"{FRONTEND}?error=permissions_missing"


def test_no_pages_to_manage(client, owner, graph):
    mock_login(graph, pages=[])
    assert login(Recorder(client), owner).headers["location"] == f"{FRONTEND}?error=no_pages"


def test_facebook_errors_during_login(client, owner, graph):
    mock_login(graph)
    graph.post(f"{GRAPH}/oauth/access_token").mock(return_value=httpx.Response(400, json={"error": {"message": "Invalid verification code format.", "code": 100}}))
    assert login(Recorder(client), owner).headers["location"] == f"{FRONTEND}?error=facebook_error"
    graph.post(f"{GRAPH}/oauth/access_token").mock(side_effect=httpx.ConnectError("down"))
    assert login(Recorder(client), owner).headers["location"] == f"{FRONTEND}?error=facebook_error"


def test_missing_app_configuration_is_explained(client, owner, monkeypatch):
    monkeypatch.setenv("FB_APP_ID", "")
    monkeypatch.setenv("FB_TOKEN_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    try:
        r = client.get(f"{API}/facebook/connect-url", headers=auth_header(owner))
        assert r.status_code == 503 and "FB_APP_ID" in r.json()["detail"] and "FB_TOKEN_ENCRYPTION_KEY" in r.json()["detail"]
        back = client.get(f"{API}/facebook/callback", params={"code": "c", "state": "s"}, follow_redirects=False)
        assert back.headers["location"] == f"{FRONTEND}?error=not_configured"
        assert client.post(f"{API}/facebook/pages/connect", json={"page_id": "1"}, headers=auth_header(owner)).status_code == 503
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_an_invalid_encryption_key_is_reported_not_crashed(client, owner, monkeypatch):
    monkeypatch.setenv("FB_TOKEN_ENCRYPTION_KEY", "not-a-fernet-key")
    get_settings.cache_clear()
    try:
        r = client.get(f"{API}/facebook/connect-url", headers=auth_header(owner))
        assert r.status_code == 503 and "not a valid Fernet key" in r.json()["detail"]
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


# ------------------------------------------------------------------------ access


def test_only_the_owner_can_use_the_facebook_endpoints(client, owner):
    client.post(f"{API}/shop/staff", json={"email": "mod@example.com", "full_name": "Mod", "password": PASSWORD}, headers=auth_header(owner))
    mod = auth_header(client.post(f"{API}/auth/login", json={"email": "mod@example.com", "password": PASSWORD}).json()["access_token"])
    for method, url, body in [
        ("GET", "/facebook/connect-url", None),
        ("GET", "/facebook/pages/available", None),
        ("POST", "/facebook/pages/connect", {"page_id": "1001"}),
        ("GET", "/facebook/page", None),
        ("POST", "/facebook/page/disconnect", None),
    ]:
        assert client.request(method, f"{API}{url}", json=body, headers=mod).status_code == 403, url
        assert client.request(method, f"{API}{url}", json=body).status_code == 401, url


# ------------------------------------------------------------- cipher and Graph client


def test_token_cipher():
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    cipher = TokenCipher(key)
    a, b = cipher.encrypt("secret-token"), cipher.encrypt("secret-token")
    assert a != b and "secret-token" not in a  # fresh randomness each time
    assert cipher.decrypt(a) == cipher.decrypt(b) == "secret-token"
    with pytest.raises(CipherError):
        TokenCipher(Fernet.generate_key().decode()).decrypt(a)  # wrong key
    with pytest.raises(CipherError):
        TokenCipher("")
    with pytest.raises(CipherError):
        TokenCipher("short")
    with pytest.raises(CipherError):
        cipher.decrypt("garbage")


def test_graph_client_follows_paging_and_parses_errors(graph):
    # the more specific route first: respx uses the first route that matches
    graph.get(f"{GRAPH}/me/accounts", params={"after": "abc"}).mock(return_value=httpx.Response(200, json={"data": [PAGES[1], {"id": "1003", "name": "No token"}]}))
    graph.get(f"{GRAPH}/me/accounts").mock(
        return_value=httpx.Response(200, json={"data": [PAGES[0]], "paging": {"next": f"{GRAPH}/me/accounts?after=abc"}})
    )
    pages = GraphClient().list_pages(LONG_TOKEN)
    assert [p["id"] for p in pages] == ["1001", "1002"]  # a Page without a Page token is skipped
    for call in graph.calls:
        assert call.request.headers["authorization"] == f"Bearer {LONG_TOKEN}" and LONG_TOKEN not in str(call.request.url)

    graph.get(f"{GRAPH}/me/permissions").mock(return_value=httpx.Response(401, json={"error": {"message": "Session has expired", "code": 190}}))
    with pytest.raises(GraphAPIError) as e:
        GraphClient().granted_permissions(LONG_TOKEN)
    assert e.value.message == "Session has expired" and e.value.code == 190
