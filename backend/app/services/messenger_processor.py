"""Processing stored Messenger messages in the background (Celery): AI reply -> Send API -> usage count.

Messages of one chat are handled in order, one at a time (a Redis lock per chat). A message is answered by the
SAME pipeline as the Test chat (``ConversationService``); this module only decides whether the AI may reply
(shop active, chat not paused, Page connected, 24-hour window open, monthly limit not reached) and delivers the
reply. The shop's usage is counted only after Facebook accepted the reply.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import CipherError, TokenCipher
from app.core.redis import get_redis
from app.integrations.facebook.graph_client import GraphClient
from app.integrations.facebook.messenger_sender import (
    MessengerSender,
    MessengerSendError,
    OutsideMessagingWindow,
    is_public_url,
    window_open,
)
from app.models import Chat, FacebookPage, Message, Shop
from app.services.conversation import ConversationService
from app.services.tenant import scoped_select
from app.services.usage import UsageLimitService

logger = logging.getLogger("shopsathi.messenger")

MAX_PHOTOS_PER_REPLY = 3


class ChatBusy(Exception):
    """Another worker is processing this chat right now; try again shortly."""


def _ms(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() * 1000)


class MessengerProcessor:
    def __init__(
        self,
        db: Session,
        service: ConversationService | None = None,
        sender: MessengerSender | None = None,
        graph: GraphClient | None = None,
    ) -> None:
        self.db = db
        self._service = service
        self.graph = graph or GraphClient()
        self.sender = sender or MessengerSender(self.graph)
        self.usage = UsageLimitService(db)

    @property
    def service(self) -> ConversationService:
        if self._service is None:
            self._service = ConversationService(self.db)
        return self._service

    # ------------------------------------------------------------------ entry

    def process(self, message_id: int) -> None:
        """Handle this customer message and any earlier ones of the same chat that are still waiting, in order."""
        message = self.db.get(Message, message_id)
        if message is None or message.sender != "customer":
            return
        chat = self.db.get(Chat, message.chat_id)
        if chat is None or chat.channel != "messenger" or chat.shop_id != message.shop_id:
            return
        lock = get_redis().lock(f"chatmsgs:{chat.shop_id}:{chat.id}", timeout=300, blocking_timeout=120)
        if not lock.acquire():
            raise ChatBusy(f"chat {chat.id} is busy")
        try:
            waiting = self.db.scalars(
                scoped_select(Message, chat.shop_id)
                .where(
                    Message.chat_id == chat.id,
                    Message.sender == "customer",
                    Message.id <= message_id,
                    Message.extras["ai_status"].astext == "pending",
                )
                .order_by(Message.id)
            ).all()
            for m in waiting:
                self._process_one(chat, m)
        finally:
            try:
                lock.release()
            except Exception:  # the lock expired: nothing to release
                pass

    # ------------------------------------------------------------------ one message

    def _mark(self, message: Message, status: str, **info: Any) -> None:
        message.extras = {**(message.extras or {}), "ai_status": status, **info}
        self.db.commit()

    def _skip_reason(self, chat: Chat, shop: Shop | None, page: FacebookPage | None) -> str | None:
        if shop is None or shop.status == "suspended":
            return "shop_suspended"
        if chat.ai_paused:
            return "ai_paused"
        if page is None:
            return "no_page"
        if not window_open(chat.last_customer_message_at):
            return "outside_window"  # also checked again when sending
        if not self.usage.can_send_ai_reply(chat.shop_id):
            return "limit_reached"  # FR-15: the monthly limit stops AI replies
        return None

    def _process_one(self, chat: Chat, message: Message) -> None:
        started = datetime.now(timezone.utc)
        try:
            self.db.refresh(chat)
            shop = self.db.get(Shop, chat.shop_id)
            page = self.db.scalars(scoped_select(FacebookPage, chat.shop_id)).first()
            reason = self._skip_reason(chat, shop, page)
            if reason:  # the message stays for the seller; no AI reply
                logger.info("chat %s message %s: no AI reply (%s)", chat.id, message.id, reason)
                self._mark(message, "skipped", ai_skip_reason=reason)
                return
            assert page is not None

            self._ensure_customer_name(chat, page)
            ai = self._existing_reply(chat, message)  # a retried task must not answer twice
            if ai is None:
                if (message.extras or {}).get("non_text"):
                    result = self.service.hand_over_non_text(chat, message)
                else:
                    result = self.service.reply_to_stored_message(chat, message)
                ai = result.ai_message
            if ai is None:  # the chat was handed to a human while this message waited
                self._mark(message, "skipped", ai_skip_reason="ai_paused")
                return
            ai_done = datetime.now(timezone.utc)
            self._deliver(chat, page, message, ai, started, ai_done)
        except Exception as e:  # never crash the worker; the customer's message is safe in the database
            self.db.rollback()
            logger.exception("processing message %s failed: %s", message.id, e.__class__.__name__)
            try:
                self._mark(self.db.get(Message, message.id), "failed", ai_error=e.__class__.__name__)  # type: ignore[arg-type]
            except Exception:
                self.db.rollback()

    def _existing_reply(self, chat: Chat, message: Message) -> Message | None:
        return self.db.scalars(
            scoped_select(Message, chat.shop_id).where(
                Message.chat_id == chat.id,
                Message.sender == "ai",
                Message.extras["in_reply_to"].astext == str(message.id),
            )
        ).first()

    # ------------------------------------------------------------------ delivery

    def _deliver(self, chat: Chat, page: FacebookPage, message: Message, ai: Message, started: datetime, ai_done: datetime) -> None:
        psid = chat.customer_psid or ""
        delivery: dict[str, Any] = {"status": "failed"}
        try:
            fb_mid = self.sender.send_text(page, psid, ai.text, chat.last_customer_message_at)
        except OutsideMessagingWindow:
            delivery = {"status": "not_sent", "reason": "outside_window"}
            fb_mid, sent = None, False
        except MessengerSendError as e:
            delivery = {"status": "failed", "reason": e.reason, "detail": e.detail[:200]}
            fb_mid, sent = None, False
        else:
            sent = True

        if sent:
            delivery = {"status": "sent", "facebook_message_id": fb_mid, **self._send_photos(chat, page, psid, ai)}
            sent_at = datetime.now(timezone.utc)
            ai.sent_at = sent_at
            received = message.received_at or started
            delivery["timings_ms"] = {
                "queue": _ms(received, started),
                "ai": _ms(started, ai_done),
                "send": _ms(ai_done, sent_at),
                "total": _ms(received, sent_at),  # customer message received -> reply accepted by Facebook (NFR-01)
            }
            ai.extras = {**ai.extras, "delivery": delivery}
            message.extras = {**(message.extras or {}), "ai_status": "replied"}
            # counted only now that Facebook accepted the reply (this call commits everything above)
            self.usage.record_ai_reply(chat.shop_id)
            logger.info("chat %s: reply sent in %s ms", chat.id, delivery["timings_ms"]["total"])
        else:
            ai.extras = {**ai.extras, "delivery": delivery}
            message.extras = {**(message.extras or {}), "ai_status": "failed" if delivery["status"] == "failed" else "skipped",
                              "ai_skip_reason": delivery.get("reason", "send_failed")}
            self.db.commit()  # a reply that was not sent is not counted against the plan
            logger.warning("chat %s: reply not sent (%s)", chat.id, delivery.get("reason"))

    def _send_photos(self, chat: Chat, page: FacebookPage, psid: str, ai: Message) -> dict[str, int]:
        """Suggested products come with their photo (AI-3). Best effort: the text reply is already delivered."""
        sent = skipped = 0
        for card in (ai.extras or {}).get("suggested_products", [])[:MAX_PHOTOS_PER_REPLY]:
            url = card.get("photo")
            if not url or not is_public_url(url):
                skipped += 1
                continue
            try:
                self.sender.send_image(page, psid, url, chat.last_customer_message_at)
                sent += 1
            except MessengerSendError:
                skipped += 1
        return {"images_sent": sent, "images_skipped": skipped}

    # ------------------------------------------------------------------ customer name

    def _ensure_customer_name(self, chat: Chat, page: FacebookPage) -> None:
        """Store the customer's name if Facebook gives it with the granted permissions; otherwise leave it empty."""
        if chat.customer_name or not chat.customer_psid:
            return
        if not get_redis().set(f"fb:name_tried:{chat.id}", 1, nx=True, ex=86400):
            return  # tried recently
        try:
            name = self.graph.customer_name(chat.customer_psid, TokenCipher().decrypt(page.encrypted_page_token))
        except Exception:  # CipherError, GraphAPIError ...: the name is optional
            return
        if name:
            chat.customer_name = name[:200]
            self.db.commit()
