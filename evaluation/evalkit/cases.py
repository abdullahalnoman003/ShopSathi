"""Loading and checking the labelled test cases (JSONL, one case per line). See data/README.md for the format."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LANGUAGES = ("bangla", "english", "banglish")
TYPES = ("intent", "answer", "order", "suggestion", "handover")
INTENTS = ("price", "size_stock", "delivery", "suggestion", "order", "complaint", "other")
FLAG_REASONS = ("complaint", "refund", "abusive_language", "low_confidence", "off_topic", "not_in_shop_data", "human_requested")
ORDER_FIELDS = ("product", "size", "colour", "quantity", "name", "phone", "address")

#: which label group each case type must have
REQUIRED_LABEL = {"intent": "intent", "answer": "answer", "order": "order", "suggestion": "suggestion", "handover": "handover"}
LABEL_GROUPS = ("intent", "answer", "order", "suggestion", "handover")


class CaseError(ValueError):
    """A case in the data file is malformed. The message names the line and the problem."""


@dataclass
class Case:
    id: str
    language: str
    type: str
    messages: list[str]
    labels: dict[str, Any]
    sample: bool = False
    note: str = ""
    line: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def _require(cond: bool, line: int, case_id: str, message: str) -> None:
    if not cond:
        raise CaseError(f"line {line} (case {case_id!r}): {message}")


def _number_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)


def validate_labels(labels: dict[str, Any], line: int, case_id: str) -> None:
    unknown = set(labels) - set(LABEL_GROUPS)
    _require(not unknown, line, case_id, f"unknown label group(s) {sorted(unknown)}; allowed: {list(LABEL_GROUPS)}")
    if "intent" in labels:
        _require(labels["intent"] in INTENTS, line, case_id, f"labels.intent must be one of {list(INTENTS)}")
    if "answer" in labels:
        a = labels["answer"]
        _require(isinstance(a, dict), line, case_id, "labels.answer must be an object")
        _require(set(a) <= {"prices", "stock_counts", "available"}, line, case_id, "labels.answer allows prices, stock_counts, available")
        for key in ("prices", "stock_counts"):
            _require(key not in a or _number_list(a[key]), line, case_id, f"labels.answer.{key} must be a list of numbers")
        _require("available" not in a or isinstance(a["available"], bool), line, case_id, "labels.answer.available must be true or false")
        _require(bool(a), line, case_id, "labels.answer must not be empty")
    if "order" in labels:
        o = labels["order"]
        _require(isinstance(o, dict), line, case_id, "labels.order must be an object")
        _require(set(o) <= {"fields", "ready", "phone_invalid"}, line, case_id, "labels.order allows fields, ready, phone_invalid")
        fields = o.get("fields", {})
        _require(isinstance(fields, dict) and set(fields) <= set(ORDER_FIELDS), line, case_id, f"labels.order.fields keys must be among {list(ORDER_FIELDS)}")
        _require("ready" not in o or isinstance(o["ready"], bool), line, case_id, "labels.order.ready must be true or false")
        _require("phone_invalid" not in o or isinstance(o["phone_invalid"], bool), line, case_id, "labels.order.phone_invalid must be true or false")
        _require(bool(fields) or "phone_invalid" in o or "ready" in o, line, case_id, "labels.order must label at least fields, ready or phone_invalid")
    if "suggestion" in labels:
        s = labels["suggestion"]
        _require(isinstance(s, dict), line, case_id, "labels.suggestion must be an object")
        _require(set(s) <= {"max_price", "must_include", "must_not_include", "expect_none"}, line, case_id,
                 "labels.suggestion allows max_price, must_include, must_not_include, expect_none")
        for key in ("must_include", "must_not_include"):
            _require(key not in s or (isinstance(s[key], list) and all(isinstance(v, str) for v in s[key])), line, case_id, f"labels.suggestion.{key} must be a list of product names")
        _require("max_price" not in s or (isinstance(s["max_price"], (int, float)) and not isinstance(s["max_price"], bool)), line, case_id, "labels.suggestion.max_price must be a number")
        _require("expect_none" not in s or isinstance(s["expect_none"], bool), line, case_id, "labels.suggestion.expect_none must be true or false")
        _require(bool(s), line, case_id, "labels.suggestion must not be empty")
    if "handover" in labels:
        h = labels["handover"]
        _require(isinstance(h, dict) and isinstance(h.get("flag"), bool), line, case_id, "labels.handover must be an object with flag: true|false")
        _require(set(h) <= {"flag", "reason"}, line, case_id, "labels.handover allows flag and reason")
        _require("reason" not in h or h["reason"] is None or h["reason"] in FLAG_REASONS, line, case_id, f"labels.handover.reason must be one of {list(FLAG_REASONS)}")
        _require(not (h["flag"] is False and h.get("reason")), line, case_id, "labels.handover.reason only makes sense when flag is true")


def parse_case(raw: dict[str, Any], line: int) -> Case:
    case_id = str(raw.get("id", ""))
    _require(bool(case_id), line, case_id, "id is required")
    _require(raw.get("language") in LANGUAGES, line, case_id, f"language must be one of {list(LANGUAGES)}")
    _require(raw.get("type") in TYPES, line, case_id, f"type must be one of {list(TYPES)}")
    msgs = raw.get("messages")
    _require(isinstance(msgs, list) and msgs and all(isinstance(m, str) and m.strip() for m in msgs), line, case_id, "messages must be a non-empty list of non-empty strings (the customer's turns, in order)")
    labels = raw.get("labels")
    _require(isinstance(labels, dict) and labels, line, case_id, "labels is required")
    validate_labels(labels, line, case_id)
    need = REQUIRED_LABEL[raw["type"]]
    _require(need in labels, line, case_id, f"a case of type {raw['type']!r} needs labels.{need}")
    known = {"id", "language", "type", "messages", "labels", "sample", "note"}
    return Case(
        id=case_id, language=raw["language"], type=raw["type"], messages=[m.strip() for m in msgs], labels=labels,
        sample=bool(raw.get("sample", False)), note=str(raw.get("note", "")), line=line,
        extra={k: v for k, v in raw.items() if k not in known},
    )


def load_cases(path: str | Path) -> list[Case]:
    """Read a JSONL file. Blank lines and lines starting with // or # are ignored. Raises CaseError on the first problem."""
    cases: list[Case] = []
    seen: set[str] = set()
    for number, text in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        text = text.strip()
        if not text or text.startswith(("//", "#")):
            continue
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as e:
            raise CaseError(f"line {number}: not valid JSON ({e.msg})") from e
        _require(isinstance(raw, dict), number, "", "each line must be a JSON object")
        case = parse_case(raw, number)
        _require(case.id not in seen, number, case.id, "duplicate id")
        seen.add(case.id)
        cases.append(case)
    if not cases:
        raise CaseError(f"{path}: no cases found")
    return cases
