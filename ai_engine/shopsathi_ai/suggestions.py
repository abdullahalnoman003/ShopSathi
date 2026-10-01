"""Product suggestions (AI-3, AI-R05, AI-R06).

1. ``extract_needs``: the customer's stated needs (product type, budget, size, colour, occasion) as validated JSON.
2. ``find_suggestions``: candidates from the catalogue (name match, then similarity), then **filtered in code**
   on live data: stock must be above zero, the stated size/colour must be offered, the price must be within the
   budget. The language model only writes the short reply text, from the products that passed.

Suggestions use only what the customer said they need and the shop's stock; nothing is guessed about the
customer (gender, religion, background).
"""

import json
from dataclasses import dataclass, field
from decimal import Decimal

from pydantic import BaseModel, Field, ValidationError, field_validator

from shopsathi_ai.budget import parse_budget, resolve_budget  # noqa: F401  (re-exported)
from shopsathi_ai.interfaces import ProductInfo, ShopDataGateway
from shopsathi_ai.prompts import load, render
from shopsathi_ai.providers.base import LLMProvider, LLMProviderError, LLMResult
from shopsathi_ai.tools import ShopTools
from shopsathi_ai.understanding import Turn, turns_for_prompt

MAX_SUGGESTIONS = 3


class Needs(BaseModel):
    product_type: str | None = None
    product_type_en: str | None = None
    budget_max: Decimal | None = Field(default=None, ge=0)
    size: str | None = None
    colour: str | None = None
    occasion: str | None = None

    @field_validator("product_type", "product_type_en", "size", "colour", "occasion", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None

    @field_validator("budget_max", mode="before")
    @classmethod
    def _budget(cls, v):
        if v in (None, "", 0, "0"):
            return None
        return v

    def is_empty(self) -> bool:
        return not any((self.product_type, self.product_type_en, self.budget_max, self.size, self.colour, self.occasion))


@dataclass
class NeedsOutcome:
    needs: Needs
    usage: list[LLMResult] = field(default_factory=list)
    #: True when the model gave no usable answer and the needs come from the understood entities and code
    used_fallback: bool = False


# ------------------------------------------------------------------- needs


def extract_needs(
    llm: LLMProvider,
    message: str,
    recent_turns: list[Turn],
    entities: dict[str, str | None],
    *,
    max_turns: int = 6,
    max_turn_chars: int = 300,
) -> NeedsOutcome:
    """Structured-output extraction of the stated needs; one retry; falls back to the understood entities."""
    # Only the latest message: earlier requests (an old budget, size or occasion) must not leak into this one.
    payload = {"message": message}
    system = load("needs_system.md")
    base_user = render(load("needs_user.md"), input_json=json.dumps(payload, ensure_ascii=False))
    usage: list[LLMResult] = []
    user = base_user
    needs: Needs | None = None
    for attempt in range(2):
        try:
            result = llm.generate_json_with_usage(system, user, task="needs")
        except LLMProviderError:
            break
        usage.append(result)
        try:
            needs = Needs.model_validate(result.data)
            break
        except ValidationError:
            user = base_user + "\nYour previous answer was invalid. Return exactly the JSON object described."
    # An unusable or empty answer: use what the understanding step already found. Individual gaps are filled too.
    fallback = needs is None or needs.is_empty()
    base = needs or Needs()
    needs = base.model_copy(
        update={
            "product_type": base.product_type or entities.get("product_name"),
            "product_type_en": base.product_type_en or entities.get("product_name_en"),
            "size": base.size or entities.get("size"),
            "colour": base.colour or entities.get("colour"),
            "budget_max": resolve_budget(message, base.budget_max),
        }
    )
    return NeedsOutcome(needs, usage, fallback)


# --------------------------------------------------------------- selection


@dataclass
class SuggestionConfig:
    max_suggestions: int = MAX_SUGGESTIONS
    pool: int = 10
    min_name_match: float = 0.5
    min_product_score: float = 0.3


def matches_needs(p: ProductInfo, needs: Needs) -> bool:
    """The hard filters, applied in code to live product data. A product with no stock never passes."""
    if p.stock_count <= 0:
        return False
    if needs.budget_max is not None and p.price > needs.budget_max:
        return False
    if needs.size is not None and needs.size.casefold() not in {s.casefold() for s in p.sizes}:
        return False
    if needs.colour is not None and needs.colour.casefold() not in {c.casefold() for c in p.colours}:
        return False
    return True


def find_suggestions(
    tools: ShopTools,
    gateway: ShopDataGateway,
    shop_id: int,
    needs: Needs,
    query_vector: list[float],
    cfg: SuggestionConfig | None = None,
) -> list[ProductInfo]:
    """Up to 3 in-stock products that fit the stated needs, best first (possibly none)."""
    cfg = cfg or SuggestionConfig()
    ranked: dict[int, tuple[int, float, ProductInfo]] = {}  # id -> (source rank, -score, product)

    def offer(p: ProductInfo, rank: int, score: float) -> None:
        if p.id not in ranked or (rank, -score) < ranked[p.id][:2]:
            ranked[p.id] = (rank, -score, p)

    terms = needs.product_type_en or needs.product_type
    if terms:
        for p in tools.search_products(terms, query_vector, cfg.pool):
            if p.match == "name" and p.score >= cfg.min_name_match:
                offer(p, 0, p.score)
            elif p.match == "semantic" and p.score >= cfg.min_product_score:
                offer(p, 1, p.score)
    else:
        # No product type: use similarity to the other stated needs (e.g. the occasion), then plain browsing.
        hits = [
            h
            for h in gateway.vector_search(shop_id, query_vector, cfg.pool, ["product"])
            if h.score >= cfg.min_product_score
        ]
        scores = {h.source_id: h.score for h in hits}
        if scores:
            for p in tools.get_products(list(scores)):
                offer(p, 1, scores[p.id])
        for p in tools.browse_products(needs.budget_max, cfg.pool * 2):
            offer(p, 2, 0.0)

    ordered = sorted(
        (item for item in ranked.values() if matches_needs(item[2], needs)),
        key=lambda item: (item[0], item[1], item[2].price, item[2].id),
    )
    chosen = [item[2] for item in ordered[: cfg.max_suggestions]]
    if not chosen:
        return []
    # Read the chosen products once more just before replying, so a sale that just happened is respected.
    fresh = {p.id: p for p in tools.get_products([p.id for p in chosen])}
    return [fresh[p.id] for p in chosen if p.id in fresh and matches_needs(fresh[p.id], needs)]


def suggestion_card(p: ProductInfo) -> dict:
    """What the chat shows for a suggested product: id, name, price and the first photo URL."""
    return {"id": p.id, "name": p.name, "price": float(p.price), "photo": p.photos[0] if p.photos else None}
