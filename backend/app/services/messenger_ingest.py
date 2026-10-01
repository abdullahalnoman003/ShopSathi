"""Turning a Messenger webhook payload into stored customer messages (FR-08).

Runs inside the webhook request, so it only does quick database work: it finds the shop by the Page id, finds or
creates the chat, stores the customer's message and returns its id. The AI work happens later in a Celery task.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.redis import get_redis
from app.models import Chat, FacebookPage, Message

logger = logging.getLogger("shopsathi.webhook")

MAX_TEXT_CHARS = 2000
#: shown to the shop's staff in place of content the AI does not interpret (voice, images, stickers, files)
PLACEHOLDERS = {
    "image": "[Customer sent a photo]",
    "audio": "[Customer sent a voice message]",
    "video": "[Customer sent a video]",
    "file": "[Customer sent a file]",
    "location": "[Customer shared a location]",
    "sticker": "[Customer sent a sticker]",
}
DEFAULT_PLACEHOLDER = "[Customer sent an attachment]"


def _event_time(ms: Any, now: datetime) -> datetime:
    """The time Facebook says the customer sent the message, if it is believable."""
    try:
        t = datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return now
    return t if now - timedelta(days=2) < t <= now + timedelta(minutes=5) else now


def _content(msg: dict[str, Any]) -> tuple[str, bool, list[str]]:
    """(text to store, is it non-text, attachment types)."""
    text = msg.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()[:MAX_TEXT_CHARS], False, []
    types = [str(a.get("type", "")) for a in (msg.get("attachments") or []) if isinstance(a, dict)]
    if msg.get("sticker_id"):
        types = ["sticker", *[t for t in types if t != "image"]]
    first = types[0] if types else ""
    return PLACEHOLDERS.get(first, DEFAULT_PLACEHOLDER), True, types


def ingest_payload(db: Session, payload: dict[str, Any]) -> list[int]:
    """Store every new customer message in the payload. Returns the ids of the messages to process."""
    if payload.get("object") != "page":
        return []
    ids: list[int] = []
    for entry in payload.get("entry") or []:
        page_id = str(entry.get("id", ""))
        page = db.scalars(select(FacebookPage).where(FacebookPage.page_id == page_id)).first()
        if page is None:
            logger.info("webhook event for a Page that is not connected (%s) ignored", page_id)
            continue
        for event in entry.get("messaging") or []:
            message_id = _ingest_event(db, page, event)
            if message_id is not None:
                ids.append(message_id)
    return ids


def _ingest_event(db: Session, page: FacebookPage, event: dict[str, Any]) -> int | None:
    msg = event.get("message")
    if not isinstance(msg, dict) or msg.get("is_echo"):  # delivery/read receipts, postbacks, echoes of our own sends
        return None
    mid = msg.get("mid")
    psid = str((event.get("sender") or {}).get("id", ""))
    recipient = str((event.get("recipient") or {}).get("id", page.page_id))
    if not mid or not psid or psid == page.page_id or recipient != page.page_id:
        return None
    shop_id = page.shop_id
    if db.scalar(select(Message.id).where(Message.shop_id == shop_id, Message.external_message_id == mid)) is not None:
        return None  # Facebook delivers some events more than once

    text, non_text, types = _content(msg)
    now = datetime.now(timezone.utc)
    sent_at = _event_time(event.get("timestamp"), now)

    with get_redis().lock(f"ingest:{shop_id}:{psid}", timeout=15, blocking_timeout=10):
        chat = db.scalars(
            select(Chat).where(Chat.shop_id == shop_id, Chat.channel == "messenger", Chat.customer_psid == psid)
        ).first()
        if chat is None:
            chat = Chat(shop_id=shop_id, channel="messenger", customer_psid=psid)
            db.add(chat)
            db.flush()
        chat.last_customer_message_at = max(filter(None, [chat.last_customer_message_at, sent_at]))
        message = Message(
            shop_id=shop_id,
            chat_id=chat.id,
            sender="customer",
            text=text,
            external_message_id=mid,
            received_at=now,  # when ShopSathi got it: the start of the 8-second reply clock (NFR-01)
            extras={"ai_status": "pending", "non_text": non_text, "attachment_types": types, "fb_timestamp": event.get("timestamp")},
        )
        db.add(message)
        try:
            db.commit()
        except IntegrityError:  # the same message arrived twice at once
            db.rollback()
            return None
    return message.id
