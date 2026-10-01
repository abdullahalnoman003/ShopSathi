"""Order extraction (AI-4, AI-R07): turn the chat into order fields with structured JSON output.

The model only reads the conversation. What it returns is checked in code afterwards (``ordering.py``):
the product must be a product of this shop, size/colour must be listed options, the quantity a positive
integer, the phone a valid Bangladeshi mobile number, and name/phone/address must really appear in the
customer's own messages.
"""

import json
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ValidationError, field_validator

from shopsathi_ai.prompts import load, render
from shopsathi_ai.providers.base import LLMProvider, LLMProviderError, LLMResult
from shopsathi_ai.understanding import Turn, turns_for_prompt

#: the order fields, in the order the customer is asked for them
ORDER_FIELDS = ("product", "size", "colour", "quantity", "name", "phone", "address")


class OrderExtraction(BaseModel):
    product: str | None = None
    product_en: str | None = None
    size: str | None = None
    colour: str | None = None
    quantity: int | None = None
    name: str | None = None
    phone: str | None = None
    address: str | None = None
    missing_fields: list[str] = Field(default_factory=list)

    @field_validator("product", "product_en", "size", "colour", "name", "phone", "address", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None

    @field_validator("quantity", mode="before")
    @classmethod
    def _quantity(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, bool):
            return None
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            return int(v.strip())
        return v

    @field_validator("missing_fields", mode="before")
    @classmethod
    def _missing(cls, v):
        return [str(x) for x in v] if isinstance(v, list) else []


@dataclass
class ExtractionOutcome:
    extraction: OrderExtraction | None  # None if the model never returned a valid object
    usage: list[LLMResult] = field(default_factory=list)


def extract_order(
    llm: LLMProvider,
    conversation_turns: list[Turn],
    current_pending_fields: dict,
    message: str,
    *,
    max_turns: int = 8,
    max_turn_chars: int = 400,
) -> ExtractionOutcome:
    """Ask the model for the order fields in the conversation; one retry if the JSON is invalid."""
    shown_pending = {k: v for k, v in current_pending_fields.items() if k in ("product_name", "size", "colour", "quantity", "name", "phone", "address") and v}
    payload = {
        "pending": shown_pending,
        "conversation": turns_for_prompt(conversation_turns, max_turns, max_turn_chars),
        "latest_message": message,
    }
    system = load("order_system.md")
    base_user = render(load("order_user.md"), input_json=json.dumps(payload, ensure_ascii=False))
    outcome = ExtractionOutcome(extraction=None)
    user = base_user
    for attempt in range(2):
        try:
            result = llm.generate_json_with_usage(system, user, task="order")
        except LLMProviderError:
            if attempt == 1:
                raise
            continue
        outcome.usage.append(result)
        try:
            outcome.extraction = OrderExtraction.model_validate(result.data)
            return outcome
        except ValidationError:
            user = base_user + "\nYour previous answer was invalid. Return exactly the JSON object described."
    return outcome
