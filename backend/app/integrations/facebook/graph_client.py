"""A small client for Meta's Graph API (used by the Page connection now and by Messenger in Prompt 14).

Secrets never travel in a URL: access tokens go in the ``Authorization`` header and the app secret / OAuth code
in a POST body, so they cannot end up in request logs.
"""

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import get_settings

logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx logs full URLs at INFO

#: what Messenger needs: list the user's Pages, send/receive messages, subscribe the Page's webhook
REQUIRED_PERMISSIONS = ("pages_show_list", "pages_messaging", "pages_manage_metadata")


class GraphAPIError(Exception):
    """Facebook answered with an error (or could not be reached). ``message`` is safe to show to the owner."""

    def __init__(
        self, message: str, code: int | None = None, status_code: int | None = None, subcode: int | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.subcode = subcode


class GraphClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        s = get_settings()
        self.version = s.fb_graph_api_version
        self.base = f"{s.fb_graph_base_url.rstrip('/')}/{self.version}"
        self.dialog_base = s.fb_dialog_base_url.rstrip("/")
        self.app_id = s.fb_app_id
        self.app_secret = s.fb_app_secret
        self.redirect_uri = s.fb_oauth_redirect_uri
        self._client = client or httpx.Client(timeout=15)

    # ------------------------------------------------------------------ plumbing

    def _request(self, method: str, path: str, *, token: str | None = None, params: dict | None = None, data: dict | None = None, json: dict | None = None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            res = self._client.request(method, f"{self.base}{path}", params=params, data=data, json=json, headers=headers)
        except httpx.HTTPError as e:
            raise GraphAPIError("Could not reach Facebook. Please try again.") from e
        try:
            body = res.json()
        except ValueError:
            body = {}
        if res.status_code >= 400 or (isinstance(body, dict) and "error" in body):
            err = body.get("error", {}) if isinstance(body, dict) else {}
            raise GraphAPIError(
                str(err.get("message") or f"Facebook returned an error ({res.status_code})"),
                code=err.get("code"),
                status_code=res.status_code,
                subcode=err.get("error_subcode"),
            )
        return body

    # ------------------------------------------------------------------- OAuth

    def login_url(self, state: str, permissions: tuple[str, ...] = REQUIRED_PERMISSIONS) -> str:
        query = urlencode(
            {
                "client_id": self.app_id,
                "redirect_uri": self.redirect_uri,
                "state": state,
                "scope": ",".join(permissions),
                "response_type": "code",
            }
        )
        return f"{self.dialog_base}/{self.version}/dialog/oauth?{query}"

    def exchange_code(self, code: str) -> str:
        """Authorization code -> short-lived user access token."""
        body = self._request(
            "POST",
            "/oauth/access_token",
            data={"client_id": self.app_id, "client_secret": self.app_secret, "redirect_uri": self.redirect_uri, "code": code},
        )
        return self._token(body)

    def long_lived_user_token(self, short_lived: str) -> str:
        body = self._request(
            "POST",
            "/oauth/access_token",
            data={
                "grant_type": "fb_exchange_token",
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "fb_exchange_token": short_lived,
            },
        )
        return self._token(body)

    @staticmethod
    def _token(body: dict[str, Any]) -> str:
        token = body.get("access_token")
        if not token:
            raise GraphAPIError("Facebook did not return an access token.")
        return str(token)

    def granted_permissions(self, user_token: str) -> set[str]:
        body = self._request("GET", "/me/permissions", token=user_token)
        return {p["permission"] for p in body.get("data", []) if p.get("status") == "granted"}

    # -------------------------------------------------------------------- Pages

    def list_pages(self, user_token: str, max_pages: int = 5) -> list[dict[str, str]]:
        """The Pages the user manages, each with its own Page access token."""
        pages: list[dict[str, str]] = []
        body = self._request("GET", "/me/accounts", token=user_token, params={"fields": "id,name,access_token", "limit": 100})
        for _ in range(max_pages):
            pages += [
                {"id": str(p["id"]), "name": str(p.get("name", "")), "access_token": str(p["access_token"])}
                for p in body.get("data", [])
                if p.get("id") and p.get("access_token")
            ]
            next_url = body.get("paging", {}).get("next")
            if not next_url:
                break
            try:
                res = self._client.get(next_url, headers={"Authorization": f"Bearer {user_token}"})
                body = res.json()
            except (httpx.HTTPError, ValueError) as e:
                raise GraphAPIError("Could not load all your Facebook Pages.") from e
        return pages

    def subscribe_page(self, page_id: str, page_token: str, fields: str = "messages") -> None:
        """Subscribe this app to the Page's webhook fields (Messenger messages)."""
        body = self._request("POST", f"/{page_id}/subscribed_apps", token=page_token, data={"subscribed_fields": fields})
        if body.get("success") is False:
            raise GraphAPIError("Facebook did not accept the webhook subscription.")

    def unsubscribe_page(self, page_id: str, page_token: str) -> None:
        self._request("DELETE", f"/{page_id}/subscribed_apps", token=page_token)

    # ---------------------------------------------------------------- Messenger

    def send_message(self, page_token: str, psid: str, message: dict[str, Any]) -> str | None:
        """Send one message to a customer as a RESPONSE (inside Meta's 24-hour window). Returns Facebook's message id."""
        body = self._request(
            "POST",
            "/me/messages",
            token=page_token,
            json={"recipient": {"id": psid}, "messaging_type": "RESPONSE", "message": message},
        )
        return body.get("message_id")

    def customer_name(self, psid: str, page_token: str) -> str | None:
        """The customer's name, if Facebook gives it with the permissions granted (else None)."""
        body = self._request("GET", f"/{psid}", token=page_token, params={"fields": "first_name,last_name"})
        name = " ".join(x for x in (body.get("first_name"), body.get("last_name")) if x)
        return name or None
