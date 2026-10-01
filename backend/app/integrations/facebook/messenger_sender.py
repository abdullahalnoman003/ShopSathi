"""Sending messages to customers through the Messenger Send API, following Meta's rules.

* Every message is sent as ``messaging_type: RESPONSE`` and only **within 24 hours of the customer's last
  message** (NFR-09). The window check is built into every send function: outside it, nothing is sent.
* Temporary Facebook errors are retried a few times; permanent ones (window closed, bad token, ...) are not.
* Page tokens are decrypted only for the call and never logged.

Prompt 15 (the seller's manual replies) MUST send through this module so the same rules apply.
"""

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.crypto import CipherError, TokenCipher
from app.integrations.facebook.graph_client import GraphAPIError, GraphClient
from app.models import FacebookPage

logger = logging.getLogger("shopsathi.messenger")

MESSAGING_WINDOW = timedelta(hours=24)
MAX_TEXT_CHARS = 2000  # Messenger's limit for one text message

#: Graph error codes that are worth retrying (temporary / rate limit); anything else is permanent
_TRANSIENT_CODES = {1, 2, 4, 17, 32, 341, 613}
_WINDOW_CLOSED = (10, 2018278)  # (code, subcode) "outside of allowed window"


class MessengerSendError(Exception):
    """The message was not sent. ``reason`` is one of: outside_window, no_token, failed."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail = reason, detail


class OutsideMessagingWindow(MessengerSendError):
    def __init__(self, detail: str = "the customer's last message is more than 24 hours old") -> None:
        super().__init__("outside_window", detail)


def window_open(last_customer_message_at: datetime | None, now: datetime | None = None) -> bool:
    """True while it is within 24 hours of the customer's last message. Unknown time = not allowed."""
    if last_customer_message_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    return now - last_customer_message_at <= MESSAGING_WINDOW


def is_public_url(url: str) -> bool:
    """Facebook downloads images itself, so it must be able to reach the URL (not localhost / a private address)."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or not host or host == "localhost" or host.endswith(".local"):
        return False
    return not re.match(r"^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|0\.|169\.254\.)", host)


def split_text(text: str, limit: int = MAX_TEXT_CHARS) -> list[str]:
    text = text.strip()
    parts: list[str] = []
    while len(text) > limit:
        cut = max(text.rfind("\n", 0, limit), text.rfind(" ", 0, limit))
        cut = cut if cut > limit // 2 else limit
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    return [*parts, text] if text else parts


class MessengerSender:
    def __init__(self, graph: GraphClient | None = None) -> None:
        self._graph = graph

    @property
    def graph(self) -> GraphClient:
        if self._graph is None:
            self._graph = GraphClient()
        return self._graph

    # ------------------------------------------------------------------ public

    def send_text(self, page: FacebookPage, psid: str, text: str, last_customer_message_at: datetime | None) -> str | None:
        """Send a text reply (split if longer than Messenger allows). Returns the id of the last message sent."""
        self._ensure_window(last_customer_message_at)
        mid = None
        for part in split_text(text):
            mid = self._send(page, psid, {"text": part}, last_customer_message_at)
        return mid

    def send_image(self, page: FacebookPage, psid: str, url: str, last_customer_message_at: datetime | None) -> str | None:
        """Send an image by its public URL."""
        self._ensure_window(last_customer_message_at)
        return self._send(
            page,
            psid,
            {"attachment": {"type": "image", "payload": {"url": url, "is_reusable": True}}},
            last_customer_message_at,
        )

    # ----------------------------------------------------------------- internals

    @staticmethod
    def _ensure_window(last_customer_message_at: datetime | None) -> None:
        if not window_open(last_customer_message_at):
            raise OutsideMessagingWindow()

    def _send(self, page: FacebookPage, psid: str, message: dict, last_customer_message_at: datetime | None) -> str | None:
        self._ensure_window(last_customer_message_at)  # re-checked for every message of a multi-part reply
        try:
            token = TokenCipher().decrypt(page.encrypted_page_token)
        except CipherError as e:
            raise MessengerSendError("no_token", str(e)) from e
        s = get_settings()
        attempts = max(1, s.fb_send_max_attempts)
        for attempt in range(1, attempts + 1):
            try:
                return self.graph.send_message(token, psid, message)
            except GraphAPIError as e:
                if (e.code, e.subcode) == _WINDOW_CLOSED:
                    raise OutsideMessagingWindow("Facebook says the message is outside the allowed window") from e
                transient = e.status_code is None or e.status_code >= 500 or e.code in _TRANSIENT_CODES
                # log the error code and message, never the token, the text or the customer's id
                logger.warning(
                    "send failed (page %s, attempt %s/%s, code %s, subcode %s): %s",
                    page.page_id, attempt, attempts, e.code, e.subcode, e.message,
                )
                if not transient or attempt == attempts:
                    raise MessengerSendError("failed", e.message) from e
                time.sleep(s.fb_send_retry_delay_seconds * attempt)
        raise MessengerSendError("failed", "no attempt was made")  # unreachable
