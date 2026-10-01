"""Running the labelled cases through the real ``ConversationEngine``.

Each case is a separate chat. Its customer turns are sent one after another; the AI's own replies become the context
of the next turn, and the pending order is carried over, exactly like the backend's ``ConversationService`` does
(short-term memory of the last turns, cleared when an order is drafted). After a turn that hands the chat to a
person the AI is paused in production, so the remaining turns of that case are not run."""

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shopsathi_ai.config import AISettings
from shopsathi_ai.engine import ChatContext, ConversationEngine, EngineConfig, EngineResult
from shopsathi_ai.providers.base import EmbeddingProvider, LLMProvider
from shopsathi_ai.providers.factory import get_embedding_provider, get_llm_provider
from shopsathi_ai.understanding import Turn

from evalkit.cases import Case
from evalkit.gateway import EvalGateway, Fixture, load_fixture

MEMORY_TURNS = 8  # the backend's CHAT_MEMORY_TURNS default
ORDER_SENT_PLACEHOLDER = "(the customer's order details were sent to the shop)"


@dataclass
class TurnResult:
    message: str
    reply: str
    intent: str
    confidence: float
    language_style: str
    flagged: bool
    flag_reason: str | None
    flag_detail: str | None
    suggested: list[dict[str, Any]]  # [{"id": 3, "name": "...", "price": 1450.0}]
    order_ready: dict[str, Any] | None
    order_missing: list[str]
    pending_order: dict[str, Any] | None
    seconds: float
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class CaseResult:
    case: Case
    turns: list[TurnResult] = field(default_factory=list)
    stopped_after_flag: bool = False
    error: str | None = None  # the engine raised: the case counts as failed for every label it has

    @property
    def last(self) -> TurnResult | None:
        return self.turns[-1] if self.turns else None

    @property
    def seconds(self) -> float:
        return sum(t.seconds for t in self.turns)


def load_env_file(path: str | Path) -> int:
    """Put KEY=value lines of a .env file into the environment (existing variables win). Returns how many were set.
    Values are never printed."""
    count = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            count += 1
    return count


def build_providers(provider: str, embedding_provider: str | None = None, model: str | None = None) -> tuple[LLMProvider, EmbeddingProvider, AISettings]:
    """``provider`` is the chat model: mock | openai | gemini. The embeddings default to mock for the mock model and to
    openai otherwise. Keys come from the environment (OPENAI_API_KEY, GEMINI_API_KEY)."""
    embedding = embedding_provider or ("mock" if provider == "mock" else "openai")
    overrides: dict[str, Any] = {"llm_provider": provider, "embedding_provider": embedding}
    if model:
        overrides["llm_model"] = model
    settings = AISettings(**overrides)
    return get_llm_provider(settings), get_embedding_provider(settings), settings


def _entities(result: EngineResult) -> dict[str, str | None]:
    return result.entities


def run_case(case: Case, engine: ConversationEngine, gateway: EvalGateway, fixture: Fixture) -> CaseResult:
    out = CaseResult(case)
    turns: list[Turn] = []
    pending: dict | None = None
    first = True
    for message in case.messages:
        ctx = ChatContext(shop_name=fixture.shop_name, is_first_ai_reply=first, recent_turns=list(turns), pending_order=pending)
        started = time.perf_counter()
        try:
            result = engine.process_customer_message(fixture.shop_id, ctx, message)
        except Exception as e:  # noqa: BLE001 - a crash is a failed case, not the end of the run
            out.error = f"{e.__class__.__name__}: {e}"[:300]
            return out
        seconds = time.perf_counter() - started
        extras = result.extras
        ready = extras.get("order_ready")
        out.turns.append(
            TurnResult(
                message=message,
                reply=result.reply_text,
                intent=result.intent,
                confidence=float(result.confidence),
                language_style=result.language_style,
                flagged=bool(result.handover.needed),
                flag_reason=result.handover.reason,
                flag_detail=result.handover.detail,
                suggested=[{"id": c.get("id"), "name": c.get("name"), "price": c.get("price")} for c in extras.get("suggested_products", [])],
                order_ready=dict(ready) if ready else None,
                order_missing=list(extras.get("order_missing", [])),
                pending_order=dict(result.pending_order) if result.pending_order else None,
                seconds=seconds,
                tokens_in=sum(u.input_tokens for u in result.usage),
                tokens_out=sum(u.output_tokens for u in result.usage),
            )
        )
        first = first and not result.disclosure_included
        # the same bookkeeping as the backend: pending order, short-term memory
        if ready is not None:
            pending, turns = None, [Turn("ai", ORDER_SENT_PLACEHOLDER, {})]
        else:
            pending = result.pending_order
            turns = (turns + [Turn("customer", message, _entities(result)), Turn("ai", result.reply_text, _entities(result))])[-MEMORY_TURNS:]
        if result.handover.needed:
            out.stopped_after_flag = message is not case.messages[-1]
            break  # production pauses the AI for a flagged chat
    return out


def run_cases(cases: list[Case], llm: LLMProvider, embedder: EmbeddingProvider, fixture: Fixture | None = None, config: EngineConfig | None = None,
              progress=None) -> tuple[list[CaseResult], EvalGateway]:
    fixture = fixture or load_fixture()
    gateway = EvalGateway(fixture, embedder)
    engine = ConversationEngine(llm, embedder, gateway, config)
    results: list[CaseResult] = []
    for i, case in enumerate(cases, start=1):
        results.append(run_case(case, engine, gateway, fixture))
        if progress:
            progress(i, len(cases), case)
    return results, gateway
