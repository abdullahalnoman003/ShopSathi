"""Step 3 of the pipeline: write the reply from the supplied facts, then check it in code."""

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from shopsathi_ai.language import normalise_digits
from shopsathi_ai.prompts import load, render
from shopsathi_ai.providers.base import LLMProvider, LLMResult
from shopsathi_ai.understanding import Turn, turns_for_prompt

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_BANGLA_LETTER = re.compile(r"[\u0980-\u09FF]")


def script_matches_style(text: str, style: str) -> bool:
    """Bangla replies must be in Bangla script (English product names may be mixed in); English and Banglish
    replies use English letters only."""
    bangla_letters = len(_BANGLA_LETTER.findall(text))
    if style == "bangla":
        return bangla_letters >= 4
    return bangla_letters == 0


def numbers_in(text: str) -> set[Decimal]:
    """All numbers in a text as Decimals ("4,800" and "4800.00" both become 4800)."""
    found: set[Decimal] = set()
    for raw in _NUMBER.findall(normalise_digits(text)):
        cleaned = raw.replace(",", "")
        try:
            found.add(Decimal(cleaned).normalize())
        except InvalidOperation:
            continue
    return found


def ungrounded_numbers(reply: str, facts: list[str]) -> list[str]:
    """Numbers in the reply that appear in none of the facts (prices and stock must match exactly)."""
    allowed: set[Decimal] = set()
    for fact in facts:
        allowed |= numbers_in(fact)
    return sorted(format(n, "f") for n in numbers_in(reply) - allowed)


#: shown to the model with every reply request: a concrete instruction and example beat an abstract rule
STYLE_INSTRUCTIONS = {
    "bangla": "Write the reply in Bangla script (বাংলা অক্ষরে). Keep product names as in the facts. "
    "Example: 'Red Jamdani Saree এর দাম 4800 টাকা।'",
    "banglish": "Write the reply in Banglish: Bangla words in English letters only, no Bangla script. "
    "Example: 'Red Jamdani Saree er dam 4800 taka.'",
    "english": "Write the reply in English, English letters only.",
}


@dataclass
class ReplyRequest:
    message: str
    intent: str
    language_style: str
    facts: list[str]
    #: structured copies of the facts, used by test doubles and future features (not required by real models)
    structured: dict = field(default_factory=dict)
    recent_turns: list[Turn] = field(default_factory=list)
    shop_name: str = ""
    max_turns: int = 6
    max_turn_chars: int = 300


@dataclass
class ReplyOutcome:
    text: str | None  # None => use the "I'll check with the shop" fallback
    reason: str | None = None
    usage: list[LLMResult] = field(default_factory=list)


def write_reply(llm: LLMProvider, req: ReplyRequest) -> ReplyOutcome:
    """Generate a reply; if a number is not in the facts, regenerate once, then give up (fallback)."""
    payload = {
        "message": req.message,
        "intent": req.intent,
        "language_style": req.language_style,
        "write_in": STYLE_INSTRUCTIONS.get(req.language_style, ""),
        "shop_name": req.shop_name,
        "recent_messages": turns_for_prompt(req.recent_turns, req.max_turns, req.max_turn_chars),
        "facts": req.facts,
        "structured_facts": req.structured,
    }
    system = load("reply_system.md")
    template = load("reply_user.md")
    outcome = ReplyOutcome(text=None, reason="reply_not_grounded")
    retry_note = ""
    for _ in range(2):
        user = render(template, input_json=json.dumps(payload, ensure_ascii=False, default=str), retry_note=retry_note)
        result = llm.generate_json_with_usage(system, user, task="reply")
        outcome.usage.append(result)
        text = str(result.data.get("reply", "")).strip()
        if not text:
            retry_note = '\nYour previous answer had no reply text. Return {"reply": "..."}.\n'
            outcome.reason = "empty_reply"
            continue
        if not script_matches_style(text, req.language_style):
            outcome.reason = "reply_wrong_script"
            retry_note = (
                f"\nYour previous reply was not in the customer's writing style ({req.language_style}). "
                f"{STYLE_INSTRUCTIONS.get(req.language_style, '')}\n"
            )
            continue
        bad = ungrounded_numbers(text, req.facts)
        if not bad:
            outcome.text, outcome.reason = text, None
            return outcome
        outcome.reason = "reply_not_grounded"
        retry_note = (
            f"\nYour previous reply used numbers that are not in the facts ({', '.join(bad)}). "
            "Use only numbers that appear in the facts, copied exactly.\n"
        )
    return outcome
