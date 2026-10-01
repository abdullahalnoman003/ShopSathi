"""Test helpers: a scripted LLM and an in-memory shop (fake ShopDataGateway)."""

import json
import re
from decimal import Decimal

from shopsathi_ai.interfaces import DeliveryChargeInfo, ProductInfo, RetrievedChunk, StockInfo
from shopsathi_ai.phrases import phrase
from shopsathi_ai.providers.base import LLMProvider, LLMProviderError, LLMResult


class ScriptedLLM(LLMProvider):
    """Returns queued answers per task and records every prompt it was given."""

    name = "scripted"
    model = "scripted-1"

    def __init__(self, understand=None, reply=None):
        self.queues = {"understand": list(understand or []), "reply": list(reply or [])}
        self.calls: list[tuple[str, str, str]] = []  # (task, system, user)

    def generate_json_with_usage(self, system_prompt, user_prompt, *, task="generic"):
        self.calls.append((task, system_prompt, user_prompt))
        queue = self.queues[task]
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return LLMResult(item, 10, 5, self.name, self.model)

    def payloads(self, task):
        out = []
        for t, _, user in self.calls:
            if t == task:
                out.append(json.loads(re.search(r"<input>\s*(.*?)\s*</input>", user, re.DOTALL).group(1)))
        return out


def und(intent="other", product=None, size=None, colour=None, area=None, confidence=0.9, style="english"):
    return {
        "intent": intent,
        "entities": {"product_name": product, "size": size, "colour": colour, "area": area},
        "language_style": style,
        "confidence": confidence,
    }


SAREE = ProductInfo(1, "Red Jamdani Saree", Decimal("4800.00"), [], ["Red"], 6, "Hand-woven red saree.")
PANJABI = ProductInfo(2, "Cotton Panjabi", Decimal("1850"), ["M", "L", "XL"], ["White", "Navy"], 24)
LIPSTICK = ProductInfo(3, "Matte Lipstick", Decimal("650"), [], ["Rose"], 0)


class FakeGateway:
    """One shop's catalogue and policy in memory. Records every call."""

    def __init__(self, products=(SAREE, PANJABI, LIPSTICK), areas=None, chunks=()):
        self.products = list(products)
        self.areas = areas if areas is not None else {"khagan": ("Khagan", Decimal("100")), "inside dhaka": ("Inside Dhaka", Decimal("60"))}
        self.chunks = list(chunks)
        self.usage: list[tuple] = []
        self.calls: list[tuple] = []

    def vector_search(self, shop_id, query_vector, top_k, source_types=None):
        self.calls.append(("vector_search", shop_id))
        return self.chunks[:top_k]

    def log_ai_usage(self, shop_id, operation, provider, model, input_tokens, output_tokens=0):
        self.usage.append((shop_id, operation, provider, model, input_tokens, output_tokens))

    def search_products(self, shop_id, query_text, query_vector, top_k):
        self.calls.append(("search_products", shop_id, query_text))
        words = [w for w in re.findall(r"\w+", query_text.lower()) if len(w) >= 3]
        found = []
        for p in self.products:
            hit = sum(1 for w in words if w in p.name.lower())
            if hit:
                found.append(ProductInfo(**{**p.__dict__, "match": "name", "score": hit / len(words)}))
        return sorted(found, key=lambda p: -p.score)[:top_k]

    def check_stock(self, shop_id, product_id, size=None, colour=None):
        self.calls.append(("check_stock", shop_id, product_id))
        p = next((p for p in self.products if p.id == product_id), None)
        if p is None:
            return None
        return StockInfo(
            p.id, p.name, p.stock_count, p.stock_count > 0, p.sizes, p.colours,
            size=size, size_offered=None if size is None else size.lower() in [s.lower() for s in p.sizes],
            colour=colour, colour_offered=None if colour is None else colour.lower() in [c.lower() for c in p.colours],
        )

    def get_delivery_charge(self, shop_id, area_text):
        self.calls.append(("get_delivery_charge", shop_id, area_text))
        hit = self.areas.get(re.sub(r"\W+", " ", area_text.lower()).strip())
        return DeliveryChargeInfo(True, hit[0], hit[1]) if hit else DeliveryChargeInfo(False)


def policy_chunk(text, score=0.8):
    return RetrievedChunk("policy", 1, text, score)


CHECK = {style: phrase("check_with_shop", style) for style in ("english", "banglish", "bangla")}
