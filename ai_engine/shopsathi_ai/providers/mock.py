"""Deterministic offline TEST DOUBLES for automated tests and offline demos.

These are NOT AI: they never understand language or call any model.

* ``MockEmbeddingProvider`` turns text into a hash-based vector (same text -> same vector, no meaning).
* ``MockLLMProvider`` is a small keyword/regex rule set that returns the same JSON shapes as a real model
  (intent + entities, and a templated reply built from the supplied facts). It only knows a handful of
  English / Banglish / Bangla keywords. Use a real provider (``LLM_PROVIDER=openai|gemini``) to judge quality.
"""

import hashlib
import json
import re
from typing import Any

from shopsathi_ai.language import detect_style, normalise_digits
from shopsathi_ai.providers.base import EmbeddingProvider, EmbeddingResult, LLMProvider, LLMResult

# ----------------------------------------------------------------------------- LLM

_INPUT = re.compile(r"<input>\s*(.*?)\s*</input>", re.DOTALL)

_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("complaint", ("complaint", "problem", "kharap", "bad", "wrong", "refund", "late", "damaged", "cheat", "সমস্যা", "খারাপ", "অভিযোগ")),
    ("order", ("order", "nibo", "nebo", "kinbo", "confirm", "buy", "অর্ডার", "নিব", "কিনব")),
    ("delivery", ("delivery", "deliver", "courier", "ডেলিভারি", "ডেলিভারী")),
    ("price", ("price", "dam", "daam", "koto", "kto", "cost", "taka", "দাম", "কত", "টাকা")),
    ("size_stock", ("size", "stock", "ache", "achhe", "available", "xl", "xxl", "has", "have", "আছে", "সাইজ", "স্টক")),
    ("suggestion", ("suggest", "recommend", "dekhan", "dekhao", "show", "option", "দেখান", "দেখাও")),
]
_SIZE = re.compile(r"\b(xxxl|xxl|xl|xs|s|m|l|\d{2})\b", re.IGNORECASE)
_AREA = re.compile(r"([A-Za-zঀ-৿][\wঀ-৿-]*(?: [A-Za-z][\w-]*)?)\s+(?:e|te|এ|তে)\s+(?:delivery|ডেলিভারি)", re.IGNORECASE)
_STOP = {
    "price", "koto", "kto", "dam", "daam", "ache", "achhe", "size", "stock", "the", "is", "are", "what", "how",
    "much", "does", "do", "you", "have", "this", "that", "eta", "ki", "e", "te", "er", "a", "an", "of", "in",
    "pawa", "jabe", "delivery", "charge", "for", "me", "show", "dekhan", "please", "pls", "available", "can",
    "i", "get", "it", "in", "stock", "ta", "ase", "nibo", "order", "want", "need", "lagbe", "chai",
}


class MockLLMProvider(LLMProvider):
    name = "mock"
    model = "mock"

    def generate_json_with_usage(self, system_prompt: str, user_prompt: str, *, task: str = "generic") -> LLMResult:
        match = _INPUT.search(user_prompt)
        payload: dict[str, Any] = json.loads(match.group(1)) if match else {}
        if task == "understand":
            data = self._understand(payload)
        elif task == "reply":
            data = self._reply(payload)
        else:
            data = {"mock": True, "echo": user_prompt}
        tokens_in = len(system_prompt.split()) + len(user_prompt.split())
        tokens_out = len(json.dumps(data, ensure_ascii=False).split())
        return LLMResult(data, tokens_in, tokens_out, self.name, self.model)

    # ---- understand: keyword rules ----

    def _understand(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = normalise_digits(str(payload.get("message", "")))
        lowered = message.lower()
        words = set(re.findall(r"[\wঀ-৿]+", lowered))
        intent = "other"
        for name, keywords in _KEYWORDS:
            if any((k in words) or (not k.isascii() and k in lowered) for k in keywords):
                intent = name
                break
        # "XL ache?" / "eta ki XL e pawa jabe?" are about size; a price word wins when both are present
        if intent == "size_stock" and ({"price", "dam", "daam", "koto"} & words) and not _SIZE.search(message):
            intent = "price"
        size = None
        size_match = _SIZE.search(message)
        if size_match and (intent in ("size_stock", "price", "order") or size_match.group(1).lower() in ("xl", "xxl", "xxxl")):
            size = size_match.group(1).upper()
        area = None
        area_match = _AREA.search(message)
        if area_match:
            area = area_match.group(1).strip()
        elif intent == "delivery":
            candidates = [w for w in re.findall(r"[A-Za-zঀ-৿]+", message) if w.lower() not in _STOP]
            area = candidates[-1] if candidates else None
        product = None
        if intent in ("price", "size_stock", "suggestion", "order") and not area:
            tokens = [w for w in re.findall(r"[A-Za-zঀ-৿]+", message) if w.lower() not in _STOP and len(w) > 2]
            if size:
                tokens = [t for t in tokens if t.upper() != size]
            product = " ".join(tokens) or None
        return {
            "intent": intent,
            "entities": {"product_name": product, "size": size, "colour": None, "area": area},
            "language_style": detect_style(message),
            "confidence": 0.5,
        }

    # ---- reply: templates over the structured facts ----

    def _reply(self, payload: dict[str, Any]) -> dict[str, Any]:
        style = payload.get("language_style", "english")
        intent = payload.get("intent")
        facts = payload.get("structured_facts") or {}
        products = facts.get("products") or []
        stock = facts.get("stock")
        delivery = facts.get("delivery")
        t = _TEMPLATES[style if style in _TEMPLATES else "english"]

        if intent == "delivery" and delivery:
            return {"reply": t["delivery"].format(**delivery)}
        if intent == "size_stock" and stock:
            return {"reply": _stock_reply(t, stock)}
        if intent in ("price", "size_stock") and products:
            p = products[0]
            return {"reply": t["price"].format(name=p["name"], price=p["price"]) + _stock_tail(t, p)}
        if intent == "suggestion" and products:
            listed = "; ".join(f'{p["name"]} - {p["price"]} BDT' for p in products)
            return {"reply": t["suggest"].format(items=listed)}
        chunks = facts.get("chunks") or payload.get("facts") or []
        if chunks:
            return {"reply": str(chunks[0]).replace("Shop policy - ", "")[:300]}
        return {"reply": ""}


_TEMPLATES = {
    "english": {
        "price": "{name} costs {price} BDT.",
        "delivery": "The delivery charge for {area} is {charge} BDT.",
        "suggest": "You may like: {items}.",
        "in_stock": " {n} in stock.",
        "out": " It is currently out of stock.",
        "size_yes": "{name} is offered in size {size}.",
        "size_no": "Sorry, {name} is not offered in size {size}.",
        "colour_yes": "{name} is offered in {colour}.",
        "colour_no": "Sorry, {name} is not offered in {colour}.",
        "plain": "{name}:",
    },
    "banglish": {
        "price": "{name} er dam {price} taka.",
        "delivery": "{area} e delivery charge {charge} taka.",
        "suggest": "Ei gulo dekhte paren: {items}.",
        "in_stock": " Stock e {n} ta ache.",
        "out": " Ekhon stock e nei.",
        "size_yes": "{name} {size} size e ache.",
        "size_no": "Sorry, {name} {size} size e nei.",
        "colour_yes": "{name} {colour} colour e ache.",
        "colour_no": "Sorry, {name} {colour} colour e nei.",
        "plain": "{name}:",
    },
    "bangla": {
        "price": "{name} এর দাম {price} টাকা।",
        "delivery": "{area} এ ডেলিভারি চার্জ {charge} টাকা।",
        "suggest": "এগুলো দেখতে পারেন: {items}।",
        "in_stock": " স্টকে {n}টি আছে।",
        "out": " এখন স্টকে নেই।",
        "size_yes": "{name} {size} সাইজে আছে।",
        "size_no": "দুঃখিত, {name} {size} সাইজে নেই।",
        "colour_yes": "{name} {colour} রঙে আছে।",
        "colour_no": "দুঃখিত, {name} {colour} রঙে নেই।",
        "plain": "{name}:",
    },
}


def _stock_tail(t: dict[str, str], p: dict[str, Any]) -> str:
    return t["in_stock"].format(n=p["stock_count"]) if p["stock_count"] > 0 else t["out"]


def _stock_reply(t: dict[str, str], s: dict[str, Any]) -> str:
    parts: list[str] = []
    if s.get("size") is not None:
        parts.append(t["size_yes" if s["size_offered"] else "size_no"].format(name=s["name"], size=s["size"]))
    if s.get("colour") is not None:
        parts.append(t["colour_yes" if s["colour_offered"] else "colour_no"].format(name=s["name"], colour=s["colour"]))
    tail = t["in_stock"].format(n=s["stock_count"]) if s["in_stock"] else t["out"]
    if not parts:
        parts.append(t["plain"].format(name=s["name"]).rstrip(":"))
        return parts[0] + "." + tail
    return " ".join(parts) + tail


# ------------------------------------------------------------------------ embeddings


class MockEmbeddingProvider(EmbeddingProvider):
    """Same text -> same vector. Different texts -> unrelated vectors (no semantics)."""

    name = "mock"
    model = "mock"

    def __init__(self, dim: int = 1536) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed_with_usage(self, texts: list[str], *, is_query: bool = False) -> EmbeddingResult:
        tokens = sum(len(t.split()) for t in texts)  # rough, deterministic
        return EmbeddingResult([self._vector(t) for t in texts], tokens, self.name, self.model)

    def _vector(self, text: str) -> list[float]:
        out: list[float] = []
        counter = 0
        while len(out) < self._dim:
            digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
            out.extend(b / 255.0 - 0.5 for b in digest)  # centred so unrelated texts are not all "close"
            counter += 1
        return out[: self._dim]
