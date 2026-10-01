import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.integrations.facebook.webhook import verify_signature
from app.services.messenger_ingest import ingest_payload
from app.workers.dispatch import enqueue

logger = logging.getLogger("shopsathi.webhook")

# Public endpoints for Meta. They are protected by the verify token (GET) and the request signature (POST),
# not by a login.
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

MAX_BODY_BYTES = 1_000_000


@router.get("/messenger", response_class=PlainTextResponse)
def verify_webhook(
    mode: str | None = Query(default=None, alias="hub.mode"),
    verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    """Meta calls this once when the webhook URL is saved: answer with the challenge if the verify token matches."""
    expected = get_settings().fb_verify_token
    if not expected:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The webhook is not set up (FB_VERIFY_TOKEN is empty)")
    if mode != "subscribe" or not verify_token or not hmac.compare_digest(verify_token.encode(), expected.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Verification failed")
    return PlainTextResponse(challenge or "")


def _handle(payload: dict[str, Any]) -> int:
    from app.workers.tasks import process_incoming_message  # imported here: the worker module needs the app

    with SessionLocal() as db:
        ids = ingest_payload(db, payload)
    for message_id in ids:
        enqueue(process_incoming_message, message_id)  # never fails the request; the message stays stored
    return len(ids)


@router.post("/messenger")
async def receive_messenger(request: Request):
    """New Messenger events. Verify the signature, store the messages, queue the AI work, answer 200 at once."""
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Payload too large")
    if not verify_signature(get_settings().fb_app_secret, body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid signature")
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON")
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payload")
    received = await run_in_threadpool(_handle, payload)
    return {"status": "ok", "received": received}
