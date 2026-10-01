"""Smart handover (AI-5, AI-R10, AI-R04): decide when a chat must be passed to the seller.

A chat is flagged for exactly one of these reasons (the first that applies, in this priority):
``abusive_language``, ``refund``, ``complaint``, ``human_requested``, ``off_topic``, ``low_confidence``,
``not_in_shop_data``. The understanding step gives structured flags (refund request, abusive language, request
for a person, off-topic) and a confidence; code adds a precise keyword check so that these safety-relevant
cases are not left to the model alone.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache

from shopsathi_ai.language import normalise_digits
from shopsathi_ai.prompts import load
from shopsathi_ai.understanding import Understanding

FLAG_REASONS = (
    "complaint",
    "refund",
    "abusive_language",
    "low_confidence",
    "off_topic",
    "not_in_shop_data",
    "human_requested",
)
#: when several reasons apply, the first one in this list is recorded
PRIORITY = (
    "abusive_language",
    "refund",
    "complaint",
    "human_requested",
    "off_topic",
    "low_confidence",
    "not_in_shop_data",
)
#: default for AI_CONFIDENCE_THRESHOLD: understanding confidence below this means the AI is not sure
DEFAULT_CONFIDENCE_THRESHOLD = 0.5

#: technical failures are recorded under one of the flag reasons; the original name stays in ``detail``
FAILURE_REASONS = {
    "not_in_shop_data": "not_in_shop_data",
    "order_product_unavailable": "not_in_shop_data",
    "complaint": "complaint",
    "understanding_failed": "low_confidence",
    "ai_unavailable": "low_confidence",
    "reply_not_grounded": "low_confidence",
    "reply_wrong_script": "low_confidence",
    "order_extraction_failed": "low_confidence",
}


@dataclass(frozen=True)
class HandoverDecision:
    flag: bool
    reason: str | None = None


@dataclass
class EngineState:
    """What the engine already knows when it decides."""

    #: the shop's data has no answer for the question (AI-R04)
    not_in_shop_data: bool = False
    #: an order is being collected: short data-only answers ("Rahim", "XL") are not a sign of confusion
    order_in_progress: bool = False
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD


def reason_for_failure(detail: str) -> str:
    """The flag reason under which a technical failure ("ai_unavailable", ...) is recorded."""
    return FAILURE_REASONS.get(detail, "low_confidence")


# ------------------------------------------------------------------ keyword check


@lru_cache(maxsize=1)
def _patterns() -> dict[str, tuple[re.Pattern[str] | None, tuple[str, ...]]]:
    terms = json.loads(load("handover_terms.json"))
    out: dict[str, tuple[re.Pattern[str] | None, tuple[str, ...]]] = {}
    for kind in ("abusive", "human", "refund"):
        latin = [t for t in terms[kind] if t.isascii()]
        bangla = tuple(t for t in terms[kind] if not t.isascii())
        regex = None
        if latin:
            alternatives = "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in sorted(latin, key=len, reverse=True))
            regex = re.compile(rf"(?<![A-Za-z0-9])(?:{alternatives})(?![A-Za-z0-9])", re.IGNORECASE)
        out[kind] = (regex, bangla)
    return out


def detect_terms(message: str) -> set[str]:
    """Which of ``abusive``, ``human``, ``refund`` the message contains (precise phrases, not single words
    like "refund" alone, so a question about the refund policy is not flagged)."""
    text = " ".join(normalise_digits(message).split())
    found: set[str] = set()
    for kind, (regex, bangla) in _patterns().items():
        if (regex is not None and regex.search(text)) or any(t in text for t in bangla):
            found.add(kind)
    return found


# ---------------------------------------------------------------------- decision


def decide_handover(
    message: str, understanding: Understanding | None, engine_state: EngineState | None = None
) -> HandoverDecision:
    """Flag the chat (and say why) or let the AI answer. ``understanding`` is None when it failed."""
    state = engine_state or EngineState()
    terms = detect_terms(message)
    reasons: set[str] = set()

    if "abusive" in terms or (understanding and understanding.abusive_language):
        reasons.add("abusive_language")
    if "refund" in terms or (understanding and understanding.refund_request):
        reasons.add("refund")
    if understanding and understanding.intent == "complaint":
        reasons.add("complaint")
    if "human" in terms or (understanding and understanding.human_requested):
        reasons.add("human_requested")
    if understanding and understanding.off_topic:
        reasons.add("off_topic")
    if not state.order_in_progress and (understanding is None or understanding.confidence < state.confidence_threshold):
        reasons.add("low_confidence")
    if state.not_in_shop_data:
        reasons.add("not_in_shop_data")

    for reason in PRIORITY:
        if reason in reasons:
            return HandoverDecision(True, reason)
    return HandoverDecision(False, None)
