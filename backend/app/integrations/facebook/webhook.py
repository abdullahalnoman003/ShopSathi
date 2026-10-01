"""Checks for Meta's webhook requests."""

import hashlib
import hmac


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """``X-Hub-Signature-256`` is ``sha256=`` + HMAC-SHA256 of the raw request body with the app secret."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256=") :])


def sign(app_secret: str, body: bytes) -> str:
    """The header value Meta would send (used by the simulation script and the tests)."""
    return "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
