"""A FAKE Facebook for local development and demos. It is NOT Facebook: it answers the few Graph API calls the
Page connection makes, with made-up users, Pages and tokens, so the whole flow can be tried without a Meta app.

    uvicorn scripts.fake_facebook:app --port 8099        (run from backend/)

and start the backend with
    FB_GRAPH_BASE_URL=http://localhost:8099 FB_DIALOG_BASE_URL=http://localhost:8099
    FB_APP_ID=fake-app FB_APP_SECRET=fake-secret FB_TOKEN_ENCRYPTION_KEY=<a Fernet key>
    FB_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/facebook/callback

Behaviour switches (environment variables of this process):
    FAKE_FB_DENY=1                the "user" cancels the login
    FAKE_FB_MISSING_PERMISSION=1  the "user" declines pages_messaging
    FAKE_FB_NO_PAGES=1            the "user" manages no Page
Inspect what the app subscribed to at GET /_debug/subscriptions and what it sent to customers at GET /_debug/messages.
POST /_debug/fail-sends/N makes the next N Send API calls fail with a temporary error.
"""

import os
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

app = FastAPI(title="Fake Facebook (development only)")

PAGES = [
    {"id": "900001", "name": "Demo Fashion Page", "access_token": "FAKE-PAGE-TOKEN-fashion"},
    {"id": "900002", "name": "Demo Gadget Page", "access_token": "FAKE-PAGE-TOKEN-gadget"},
]
subscriptions: dict[str, str] = {}  # page id -> subscribed fields
sent_messages: list[dict] = []  # what the app sent through the Send API (newest last)
FAIL_SENDS = {"left": 0}  # POST /_debug/fail-sends/{n}: the next n sends fail with a temporary error


def _error(message: str, code: int = 190, status: int = 400):
    raise HTTPException(status, detail={"error": {"message": message, "code": code, "type": "OAuthException"}})


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        _error("An active access token must be used to query information about the current user.")
    return authorization.split(" ", 1)[1]


@app.exception_handler(HTTPException)
async def graph_errors(_, exc: HTTPException):
    from fastapi.responses import JSONResponse

    return JSONResponse(exc.detail if isinstance(exc.detail, dict) else {"error": {"message": str(exc.detail)}}, status_code=exc.status_code)


@app.get("/{version}/dialog/oauth")
def dialog(version: str, redirect_uri: str, state: str, client_id: str = "", scope: str = "", response_type: str = "code"):
    """The Facebook Login screen, auto-approved: sends the browser straight back with a code."""
    if os.environ.get("FAKE_FB_DENY"):
        query = {"error": "access_denied", "error_reason": "user_denied", "error_description": "The user denied your request.", "state": state}
    else:
        query = {"code": "fake-auth-code", "state": state}
    return RedirectResponse(f"{redirect_uri}?{urlencode(query)}", status_code=302)


@app.post("/{version}/oauth/access_token")
def access_token(version: str, grant_type: str = Form(default=""), code: str = Form(default=""), fb_exchange_token: str = Form(default=""), client_id: str = Form(default=""), client_secret: str = Form(default="")):
    if not client_id or not client_secret:
        _error("Missing client_id or client_secret", 101)
    if grant_type == "fb_exchange_token":
        if fb_exchange_token != "FAKE-SHORT-USER-TOKEN":
            _error("Invalid OAuth access token.")
        return {"access_token": "FAKE-LONG-USER-TOKEN", "token_type": "bearer", "expires_in": 5183944}
    if code != "fake-auth-code":
        _error("Invalid verification code format.", 100)
    return {"access_token": "FAKE-SHORT-USER-TOKEN", "token_type": "bearer", "expires_in": 3600}


@app.get("/{version}/me/permissions")
def permissions(version: str, authorization: str | None = Header(default=None)):
    if _bearer(authorization) != "FAKE-LONG-USER-TOKEN":
        _error("Invalid OAuth access token.")
    declined = {"pages_messaging"} if os.environ.get("FAKE_FB_MISSING_PERMISSION") else set()
    names = ["public_profile", "pages_show_list", "pages_messaging", "pages_manage_metadata"]
    return {"data": [{"permission": n, "status": "declined" if n in declined else "granted"} for n in names]}


@app.get("/{version}/me/accounts")
def accounts(version: str, authorization: str | None = Header(default=None), fields: str = Query(default=""), limit: int = 25):
    if _bearer(authorization) != "FAKE-LONG-USER-TOKEN":
        _error("Invalid OAuth access token.")
    return {"data": [] if os.environ.get("FAKE_FB_NO_PAGES") else PAGES}


@app.post("/{version}/{page_id}/subscribed_apps")
def subscribe(version: str, page_id: str, subscribed_fields: str = Form(default=""), authorization: str | None = Header(default=None)):
    page = next((p for p in PAGES if p["id"] == page_id), None)
    if page is None or _bearer(authorization) != page["access_token"]:
        _error("Invalid OAuth access token.")
    subscriptions[page_id] = subscribed_fields
    return {"success": True}


@app.delete("/{version}/{page_id}/subscribed_apps")
def unsubscribe(version: str, page_id: str, authorization: str | None = Header(default=None)):
    page = next((p for p in PAGES if p["id"] == page_id), None)
    if page is None or _bearer(authorization) != page["access_token"]:
        _error("Invalid OAuth access token.")
    subscriptions.pop(page_id, None)
    return {"success": True}


@app.get("/_debug/subscriptions")
def debug_subscriptions():
    return subscriptions


@app.get("/_debug/messages")
def debug_messages():
    return sent_messages


@app.post("/_debug/fail-sends/{n}")
def debug_fail_sends(n: int):
    FAIL_SENDS["left"] = n
    return FAIL_SENDS


@app.post("/_debug/reset")
def debug_reset():
    sent_messages.clear()
    FAIL_SENDS["left"] = 0
    return {"ok": True}


@app.post("/{version}/me/messages")
async def send_api(version: str, request: Request, authorization: str | None = Header(default=None)):
    """The Send API: accepts a message for a customer from a connected Page (identified by its Page token)."""
    token = _bearer(authorization)
    page = next((p for p in PAGES if p["access_token"] == token), None)
    if page is None:
        _error("Invalid OAuth access token.")
    body = await request.json()
    if FAIL_SENDS["left"] > 0:
        FAIL_SENDS["left"] -= 1
        _error("An unexpected error has occurred. Please retry your request later.", 2, 500)
    if body.get("messaging_type") != "RESPONSE" or not body.get("recipient", {}).get("id") or not body.get("message"):
        _error("(#100) Invalid parameter", 100)
    sent_messages.append({"page_id": page["id"], "recipient": body["recipient"]["id"], "messaging_type": body["messaging_type"], "message": body["message"]})
    return {"recipient_id": body["recipient"]["id"], "message_id": f"m_fake_{len(sent_messages)}"}


@app.get("/{version}/{psid}")
def user_profile(version: str, psid: str, fields: str = Query(default=""), authorization: str | None = Header(default=None)):
    """A customer's profile (name) for a Page-scoped id."""
    token = _bearer(authorization)
    if not any(p["access_token"] == token for p in PAGES):
        _error("Invalid OAuth access token.")
    return {"id": psid, "first_name": "Test", "last_name": f"Customer {psid[-4:]}"}
