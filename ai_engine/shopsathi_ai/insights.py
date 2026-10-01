"""Weekly insights (AI-6, AI-R12): the top customer questions of a week and the products customers asked for that
the shop does not have.

Privacy (section 5.3): the LLM only gets what it needs. Before anything is sent, personal details are removed from
the customers' messages (phone numbers, links, e-mail addresses, addresses, names). Large weeks are summarised in
batches (map) and merged (reduce) so a prompt never grows without limit. Whether a requested product exists is
decided in code through ``product_lookup``, never by the model.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Sequence

from pydantic import BaseModel, Field, ValidationError, field_validator

from shopsathi_ai.language import normalise_digits
from shopsathi_ai.prompts import load, render
from shopsathi_ai.providers.base import LLMProvider, LLMProviderError, LLMResult

MAX_QUESTIONS = 5
MAX_MISSING_PRODUCTS = 5
MAX_MESSAGE_CHARS = 300  # longer messages are cut: a question rarely needs more
BATCH_CHARS = 6000  # about 1,500 tokens of messages per model call
MAX_MESSAGES = 2000  # an even sample beyond this, so a huge week stays affordable
MAX_BATCHES = 40
_PHRASE_CHARS = 200

# --------------------------------------------------------------------------- removing personal details

_LINK = re.compile(r"(https?://\S+|www\.\S+|\b\S+@\S+\.\S+\b)", re.IGNORECASE)
# 7 or more digits, with optional +, spaces, dashes and dots between them (Bangla digits are converted first)
_PHONE = re.compile(r"(?<![\w])\+?\d[\d\s\-().]{5,}\d(?![\w])")
# an address starts at a cue word and runs to the end of the sentence/line
_ADDRESS = re.compile(
    r"(?:\b(?:address|addr|thikana|thikanay|house|flat|road|block|sector|village|vill|holding|plot|post office|upazila|thana)\b|ঠিকানা|বাড়ি|রোড|গ্রাম|থানা)[^\n.?!।]*",
    re.IGNORECASE,
)
# "my name is Rahim Uddin", "amar nam Rahim", "name: Rahim", "আমার নাম রহিম"
_NAME = re.compile(
    r"(\b(?:my name is|amar nam(?: holo| hocche)?|nam|name)\b\s*:?\s*|(?:আমার নাম|নাম)\s*(?:হলো|:)?\s*)"
    r"([A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){0,2}|[ঀ-৿]+(?:\s+[ঀ-৿]+){0,2})",
)
_NAME_NOT = {"interested", "looking", "wondering", "asking", "ready", "sure", "also", "from"}


_MARKER = re.compile(r"\[(?:phone|address|name|link)\]")


def redact(text: str, known_terms: Sequence[str] = ()) -> str:
    """Replace personal details with markers. Best effort on free text, exact for ``known_terms`` (the shop's
    customer names), and applied to the model's answers as well."""
    out = normalise_digits(text)
    for term in sorted({t.strip() for t in known_terms if t and len(t.strip()) >= 2}, key=len, reverse=True):
        out = re.sub(re.escape(term), "[name]", out, flags=re.IGNORECASE)
    out = _LINK.sub("[link]", out)
    out = _PHONE.sub("[phone]", out)
    out = _ADDRESS.sub("[address]", out)

    def _name(m: re.Match) -> str:
        who = m.group(2).split()[0].lower()
        return m.group(0) if who in _NAME_NOT else f"{m.group(1)}[name]"

    out = _NAME.sub(_name, out)
    return re.sub(r"\s+", " ", out).strip()


# --------------------------------------------------------------------------- results


@dataclass(frozen=True)
class QuestionCount:
    question: str
    count: int


@dataclass(frozen=True)
class ProductCount:
    name: str
    count: int


@dataclass
class WeeklyInsights:
    top_questions: list[QuestionCount] = field(default_factory=list)  # at most 5, most asked first
    requested_products: list[ProductCount] = field(default_factory=list)  # every product customers asked for
    missing_products: list[ProductCount] = field(default_factory=list)  # the ones the shop does not have, most asked first
    messages_used: int = 0
    usage: list[LLMResult] = field(default_factory=list)  # one entry per model call (NFR-08)


class _Counted(BaseModel):
    count: int = 1

    @field_validator("count", mode="before")
    @classmethod
    def _count(cls, v):
        try:
            return max(1, int(round(float(v))))
        except (TypeError, ValueError):
            return 1


class _Question(_Counted):
    question: str = Field(min_length=1)


class _Product(_Counted):
    name: str = Field(min_length=1)


def _usable(items, key: str) -> list:
    """Keep the entries that have a non-blank text: one broken entry does not spoil the whole answer."""
    if not isinstance(items, list):
        return []
    return [i for i in items if isinstance(i, dict) and isinstance(i.get(key), str) and i[key].strip()]


class _MapAnswer(BaseModel):
    questions: list[_Question] = Field(default_factory=list)
    products: list[_Product] = Field(default_factory=list)

    @field_validator("questions", mode="before")
    @classmethod
    def _questions(cls, v):
        return _usable(v, "question")

    @field_validator("products", mode="before")
    @classmethod
    def _products(cls, v):
        return _usable(v, "name")


class _ReduceAnswer(BaseModel):
    questions: list[_Question] = Field(default_factory=list)

    @field_validator("questions", mode="before")
    @classmethod
    def _questions(cls, v):
        return _usable(v, "question")


# --------------------------------------------------------------------------- pipeline


def _prepare(messages: Sequence[str], known_terms: Sequence[str]) -> list[str]:
    cleaned: list[str] = []
    for raw in messages:
        text = redact(str(raw), known_terms)[:MAX_MESSAGE_CHARS].strip()
        if len(re.sub(r"\[\w+\]|[\W\d_]+", "", text)) < 2:  # nothing but markers, digits or symbols
            continue
        if text.startswith("[Customer sent"):  # photo / voice placeholders carry no question
            continue
        cleaned.append(text)
    if len(cleaned) > MAX_MESSAGES:  # an even sample, so the whole week is still represented
        step = len(cleaned) / MAX_MESSAGES
        cleaned = [cleaned[int(i * step)] for i in range(MAX_MESSAGES)]
    return cleaned


def _batches(messages: list[str]) -> list[list[str]]:
    batches: list[list[str]] = [[]]
    size = 0
    for m in messages:
        if batches[-1] and size + len(m) > BATCH_CHARS:
            batches.append([])
            size = 0
        batches[-1].append(m)
        size += len(m)
    if len(batches) > MAX_BATCHES:  # keep an even spread of the batches
        step = len(batches) / MAX_BATCHES
        batches = [batches[int(i * step)] for i in range(MAX_BATCHES)]
    return batches


def _ask(llm: LLMProvider, task: str, template: str, payload: dict, model_cls, usage: list[LLMResult]):
    system = load("insights_system.md")
    base = render(load(template), input_json=json.dumps(payload, ensure_ascii=False))
    user = base
    for attempt in range(2):
        try:
            result = llm.generate_json_with_usage(system, user, task=task)
        except LLMProviderError:
            if attempt == 1:
                raise
            continue
        usage.append(result)
        try:
            return model_cls.model_validate(result.data)
        except ValidationError:
            user = base + "\nYour previous answer was invalid. Return exactly the JSON object described."
    raise LLMProviderError(f"the model did not return a valid {task} answer")


def _clean_phrase(text: str, known_terms: Sequence[str]) -> str:
    return redact(text, known_terms)[:_PHRASE_CHARS].strip(" .")


def _top_questions(items: list[tuple[str, int]], limit_count: int, known_terms: Sequence[str]) -> list[QuestionCount]:
    merged: Counter[str] = Counter()
    label: dict[str, str] = {}
    for text, count in items:
        phrase = _clean_phrase(text, known_terms)
        key = phrase.casefold()
        if len(_MARKER.sub("", phrase).strip(" ,.-")) < 3:  # nothing left but removed details
            continue
        merged[key] += max(1, min(count, limit_count))
        label.setdefault(key, phrase)
    ranked = sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_QUESTIONS]
    return [QuestionCount(label[k], min(c, limit_count)) for k, c in ranked]


def summarize_week(
    llm: LLMProvider,
    customer_messages: Sequence[str],
    product_lookup: Callable[[str], bool],
    *,
    known_terms: Sequence[str] = (),
) -> WeeklyInsights:
    """Summarise one week of a shop's customer messages.

    ``product_lookup(name)`` must return True when the shop's catalogue has a matching product. ``known_terms`` are
    exact strings to remove as well (for example the customers' names). Raises ``LLMProviderError`` if the model
    cannot be used: no partial summary is made up.
    """
    messages = _prepare(customer_messages, known_terms)
    insights = WeeklyInsights(messages_used=len(messages))
    if not messages:
        return insights

    try:
        _summarise(llm, messages, product_lookup, known_terms, insights)
    except LLMProviderError as e:
        e.usage = insights.usage  # type: ignore[attr-defined]  # the calls made before the failure still cost money
        raise
    return insights


def _summarise(llm, messages, product_lookup, known_terms, insights: WeeklyInsights) -> None:
    question_items: list[tuple[str, int]] = []
    product_counts: Counter[str] = Counter()
    product_label: dict[str, str] = {}
    batches = _batches(messages)
    per_batch_questions: list[list[_Question]] = []
    for batch in batches:
        answer = _ask(llm, "insights_map", "insights_map_user.md", {"messages": batch}, _MapAnswer, insights.usage)
        per_batch_questions.append(answer.questions)
        for q in answer.questions:
            question_items.append((q.question, q.count))
        for p in answer.products:
            name = _clean_phrase(p.name, known_terms)
            key = name.casefold()
            if len(_MARKER.sub("", name).strip(" ,.-")) < 2:
                continue
            product_counts[key] += min(p.count, len(messages))
            product_label.setdefault(key, name)

    if len(batches) > 1:  # reduce: the model merges the batch lists into one top-5
        payload = {"lists": [[{"question": _clean_phrase(q.question, known_terms), "count": q.count} for q in qs[:12]] for qs in per_batch_questions]}
        merged = _ask(llm, "insights_reduce", "insights_reduce_user.md", payload, _ReduceAnswer, insights.usage)
        question_items = [(q.question, q.count) for q in merged.questions]
    insights.top_questions = _top_questions(question_items, len(messages), known_terms)

    ranked = sorted(product_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    insights.requested_products = [ProductCount(product_label[k], c) for k, c in ranked]
    missing = [p for p in insights.requested_products if not product_lookup(p.name)]
    insights.missing_products = missing[:MAX_MISSING_PRODUCTS]
