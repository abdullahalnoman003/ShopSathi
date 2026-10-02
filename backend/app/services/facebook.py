"""Connecting a shop's Facebook Page (FR-07) through Facebook Login.

Flow: the owner is sent to Facebook with a signed, expiring ``state`` bound to the shop -> Facebook sends the
browser back to /api/v1/facebook/callback -> we exchange the code for a long-lived user token, list the Pages
the user manages and keep them for a few minutes in Redis (encrypted) -> the owner picks one -> we store its
Page token encrypted and subscribe the app to the Page's ``messages`` webhook.
Page tokens are never logged and never returned by any API.
"""

import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import CipherError, TokenCipher
from app.core.redis import get_redis
from app.integrations.facebook.graph_client import REQUIRED_PERMISSIONS, GraphAPIError, GraphClient
import logging
from app.models import FacebookPage

logger = logging.getLogger("shopsathi.facebook")

STATE_TTL = timedelta(minutes=10)
PENDING_TTL_SECONDS = 600
STATE_PURPOSE = "fb_connect"


class FacebookError(Exception):
    """A problem to show to the owner. ``code`` is stable (the frontend maps it), ``message`` is readable."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


def missing_config() -> list[str]:
    s = get_settings()
    names = {
        "FB_APP_ID": s.fb_app_id,
        "FB_APP_SECRET": s.fb_app_secret,
        "FB_OAUTH_REDIRECT_URI": s.fb_oauth_redirect_uri,
        "FB_TOKEN_ENCRYPTION_KEY": s.fb_token_encryption_key,
    }
    return [name for name, value in names.items() if not value]


def ensure_configured() -> TokenCipher:
    missing = missing_config()
    if missing:
        raise FacebookError(
            "not_configured",
            f"Facebook is not set up on this server. Missing settings: {', '.join(missing)}.",
            503,
        )
    try:
        return TokenCipher()
    except CipherError as e:
        raise FacebookError("not_configured", f"Facebook is not set up on this server: {e}.", 503) from e


# ---------------------------------------------------------------------- state


def _state_key() -> str:
    # not the access-token key: a login token can never be used as a state, and the reverse
    return f"fb-state:{get_settings().jwt_secret}"


def make_state(shop_id: int, user_id: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"purpose": STATE_PURPOSE, "sid": shop_id, "uid": user_id, "nonce": secrets.token_urlsafe(12), "iat": now, "exp": now + STATE_TTL},
        _state_key(),
        algorithm="HS256",
    )


def read_state(state: str | None) -> dict:
    if not state:
        raise FacebookError("state_invalid", "The Facebook login link is not valid. Please start again.")
    try:
        claims = jwt.decode(state, _state_key(), algorithms=["HS256"], options={"require": ["exp", "sid", "nonce"]})
    except jwt.ExpiredSignatureError as e:
        raise FacebookError("state_expired", "The Facebook login took too long. Please start again.") from e
    except jwt.PyJWTError as e:
        raise FacebookError("state_invalid", "The Facebook login link is not valid. Please start again.") from e
    if claims.get("purpose") != STATE_PURPOSE:
        raise FacebookError("state_invalid", "The Facebook login link is not valid. Please start again.")
    return claims


def _pending_key(shop_id: int) -> str:
    return f"fb:pages:{shop_id}"


class FacebookService:
    def __init__(self, db: Session, graph: GraphClient | None = None) -> None:
        self.db = db
        self._graph = graph
        self.redis = get_redis()

    @property
    def graph(self) -> GraphClient:
        if self._graph is None:
            self._graph = GraphClient()
        return self._graph

    # ---------------------------------------------------------------- login

    def connect_url(self, shop_id: int, user_id: int) -> str:
        ensure_configured()
        return self.graph.login_url(make_state(shop_id, user_id))

    @staticmethod
    def frontend_page() -> str:
        s = get_settings()
        return f"{(s.frontend_url or s.frontend_origin).rstrip('/')}/dashboard/facebook"

    def handle_callback(self, *, code: str | None, state: str | None, error: str | None) -> str:
        """Finish the login after Facebook sent the browser back. Returns the frontend URL to redirect to:
        ``?status=select`` on success, ``?error=<code>`` otherwise."""
        base = self.frontend_page()

        def fail(code_: str) -> str:
            return f"{base}?{urlencode({'error': code_})}"

        try:
            cipher = ensure_configured()
            claims = read_state(state)
            # a state works once
            if not self.redis.set(f"fb:state:{claims['nonce']}", 1, ex=int(STATE_TTL.total_seconds()) + 60, nx=True):
                raise FacebookError("state_invalid", "This Facebook login link was already used. Please start again.")
            if error or not code:
                return fail("denied")
            user_token = self.graph.long_lived_user_token(self.graph.exchange_code(code))
            if not set(REQUIRED_PERMISSIONS) <= self.graph.granted_permissions(user_token):
                return fail("permissions_missing")
            pages = self.graph.list_pages(user_token)
            if not pages:
                return fail("no_pages")
            blob = cipher.encrypt(json.dumps({"pages": pages}))
            self.redis.set(_pending_key(int(claims["sid"])), blob, ex=PENDING_TTL_SECONDS)
            return f"{base}?status=select"
        except FacebookError as e:
            return fail(e.code)
        except GraphAPIError as e:
            # the message comes from Facebook and holds no secret; it tells the developer what to fix (for example the redirect URI or the app type)
            logger.warning("Facebook login callback failed: code=%s subcode=%s message=%s", e.code, getattr(e, "subcode", None), e)
            return fail("facebook_error")

    # ---------------------------------------------------------------- pages

    def _pending_pages(self, shop_id: int) -> list[dict[str, str]]:
        cipher = ensure_configured()
        raw = self.redis.get(_pending_key(shop_id))
        if not raw:
            raise FacebookError("selection_expired", "The Page list expired. Please connect to Facebook again.", 404)
        return json.loads(cipher.decrypt(raw.decode() if isinstance(raw, bytes) else raw))["pages"]

    def available_pages(self, shop_id: int) -> list[dict]:
        """Name and id of the Pages the owner may pick (never the tokens)."""
        pages = self._pending_pages(shop_id)
        in_use = set(self.db.scalars(select(FacebookPage.page_id).where(FacebookPage.page_id.in_([p["id"] for p in pages]))))
        return [{"id": p["id"], "name": p["name"], "in_use": p["id"] in in_use} for p in pages]

    def connect(self, shop_id: int, page_id: str) -> FacebookPage:
        cipher = ensure_configured()
        if self.db.scalar(select(FacebookPage.id).where(FacebookPage.shop_id == shop_id)) is not None:
            raise FacebookError("already_connected", "A Facebook Page is already connected. Disconnect it first.", 409)
        page = next((p for p in self._pending_pages(shop_id) if p["id"] == page_id), None)
        if page is None:
            raise FacebookError("page_not_found", "That Page is not in your list.", 404)
        if self.db.scalar(select(FacebookPage.id).where(FacebookPage.page_id == page_id)) is not None:
            raise FacebookError("page_in_use", "This Facebook Page is already connected to another shop.", 409)
        try:
            self.graph.subscribe_page(page_id, page["access_token"], "messages")
        except GraphAPIError as e:
            raise FacebookError("subscribe_failed", f"Facebook could not subscribe ShopSathi to this Page: {e.message}", 502) from e
        row = FacebookPage(
            shop_id=shop_id,
            page_id=page_id,
            page_name=page["name"],
            encrypted_page_token=cipher.encrypt(page["access_token"]),
        )
        self.db.add(row)
        try:
            self.db.commit()
        except IntegrityError as e:
            self.db.rollback()
            raise FacebookError("page_in_use", "This Facebook Page is already connected to another shop.", 409) from e
        self.redis.delete(_pending_key(shop_id))  # the other Pages' tokens are not needed any more
        return row

    # ---------------------------------------------------------------- status

    def get_page(self, shop_id: int) -> FacebookPage | None:
        return self.db.scalars(select(FacebookPage).where(FacebookPage.shop_id == shop_id)).first()

    def disconnect(self, shop_id: int) -> None:
        row = self.get_page(shop_id)
        if row is None:
            raise FacebookError("not_connected", "No Facebook Page is connected.", 404)
        try:  # best effort: the Page may have been removed or the token revoked on Facebook's side
            self.graph.unsubscribe_page(row.page_id, TokenCipher().decrypt(row.encrypted_page_token))
        except (GraphAPIError, CipherError):
            pass
        self.db.delete(row)
        self.db.commit()
        self.redis.delete(_pending_key(shop_id))
