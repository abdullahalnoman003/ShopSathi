"""Step 1 of the pipeline: understand the customer message (intent + key details) as validated JSON."""

import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from shopsathi_ai.prompts import load, render
from shopsathi_ai.providers.base import LLMProvider, LLMProviderError, LLMResult

Intent = Literal["price", "size_stock", "delivery", "suggestion", "order", "complaint", "other"]
INTENTS: tuple[str, ...] = ("price", "size_stock", "delivery", "suggestion", "order", "complaint", "other")
_INTENT_AS_FLAG = {
    "off_topic": "off_topic",
    "refund": "refund_request",
    "refund_request": "refund_request",
    "abusive": "abusive_language",
    "abusive_language": "abusive_language",
    "human": "human_requested",
    "human_requested": "human_requested",
}


class Entities(BaseModel):
    product_name: str | None = None
    #: the product name in English/Latin letters (translated or transliterated), used to search the catalogue
    product_name_en: str | None = None
    size: str | None = None
    colour: str | None = None
    area: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None


class Understanding(BaseModel):
    intent: Intent
    entities: Entities = Field(default_factory=Entities)
    language_style: Literal["bangla", "english", "banglish"] = "english"
    confidence: float = Field(ge=0, le=1)
    #: structured handover signals (see handover.py); all default to False
    refund_request: bool = False
    abusive_language: bool = False
    human_requested: bool = False
    off_topic: bool = False

    @model_validator(mode="before")
    @classmethod
    def _handover_words_used_as_intent(cls, data):
        """A model sometimes writes a handover flag name as the intent ("off_topic"). Keep the signal: it
        becomes the matching flag with intent "other", so a safety flag is never lost to a validation error."""
        if isinstance(data, dict) and isinstance(data.get("intent"), str):
            flag = _INTENT_AS_FLAG.get(data["intent"].strip().lower().replace("-", "_").replace(" ", "_"))
            if flag:
                data = {**data, "intent": "other", flag: True}
        return data


@dataclass
class Turn:
    """One earlier message in the chat (only the last few are ever given to the LLM)."""

    role: Literal["customer", "ai", "seller"]
    text: str
    #: entities understood for that customer message / used in that AI reply (to resolve "eta", "this one")
    entities: dict[str, str | None] = field(default_factory=dict)


@dataclass
class UnderstandOutcome:
    understanding: Understanding | None  # None if the model never returned valid output
    usage: list[LLMResult] = field(default_factory=list)


def turns_for_prompt(turns: list[Turn], limit: int, max_chars: int) -> list[dict[str, str]]:
    """Only the last few turns, each shortened: the LLM gets what it needs for one reply, not the history."""
    names = {"customer": "customer", "ai": "assistant", "seller": "shop staff"}
    return [{"from": names[t.role], "text": t.text[:max_chars]} for t in turns[-limit:]]


def understand(
    llm: LLMProvider, message: str, recent_turns: list[Turn], *, max_turns: int = 6, max_turn_chars: int = 300
) -> UnderstandOutcome:
    """Ask the LLM for intent/entities and validate the JSON; one retry if it is invalid."""
    payload = {"message": message, "recent_messages": turns_for_prompt(recent_turns, max_turns, max_turn_chars)}
    system = load("understand_system.md")
    base_user = render(load("understand_user.md"), input_json=json.dumps(payload, ensure_ascii=False))
    outcome = UnderstandOutcome(understanding=None)
    user = base_user
    for attempt in range(2):
        try:
            result = llm.generate_json_with_usage(system, user, task="understand")
        except LLMProviderError:
            if attempt == 1:
                raise
            continue
        outcome.usage.append(result)
        try:
            outcome.understanding = Understanding.model_validate(result.data)
            return outcome
        except ValidationError as e:
            fields = ", ".join(sorted({str(err["loc"][0]) for err in e.errors() if err["loc"]})) or "the object"
            user = base_user + f"\nYour previous answer was invalid ({fields}). Return exactly the JSON object described."
    return outcome
