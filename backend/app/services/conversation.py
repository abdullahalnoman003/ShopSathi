"""The single entry point for customer messages: ConversationService.handle_customer_message.

The Test chat window uses it now; Prompt 14 (Messenger) MUST reuse it so every channel gets the same
behaviour: storing messages, short-term memory, the AI engine, the first-reply disclosure and usage logging.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from shopsathi_ai.engine import ChatContext, ConversationEngine, EngineConfig, EngineResult
from shopsathi_ai.understanding import Turn
from sqlalchemy.orm import Session

from app.ai_adapters.factory import get_embedder, get_llm
from app.ai_adapters.gateway import BackendShopDataGateway
from app.core.config import get_settings
from app.core.redis import get_redis
from app.models import Chat, Message, Shop
from app.services.ai_usage import log_ai_usage
from app.services.chat_memory import ChatMemoryService


@dataclass
class ConversationResult:
    customer_message: Message
    ai_message: Message
    engine_result: EngineResult


def build_engine(db: Session) -> ConversationEngine:
    s = get_settings()
    return ConversationEngine(
        get_llm(),
        get_embedder(),
        BackendShopDataGateway(db),
        EngineConfig(min_chunk_score=s.rag_min_score, min_product_score=s.rag_min_product_score),
    )


class ConversationService:
    def __init__(
        self, db: Session, engine: ConversationEngine | None = None, memory: ChatMemoryService | None = None
    ) -> None:
        self.db = db
        self.engine = engine or build_engine(db)
        self.memory = memory or ChatMemoryService(db)

    def handle_customer_message(self, chat: Chat, text: str) -> ConversationResult:
        """Store the customer's message, produce the AI reply, store it, and log the AI usage."""
        db, shop_id = self.db, chat.shop_id
        recent = self.memory.load(chat)  # the turns BEFORE this message

        now = datetime.now(timezone.utc)
        customer = Message(shop_id=shop_id, chat_id=chat.id, sender="customer", text=text, received_at=now)
        db.add(customer)
        chat.last_customer_message_at = now
        db.commit()  # the customer's message is kept even if something fails below

        # One message at a time per chat, so only one reply can be "the first" (disclosure).
        with get_redis().lock(f"chatlock:{shop_id}:{chat.id}", timeout=90, blocking_timeout=60):
            db.refresh(chat)
            shop = db.get(Shop, shop_id)
            ctx = ChatContext(
                shop_name=shop.name if shop else "",
                is_first_ai_reply=not chat.ai_disclosure_sent,
                recent_turns=recent,
            )
            result = self.engine.process_customer_message(shop_id, ctx, text)

            entities = result.entities
            customer.intent = result.intent
            customer.confidence = result.confidence
            customer.language_style = result.language_style
            customer.extras = {"entities": entities}
            ai = Message(
                shop_id=shop_id,
                chat_id=chat.id,
                sender="ai",
                text=result.reply_text,
                intent=result.intent,
                confidence=result.confidence,
                language_style=result.language_style,
                extras={
                    **result.extras,
                    "entities": entities,
                    "handover": {"needed": result.handover.needed, "reason": result.handover.reason},
                    "disclosure": result.disclosure_included,
                },
                sent_at=datetime.now(timezone.utc),
            )
            db.add(ai)
            if result.disclosure_included:
                chat.ai_disclosure_sent = True
            for u in result.usage:  # LLM calls: operation "intent" and "chat_reply"
                log_ai_usage(db, shop_id, u.operation, u.provider, u.model, u.input_tokens, u.output_tokens, commit=False)
            db.commit()

            self.memory.append(
                chat,
                [Turn("customer", text, entities), Turn("ai", result.reply_text, entities)],
            )
        return ConversationResult(customer, ai, result)
