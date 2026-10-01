"""The conversation pipeline (Figure 1): 1. Understand -> 2. Search (RAG + tools) -> 3. Write reply.

``ConversationEngine.process_customer_message`` is the single entry point. It never touches a database:
all shop data comes through the ``ShopDataGateway``. Every answer is built only from the shop's products
and policy; when the data has no answer the reply is "I'll check with the shop" plus a handover signal.
"""

from dataclasses import dataclass, field
from typing import Any

from shopsathi_ai.chunking import format_money
from shopsathi_ai.extraction import extract_order
from shopsathi_ai.handover import DEFAULT_CONFIDENCE_THRESHOLD, EngineState, decide_handover, reason_for_failure
from shopsathi_ai.interfaces import ProductInfo, RetrievedChunk, ShopDataGateway, StockInfo
from shopsathi_ai.language import LanguageStyle, detect_style, normalise_digits
from shopsathi_ai.ordering import compose_order_reply, core, order_ready_fields, process_order
from shopsathi_ai.phrases import is_greeting, phrase
from shopsathi_ai.providers.base import EmbeddingProvider, EmbeddingProviderError, LLMProvider, LLMProviderError, LLMResult
from shopsathi_ai.reply import ReplyRequest, write_reply
from shopsathi_ai.suggestions import SuggestionConfig, extract_needs, find_suggestions, suggestion_card
from shopsathi_ai.tools import ShopTools
from shopsathi_ai.understanding import Turn, Understanding, understand

PRODUCT_INTENTS = ("price", "size_stock")


@dataclass
class EngineConfig:
    top_k_chunks: int = 5
    #: retrieved chunks below this cosine similarity are ignored
    min_chunk_score: float = 0.2
    #: semantic (non name-match) products below this similarity are ignored
    min_product_score: float = 0.3
    #: name matches need at least this fraction of the customer's words in the product name
    min_name_match: float = 0.5
    max_products: int = 3
    #: how many candidate products the suggestion step looks at before filtering
    suggestion_pool: int = 10
    max_recent_turns: int = 6
    max_turn_chars: int = 300
    #: understanding confidence below this flags the chat (backend setting AI_CONFIDENCE_THRESHOLD)
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD


@dataclass
class ChatContext:
    """What the engine may know about the chat: the shop name, whether this is the first AI reply, and the
    last few turns (never the full history)."""

    shop_name: str
    is_first_ai_reply: bool = False
    recent_turns: list[Turn] = field(default_factory=list)
    #: the order being collected in this chat (validated fields so far), or None
    pending_order: dict | None = None


@dataclass
class Handover:
    """Signal that a person should look at this chat (the flagging itself arrives in Prompt 12)."""

    needed: bool = False
    reason: str | None = None
    #: the technical cause when the reason is a general one (e.g. "ai_unavailable" under low_confidence)
    detail: str | None = None


@dataclass
class UsageRecord:
    operation: str  # "intent" | "chat_reply"
    provider: str
    model: str
    input_tokens: int
    output_tokens: int


@dataclass
class EngineResult:
    reply_text: str
    intent: str
    entities: dict[str, str | None]
    confidence: float
    language_style: LanguageStyle
    handover: Handover
    #: extensible: product_ids, tools, sources (Prompts 10-12 add their own keys)
    extras: dict[str, Any] = field(default_factory=dict)
    usage: list[UsageRecord] = field(default_factory=list)
    #: True when the automatic-assistant disclosure is part of reply_text
    disclosure_included: bool = False
    #: the chat's pending order after this turn (store it; None clears it). Complete orders are in
    #: extras["order_ready"]; the AI only ever produces drafts for the seller to confirm.
    pending_order: dict | None = None


class _Run:
    """Mutable state of one message being processed."""

    def __init__(self, shop_id: int, ctx: ChatContext, message: str, style: LanguageStyle, tools: ShopTools):
        self.shop_id, self.ctx, self.message, self.style, self.tools = shop_id, ctx, message, style, tools
        self.usage: list[UsageRecord] = []
        self.pending_out: dict | None = ctx.pending_order
        self.intent = "other"
        self.entities: dict[str, str | None] = {
            "product_name": None, "product_name_en": None, "size": None, "colour": None, "area": None,
        }
        self.confidence = 0.0

    def add_llm(self, operation: str, results: list[LLMResult]) -> None:
        for r in results:
            self.usage.append(UsageRecord(operation, r.provider, r.model, r.input_tokens, r.output_tokens))


class ConversationEngine:
    def __init__(
        self,
        llm: LLMProvider,
        embedder: EmbeddingProvider,
        gateway: ShopDataGateway,
        config: EngineConfig | None = None,
    ) -> None:
        self.llm = llm
        self.embedder = embedder
        self.gateway = gateway
        self.config = config or EngineConfig()

    # ------------------------------------------------------------------ public

    def process_customer_message(self, shop_id: int, chat_context: ChatContext, message: str) -> EngineResult:
        text = normalise_digits(message).strip()
        style = detect_style(text)
        if style == "english" and chat_context.pending_order:
            # A name, phone number or address has no language signal: while an order is being collected,
            # keep the style the customer has been writing in.
            for turn in reversed(chat_context.recent_turns):
                earlier = detect_style(normalise_digits(turn.text)) if turn.role == "customer" else "english"
                if earlier != "english":
                    style = earlier
                    break
        run = _Run(shop_id, chat_context, text, style, ShopTools(self.gateway, shop_id))
        try:
            return self._process(run)
        except (LLMProviderError, EmbeddingProviderError):
            return self._check_with_shop(run, "ai_unavailable")

    # ---------------------------------------------------------------- pipeline

    def _process(self, run: _Run) -> EngineResult:
        cfg = self.config

        # 1. Understand
        outcome = understand(
            self.llm, run.message, run.ctx.recent_turns, max_turns=cfg.max_recent_turns, max_turn_chars=cfg.max_turn_chars
        )
        run.add_llm("intent", outcome.usage)
        if outcome.understanding is None:
            decision = decide_handover(run.message, None, EngineState(order_in_progress=bool(run.ctx.pending_order)))
            return self._hold(run, decision.reason or "low_confidence", "understanding_failed")
        und: Understanding = outcome.understanding
        run.intent, run.confidence = und.intent, und.confidence
        run.entities = und.entities.model_dump()
        if und.intent in ("price", "size_stock", "delivery") and not run.entities["product_name"]:
            run.entities["product_name"] = self._product_from_history(run.ctx.recent_turns)
        if run.entities["size"]:
            run.entities["size"] = run.entities["size"].upper()

        # AI-5 / AI-R10: complaints, refund requests, abuse, a request for a person, an unsure AI and
        # off-topic messages are passed to the shop with a short holding reply (greetings are never flagged).
        if not (und.intent == "other" and is_greeting(run.message)):
            decision = decide_handover(
                run.message,
                und,
                EngineState(
                    order_in_progress=bool(run.ctx.pending_order),
                    confidence_threshold=self.config.confidence_threshold,
                ),
            )
            if decision.flag:
                return self._hold(run, decision.reason or "low_confidence")
        # Order drafting (AI-4): on an order request, and on follow-up turns while an order is being collected
        if und.intent == "order" or run.ctx.pending_order:
            ordered = self._order(run, und)
            if ordered is not None:
                return ordered

        if und.intent == "other" and is_greeting(run.message):
            return self._finish(run, phrase("greeting", run.style), Handover())

        if und.intent == "suggestion":
            return self._suggest(run)

        if und.intent in ("price", "size_stock") and not run.entities["product_name"]:
            return self._finish(run, phrase("ask_product", run.style), Handover(), extras={"clarification": "product"})

        # 2. Search (RAG + tools)
        query_text = " ".join(x for x in (run.entities["product_name"], run.entities.get("product_name_en"), run.message) if x)
        embedded = self.embedder.embed_with_usage([query_text], is_query=True)
        self.gateway.log_ai_usage(run.shop_id, "embedding", embedded.provider, embedded.model, embedded.input_tokens)
        vector = embedded.vectors[0]

        chunks = [
            c
            for c in self.gateway.vector_search(run.shop_id, vector, cfg.top_k_chunks)
            if c.score >= cfg.min_chunk_score
        ]
        facts, structured, product_ids = self._gather_facts(run, vector, chunks)

        if not facts:
            if und.intent == "delivery" and not run.entities["area"]:
                return self._finish(run, phrase("ask_area", run.style), Handover(), extras={"clarification": "area"})
            return self._check_with_shop(run, "not_in_shop_data")

        # 3. Write the reply (checked in code: every number must come from the facts)
        reply = write_reply(
            self.llm,
            ReplyRequest(
                message=run.message,
                intent=run.intent,
                language_style=run.style,
                facts=facts,
                structured=structured,
                recent_turns=run.ctx.recent_turns,
                shop_name=run.ctx.shop_name,
                max_turns=cfg.max_recent_turns,
                max_turn_chars=cfg.max_turn_chars,
            ),
        )
        run.add_llm("chat_reply", reply.usage)
        if reply.text is None:
            return self._check_with_shop(run, reply.reason or "reply_not_grounded")

        extras = {
            "product_ids": product_ids,
            "sources": [{"type": c.source_type, "id": c.source_id} for c in chunks],
        }
        return self._finish(run, reply.text, Handover(), extras=extras)

    # --------------------------------------------------------------- orders

    def _order(self, run: _Run, und: Understanding) -> EngineResult | None:
        """Collect, validate and draft an order. Returns None when the message is not about the order (a question
        asked in the middle of collecting one), so it is answered normally and the pending order is kept."""
        cfg = self.config
        pending = core(run.ctx.pending_order)
        out = extract_order(
            self.llm, run.ctx.recent_turns, pending, run.message, max_turns=cfg.max_recent_turns + 2, max_turn_chars=cfg.max_turn_chars + 100
        )
        run.add_llm("order_extraction", out.usage)
        if out.extraction is None:
            return None if und.intent != "order" else self._check_with_shop(run, "order_extraction_failed")

        customer_text = " ".join([t.text for t in run.ctx.recent_turns if t.role == "customer"] + [run.message])
        hint = (
            run.entities.get("product_name_en") or run.entities.get("product_name") or self._product_from_history(run.ctx.recent_turns)
        )
        check = process_order(run.tools, out.extraction, pending, customer_text, hint, cfg.min_name_match)
        if not check.progressed and und.intent != "order":
            return None

        run.intent = "order"
        state = run.tools.update_order_draft(run.ctx.pending_order, check.state)
        run.entities.update(product_name=state.get("product_name"), size=state.get("size"), colour=state.get("colour"))
        run.pending_out = state if any(v is not None for v in check.state.values()) else None

        if "unknown_product" in check.issues:  # AI-R04: not in the shop's data, so do not guess
            return self._check_with_shop(run, "not_in_shop_data")

        extras: dict[str, Any] = {"order_missing": check.ask}
        if check.ready:
            extras["order_ready"] = order_ready_fields(check)
            extras["product_ids"] = [check.state["product_id"]]
            run.pending_out = None
        return self._finish(run, compose_order_reply(check, run.style), Handover(), extras=extras)

    # ------------------------------------------------------------ suggestions

    def _suggest(self, run: _Run) -> EngineResult:
        """AI-3: 1-3 in-stock products that match the stated needs, with price and photo."""
        cfg = self.config
        out = extract_needs(
            self.llm, run.message, run.ctx.recent_turns, run.entities,
            max_turns=cfg.max_recent_turns, max_turn_chars=cfg.max_turn_chars,
        )
        run.add_llm("suggestion_needs", out.usage)
        needs = out.needs
        needs_info = {
            "product_type": needs.product_type_en or needs.product_type,
            "budget_max": None if needs.budget_max is None else float(needs.budget_max),
            "size": needs.size,
            "colour": needs.colour,
            "occasion": needs.occasion,
        }
        if needs.is_empty():
            return self._finish(
                run, phrase("ask_needs", run.style), Handover(), extras={"suggested_products": [], "clarification": "needs"}
            )

        query_text = " ".join(
            x for x in (needs.product_type_en, needs.product_type, needs.occasion, needs.colour, run.message) if x
        )
        embedded = self.embedder.embed_with_usage([query_text], is_query=True)
        self.gateway.log_ai_usage(run.shop_id, "embedding", embedded.provider, embedded.model, embedded.input_tokens)

        picked = find_suggestions(
            run.tools,
            self.gateway,
            run.shop_id,
            needs,
            embedded.vectors[0],
            SuggestionConfig(
                pool=cfg.suggestion_pool, min_name_match=cfg.min_name_match, min_product_score=cfg.min_product_score
            ),
        )
        extras: dict[str, Any] = {"suggested_products": [], "needs": needs_info}
        if not picked:
            return self._finish(run, phrase("no_suggestion", run.style), Handover(), extras=extras)

        reply = write_reply(
            self.llm,
            ReplyRequest(
                message=run.message,
                intent="suggestion",
                language_style=run.style,
                facts=[product_fact(p) for p in picked],
                structured={"products": [product_dict(p) for p in picked]},
                recent_turns=run.ctx.recent_turns,
                shop_name=run.ctx.shop_name,
                max_turns=cfg.max_recent_turns,
                max_turn_chars=cfg.max_turn_chars,
            ),
        )
        run.add_llm("chat_reply", reply.usage)
        if reply.text is None:  # could not write a verified reply: no cards either
            return self._finish(
                run, phrase("check_with_shop", run.style), Handover(True, "low_confidence", reply.reason or "reply_not_grounded"), extras=extras
            )
        extras["suggested_products"] = [suggestion_card(p) for p in picked]
        extras["product_ids"] = [p.id for p in picked]
        if len(picked) == 1:  # "eta ki XL e pawa jabe?" can then refer to it
            run.entities["product_name"] = picked[0].name
        return self._finish(run, reply.text, Handover(), extras=extras)

    # ------------------------------------------------------------------ facts

    def _gather_facts(
        self, run: _Run, vector: list[float], chunks: list[RetrievedChunk]
    ) -> tuple[list[str], dict[str, Any], list[int]]:
        cfg = self.config
        facts: list[str] = []
        structured: dict[str, Any] = {}
        product_ids: list[int] = []
        e = run.entities

        if run.intent in PRODUCT_INTENTS:
            products = self._matching_products(run, vector)
            if run.intent == "size_stock" and products:
                stock = run.tools.check_stock(products[0].id, e["size"], e["colour"])
                if stock is not None:
                    facts.append(stock_fact(stock))
                    structured["stock"] = stock_dict(stock)
                    products = [p for p in products if p.id == stock.product_id]
            facts = [product_fact(p) for p in products] + facts
            structured["products"] = [product_dict(p) for p in products]
            product_ids = [p.id for p in products]
        elif run.intent == "delivery" and e["area"]:
            charge = run.tools.get_delivery_charge(e["area"])
            if charge.found:
                facts.append(f"Delivery charge for {charge.area_name}: {format_money(charge.charge)} BDT")  # type: ignore[arg-type]
                structured["delivery"] = {"area": charge.area_name, "charge": format_money(charge.charge)}  # type: ignore[arg-type]
                facts.extend(c.content for c in chunks if c.source_type == "policy" and "Delivery time" in c.content)
            # an area that is not in the policy gives no fact: the reply becomes "I'll check with the shop"
        elif run.intent in ("delivery", "other"):
            # delivery without an area: the delivery policy; other: whatever the shop's data says about it
            facts.extend(c.content for c in chunks if run.intent == "other" or c.source_type == "policy")
        if run.intent == "other":
            structured["chunks"] = [c.content for c in chunks]
        return facts, structured, product_ids

    def _matching_products(self, run: _Run, vector: list[float]) -> list[ProductInfo]:
        cfg = self.config
        # the English form matches an English catalogue best (e.g. "লাল শাড়ি" -> "red saree")
        query = run.entities.get("product_name_en") or run.entities["product_name"] or run.message
        found = run.tools.search_products(query, vector, cfg.max_products)
        keep = [
            p
            for p in found
            if (p.match == "name" and p.score >= cfg.min_name_match)
            or (p.match == "semantic" and p.score >= cfg.min_product_score)
        ]
        return keep[: cfg.max_products]

    @staticmethod
    def _product_from_history(turns: list[Turn]) -> str | None:
        """The product talked about most recently, so "eta ki XL e pawa jabe?" knows what "eta" is."""
        for turn in reversed(turns):
            name = turn.entities.get("product_name") if turn.entities else None
            if name:
                return name
        return None

    # --------------------------------------------------------------- results

    _HOLDING_PHRASE = {
        "complaint": "holding_complaint",
        "refund": "holding_complaint",
        "abusive_language": "holding_abusive",
        "human_requested": "holding_human",
        "off_topic": "holding_off_topic",
        "low_confidence": "check_with_shop",
        "not_in_shop_data": "check_with_shop",
    }

    def _hold(self, run: _Run, reason: str, detail: str | None = None) -> EngineResult:
        """Flag the chat for the shop: a short, polite holding reply in the customer's style. It promises nothing
        (no refund, discount or answer); the shop's staff take over."""
        return self._finish(run, phrase(self._HOLDING_PHRASE[reason], run.style), Handover(True, reason, detail))

    def _check_with_shop(self, run: _Run, cause: str) -> EngineResult:
        """The safe answer when the shop's data has no answer or something went wrong: never guess.

        ``cause`` may be a flag reason or a technical failure ("ai_unavailable", "reply_not_grounded", ...),
        which is recorded under a flag reason with the cause kept as the detail."""
        reason = reason_for_failure(cause)
        return self._hold(run, reason, None if cause == reason else cause)

    def _finish(self, run: _Run, body: str, handover: Handover, extras: dict[str, Any] | None = None) -> EngineResult:
        text = body
        disclosure = run.ctx.is_first_ai_reply
        if disclosure:
            text = f"{phrase('disclosure', run.style, shop_name=run.ctx.shop_name)}\n\n{body}"
        out_extras: dict[str, Any] = dict(extras or {})
        out_extras["tools"] = [{"name": c.name, "args": c.args, "result": c.result} for c in run.tools.calls]
        return EngineResult(
            reply_text=text,
            intent=run.intent,
            entities=run.entities,
            confidence=run.confidence,
            language_style=run.style,
            handover=handover,
            extras=out_extras,
            usage=run.usage,
            disclosure_included=disclosure,
            pending_order=run.pending_out,
        )


# ---------------------------------------------------------------- fact text


def product_fact(p: ProductInfo) -> str:
    stock = f"in stock ({p.stock_count} available overall)" if p.stock_count > 0 else "out of stock"
    parts = [
        f"Product: {p.name}",
        f"Price: {format_money(p.price)} BDT",
        f"Sizes: {', '.join(p.sizes) if p.sizes else 'not applicable'}",
        f"Colours: {', '.join(p.colours) if p.colours else 'not applicable'}",
        f"Stock: {stock}",
    ]
    if p.description:
        parts.append(f"Description: {p.description[:300]}")
    return " | ".join(parts)


def stock_fact(s: StockInfo) -> str:
    parts = [f"Stock check for {s.name}"]
    if s.size is not None:
        if s.size_offered:
            parts.append(f"size {s.size} is offered")
        else:
            offered = ", ".join(s.sizes) if s.sizes else "none listed"
            parts.append(f"size {s.size} is NOT offered (offered sizes: {offered})")
    if s.colour is not None:
        if s.colour_offered:
            parts.append(f"colour {s.colour} is offered")
        else:
            offered = ", ".join(s.colours) if s.colours else "none listed"
            parts.append(f"colour {s.colour} is NOT offered (offered colours: {offered})")
    parts.append(f"in stock ({s.stock_count} available overall)" if s.in_stock else "out of stock")
    return ": ".join([parts[0], "; ".join(parts[1:])])


def product_dict(p: ProductInfo) -> dict[str, Any]:
    return {
        "name": p.name,
        "price": format_money(p.price),
        "sizes": p.sizes,
        "colours": p.colours,
        "stock_count": p.stock_count,
    }


def stock_dict(s: StockInfo) -> dict[str, Any]:
    return {
        "name": s.name,
        "stock_count": s.stock_count,
        "in_stock": s.in_stock,
        "size": s.size,
        "size_offered": s.size_offered,
        "colour": s.colour,
        "colour_offered": s.colour_offered,
    }
