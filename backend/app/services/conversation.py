"""The single entry point for customer messages: ConversationService.handle_customer_message.

The Test chat window uses it now; Prompt 14 (Messenger) MUST reuse it so every channel gets the same
behaviour: storing messages, short-term memory, the AI engine, the first-reply disclosure, order drafting
and usage logging.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from shopsathi_ai.engine import ChatContext, ConversationEngine, EngineConfig, EngineResult
from shopsathi_ai.language import detect_style, normalise_digits
from shopsathi_ai.phrases import phrase
from shopsathi_ai.understanding import Turn
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_adapters.factory import get_embedder, get_llm
from app.ai_adapters.gateway import BackendShopDataGateway
from app.core.config import get_settings
from app.core.redis import get_redis
from app.models import Chat, HandoverEvent, Message, Notification, Order, Product, Shop
from app.models.handover import FLAG_REASONS
from app.services.ai_usage import log_ai_usage
from app.services.chat_memory import ChatMemoryService
from app.services.tenant import scoped_select

DUPLICATE_DRAFT_WINDOW = timedelta(minutes=10)
ORDER_SENT_PLACEHOLDER = "(the customer's order details were sent to the shop)"


@dataclass
class ConversationResult:
    customer_message: Message
    #: None when the chat is handed to a human (AI paused): the message is stored, no reply is written
    ai_message: Message | None
    engine_result: EngineResult | None
    order: Order | None = None


def build_engine(db: Session) -> ConversationEngine:
    s = get_settings()
    return ConversationEngine(
        get_llm(),
        get_embedder(),
        BackendShopDataGateway(db),
        EngineConfig(
            min_chunk_score=s.rag_min_score,
            min_product_score=s.rag_min_product_score,
            confidence_threshold=s.ai_confidence_threshold,
        ),
    )


def _strip_stamp(pending: dict | None) -> dict | None:
    return {k: v for k, v in pending.items() if k != "updated_at"} if pending else None


class ConversationService:
    def __init__(
        self, db: Session, engine: ConversationEngine | None = None, memory: ChatMemoryService | None = None
    ) -> None:
        self.db = db
        self.engine = engine or build_engine(db)
        self.memory = memory or ChatMemoryService(db)

    # ------------------------------------------------------------------ orders

    def _live_pending(self, chat: Chat, now: datetime) -> dict | None:
        """The order being collected, unless it was left unfinished for too long."""
        pending = chat.pending_order
        if not pending:
            return None
        stamp = pending.get("updated_at")
        if stamp:
            try:
                age = now - datetime.fromisoformat(stamp)
            except ValueError:
                age = timedelta(0)
            if age > timedelta(hours=get_settings().order_pending_ttl_hours):
                return None
        return _strip_stamp(pending)

    def _create_draft(self, chat: Chat, ready: dict[str, Any], now: datetime) -> Order | None:
        """Create ONE order with status 'draft'. The AI never confirms: that is the seller's decision."""
        product = self.db.scalars(
            scoped_select(Product, chat.shop_id).where(Product.id == ready["product_id"])
        ).first()
        if product is None or product.stock_count <= 0:
            return None  # sold out or removed while the customer was typing
        same = self.db.scalars(
            scoped_select(Order, chat.shop_id).where(
                Order.chat_id == chat.id,
                Order.status == "draft",
                Order.product_id == product.id,
                Order.size.is_(ready["size"]) if ready["size"] is None else Order.size == ready["size"],
                Order.colour.is_(ready["colour"]) if ready["colour"] is None else Order.colour == ready["colour"],
                Order.quantity == ready["quantity"],
                Order.customer_phone == ready["customer_phone"],
                Order.customer_address == ready["customer_address"],
                Order.created_at > now - DUPLICATE_DRAFT_WINDOW,
            )
        ).first()
        if same is not None:  # the same completed collection: do not create a second draft
            return same
        order = Order(
            shop_id=chat.shop_id,
            chat_id=chat.id,
            product_id=product.id,
            product_name=product.name,
            size=ready["size"],
            colour=ready["colour"],
            quantity=ready["quantity"],
            unit_price=product.price,  # catalogue price now, not what the model or the customer said
            customer_name=ready["customer_name"],
            customer_phone=ready["customer_phone"],
            customer_address=ready["customer_address"],
            status="draft",
            is_test=chat.channel == "test",
        )
        self.db.add(order)
        self.db.flush()
        return order

    @staticmethod
    def _draft_card(order: Order) -> dict[str, Any]:
        return {
            "id": order.id,
            "product_name": order.product_name,
            "size": order.size,
            "colour": order.colour,
            "quantity": order.quantity,
            "unit_price": float(order.unit_price),
            "customer_name": order.customer_name,
            "customer_phone": order.customer_phone,
            "customer_address": order.customer_address,
            "status": order.status,
        }

    # ------------------------------------------------------------------ handover

    def _flag_chat(self, chat: Chat, reason: str, now: datetime) -> None:
        """The AI could not handle this chat: flag it, hand it to a human (AI paused until a shop user turns it
        back on, Prompt 15), record the event for reports, and notify the shop (Messenger chats only: a flag
        in the Test chat window is shown in that window)."""
        if reason not in FLAG_REASONS:
            reason = "low_confidence"
        chat.is_flagged = True
        chat.flag_reason = reason
        chat.flagged_at = now
        chat.ai_paused = True
        self.db.add(HandoverEvent(shop_id=chat.shop_id, chat_id=chat.id, reason=reason))
        if chat.channel == "messenger":
            self.db.add(Notification(shop_id=chat.shop_id, type="chat_flagged", chat_id=chat.id, reason=reason))

    # ------------------------------------------------------------------ entry point

    def handle_customer_message(self, chat: Chat, text: str) -> ConversationResult:
        """Store the customer's message, produce the AI reply, store it, and log the AI usage."""
        recent = self.memory.load(chat)  # the turns BEFORE this message
        now = datetime.now(timezone.utc)
        customer = Message(shop_id=chat.shop_id, chat_id=chat.id, sender="customer", text=text, received_at=now)
        self.db.add(customer)
        chat.last_customer_message_at = now
        self.db.commit()  # the customer's message is kept even if something fails below
        return self._reply(chat, customer, recent)

    def reply_to_stored_message(self, chat: Chat, customer: Message) -> ConversationResult:
        """Answer a customer message that is already stored (a Messenger webhook stores it on arrival), without
        storing a second copy. Everything else is exactly what handle_customer_message does."""
        recent = self.memory.load(chat, before_message_id=customer.id)
        return self._reply(chat, customer, recent)

    def hand_over_non_text(self, chat: Chat, customer: Message) -> ConversationResult:
        """A photo, voice message, sticker or file arrived. The AI does not interpret those (out of scope): the
        chat is handed to the shop (reason low_confidence, through the normal handover) with a short holding reply."""
        db, shop_id = self.db, chat.shop_id
        now = datetime.now(timezone.utc)
        with get_redis().lock(f"chatlock:{shop_id}:{chat.id}", timeout=90, blocking_timeout=60):
            db.refresh(chat)
            shop = db.get(Shop, shop_id)
            style = self._style_of_chat(chat, customer.id)
            text = phrase("check_with_shop", style)
            first = not chat.ai_disclosure_sent
            if first:
                text = f"{phrase('disclosure', style, shop_name=shop.name if shop else '')}\n\n{text}"
                chat.ai_disclosure_sent = True
            customer.extras = {**(customer.extras or {}), "entities": {}}
            ai = Message(
                shop_id=shop_id,
                chat_id=chat.id,
                sender="ai",
                text=text,
                language_style=style,
                extras={
                    "handover": {"needed": True, "reason": "low_confidence", "detail": "non_text_message"},
                    "disclosure": first,
                    "in_reply_to": customer.id,
                },
                sent_at=None if chat.channel == "messenger" else now,
            )
            db.add(ai)
            self._flag_chat(chat, "low_confidence", now)
            db.commit()
            self.memory.append(chat, [Turn("customer", customer.text, {}), Turn("ai", text, {})])
        return ConversationResult(customer, ai, None, None)

    def _style_of_chat(self, chat: Chat, before_id: int) -> str:
        """The writing style of the customer's latest text message (English if there is none)."""
        rows = self.db.scalars(
            scoped_select(Message, chat.shop_id)
            .where(Message.chat_id == chat.id, Message.sender == "customer", Message.id < before_id)
            .order_by(Message.id.desc())
            .limit(5)
        ).all()
        for m in rows:
            if not (m.extras or {}).get("non_text"):
                return detect_style(normalise_digits(m.text))
        return "english"

    def _reply(self, chat: Chat, customer: Message, recent: list[Turn]) -> ConversationResult:
        db, shop_id, text = self.db, chat.shop_id, customer.text
        now = datetime.now(timezone.utc)

        # One message at a time per chat, so only one reply can be "the first" (disclosure) and an order
        # collection cannot be updated by two messages at once.
        with get_redis().lock(f"chatlock:{shop_id}:{chat.id}", timeout=90, blocking_timeout=60):
            db.refresh(chat)
            if chat.ai_paused:  # handed to a human: keep the customer's message, write no AI reply
                self.memory.append(chat, [Turn("customer", text, {})])
                return ConversationResult(customer, None, None, None)
            shop = db.get(Shop, shop_id)
            ctx = ChatContext(
                shop_name=shop.name if shop else "",
                is_first_ai_reply=not chat.ai_disclosure_sent,
                recent_turns=recent,
                pending_order=self._live_pending(chat, now),
            )
            result = self.engine.process_customer_message(shop_id, ctx, text)

            entities = result.entities
            customer.intent = result.intent
            customer.confidence = result.confidence
            customer.language_style = result.language_style
            customer.extras = {**(customer.extras or {}), "entities": entities}

            reply_text = result.reply_text
            extras: dict[str, Any] = {
                **result.extras,
                "entities": entities,
                "handover": {"needed": result.handover.needed, "reason": result.handover.reason, "detail": result.handover.detail},
                "disclosure": result.disclosure_included,
                "in_reply_to": customer.id,
            }
            order: Order | None = None
            ready = extras.pop("order_ready", None)  # the stored order replaces it
            if ready is not None:
                order = self._create_draft(chat, ready, now)
                if order is not None:
                    extras["order_id"] = order.id
                    extras["order_draft"] = self._draft_card(order)
                else:  # never tell the customer it was sent when nothing was created
                    reply_text = phrase("check_with_shop", result.language_style)
                    extras["handover"] = {"needed": True, "reason": "not_in_shop_data", "detail": "order_product_unavailable"}

            # keep the collected fields for the next turn (or clear them once the draft exists)
            if ready is not None:
                chat.pending_order = None
            elif result.pending_order is None:
                chat.pending_order = None
            elif _strip_stamp(result.pending_order) != _strip_stamp(chat.pending_order):
                chat.pending_order = {**_strip_stamp(result.pending_order), "updated_at": now.isoformat()}

            if extras["handover"]["needed"]:
                self._flag_chat(chat, extras["handover"]["reason"], now)

            ai = Message(
                shop_id=shop_id,
                chat_id=chat.id,
                sender="ai",
                text=reply_text,
                intent=result.intent,
                confidence=result.confidence,
                language_style=result.language_style,
                extras=extras,
                # a Messenger reply counts as sent only after Facebook accepted it (the worker sets sent_at)
                sent_at=None if chat.channel == "messenger" else datetime.now(timezone.utc),
            )
            db.add(ai)
            if result.disclosure_included:
                chat.ai_disclosure_sent = True
            for u in result.usage:  # LLM calls: intent, order_extraction, suggestion_needs, chat_reply
                log_ai_usage(db, shop_id, u.operation, u.provider, u.model, u.input_tokens, u.output_tokens, commit=False)
            db.commit()

            if ready is not None:
                # The details were used: forget them, so they cannot be read again and drafted twice.
                self.memory.clear(chat)
                self.memory.append(chat, [Turn("ai", ORDER_SENT_PLACEHOLDER, {})])
            else:
                self.memory.append(chat, [Turn("customer", text, entities), Turn("ai", reply_text, entities)])
        return ConversationResult(customer, ai, result, order)
