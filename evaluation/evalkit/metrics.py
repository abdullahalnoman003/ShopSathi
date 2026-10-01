"""The accuracy metrics. Everything here is pure (no model calls), so it is unit-tested on its own.

Each labelled case is turned into a list of ``Check`` records; a metric is the share of its checks that passed,
overall and per language (section 5.3: Bangla script, English and Banglish are reported separately).
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from shopsathi_ai.language import normalise_digits
from shopsathi_ai.validators import normalize_and_validate_bd_phone

from evalkit.cases import LANGUAGES, Case
from evalkit.gateway import Fixture
from evalkit.runner import CaseResult

#: key -> (proposal reference, description, target, kind). kind: "rate" (share of passed checks >= target),
#: "zero" (no violation allowed) or "info" (reported, the proposal gives no number).
METRICS: dict[str, dict[str, Any]] = {
    "intent_accuracy": {"ref": "AI-R01", "title": "Intent accuracy", "target": 0.85, "kind": "rate"},
    "price_stock_accuracy": {"ref": "AI-R03", "title": "Prices and stock values match the catalogue exactly", "target": 0.95, "kind": "rate"},
    "order_field_accuracy": {"ref": "AI-R07", "title": "Order fields correct (product, size, colour, quantity, name, phone, address)", "target": 0.90, "kind": "rate"},
    "zero_stock_suggestions": {"ref": "AI-R06", "title": "Zero-stock products suggested (violations)", "target": 0, "kind": "zero"},
    "phone_reask": {"ref": "AI-R08", "title": "Invalid phone numbers are asked for again", "target": 1.0, "kind": "rate"},
    "flag_precision": {"ref": "AI-R04/AI-R10", "title": "Flagged chats that needed a person (precision)", "target": None, "kind": "info"},
    "flag_recall": {"ref": "AI-R04/AI-R10", "title": "Chats that needed a person and were flagged (recall)", "target": None, "kind": "info"},
    "flag_reason_accuracy": {"ref": "AI-R10", "title": "Correct flag reason", "target": None, "kind": "info"},
    "suggestion_quality": {"ref": "AI-3", "title": "Suggestions match the labelled expectations", "target": None, "kind": "info"},
    "order_completion": {"ref": "AI-R09", "title": "Order complete / incomplete as labelled", "target": None, "kind": "info"},
    "language_match": {"ref": "section 5.3", "title": "Message language recognised as labelled", "target": None, "kind": "info"},
}
CHECK_KEYS = [k for k in METRICS if k not in ("flag_precision", "flag_recall")]


@dataclass
class Check:
    metric: str
    case_id: str
    language: str
    ok: bool
    expected: Any = None
    actual: Any = None
    detail: str = ""


# ----------------------------------------------------------------------------- numbers and wording

_NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def numbers_in(text: str) -> list[Decimal]:
    """The numbers written in a text (Bangla digits and thousands separators understood), in order."""
    out: list[Decimal] = []
    for m in _NUMBER.findall(normalise_digits(text)):
        try:
            out.append(Decimal(m.replace(",", "")).normalize())
        except InvalidOperation:
            pass
    return out


def _dec(value: Any) -> Decimal:
    return Decimal(str(value)).normalize()


def fixture_numbers(fixture: Fixture) -> set[Decimal]:
    """Every number that may legitimately appear in a reply: prices, stock counts, charges, and the digits that are
    part of product names, sizes and the policy text."""
    nums: set[Decimal] = set()
    for p in fixture.products:
        nums.add(_dec(p.price))
        nums.add(_dec(p.stock_count))
        for text in (p.name, *p.sizes, *p.colours):
            nums.update(numbers_in(text))
    for _, charge in fixture.policy.delivery_areas:
        nums.add(_dec(charge))
    for text in (fixture.policy.delivery_time, fixture.policy.return_rules, fixture.policy.payment_options):
        nums.update(numbers_in(text))
    return nums


_OUT = [r"out of stock", r"not in stock", r"sold out", r"unavailable", r"not available", r"no longer available", r"stock e nei", r"stock nei",
        r"\bnei\b", r"নেই", r"স্টকে নেই", r"শেষ"]
_IN = [r"in stock", r"\bavailable\b", r"stock e ache", r"\bache\b", r"\bachhe\b", r"আছে", r"স্টকে আছে", r"\byes\b", r"\bji\b"]


def availability_claim(text: str) -> str | None:
    """'unavailable' if the reply says the product is not available, 'available' if it says it is, else None. A keyword
    check in English, Banglish and Bangla: the per-case failure list shows the reply so a person can confirm."""
    low = normalise_digits(text).casefold()
    if any(re.search(p, low) for p in _OUT):
        return "unavailable"
    if any(re.search(p, low) for p in _IN):
        return "available"
    return None


# ----------------------------------------------------------------------------- order fields

_PUNCT = re.compile(r"[^\w\s]|_", re.UNICODE)


def _norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", normalise_digits(str(value or "")).casefold())).strip()


def order_field_matches(field_name: str, expected: Any, actual: Any) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if field_name == "quantity":
        try:
            return int(expected) == int(actual)
        except (TypeError, ValueError):
            return False
    if field_name == "phone":
        e, a = normalize_and_validate_bd_phone(str(expected)), normalize_and_validate_bd_phone(str(actual))
        return e is not None and e == a
    e, a = _norm_text(expected), _norm_text(actual)
    if field_name == "address":
        return bool(e) and (e == a or e in a or a in e)  # the AI may keep a little more or less of the address text
    return e == a


_READY_KEYS = {"product": "product_name", "size": "size", "colour": "colour", "quantity": "quantity", "name": "customer_name", "phone": "customer_phone", "address": "customer_address"}
_PENDING_KEYS = {"product": "product_name", "size": "size", "colour": "colour", "quantity": "quantity", "name": "name", "phone": "phone", "address": "address"}


def final_order_fields(result: CaseResult) -> dict[str, Any] | None:
    """The order the AI ended up with: the drafted order if it completed one, else what it had collected so far."""
    for t in result.turns:
        if t.order_ready:
            return {k: t.order_ready.get(v) for k, v in _READY_KEYS.items()}
    last = result.last
    if last and last.pending_order:
        return {k: last.pending_order.get(v) for k, v in _PENDING_KEYS.items()}
    return None


# ----------------------------------------------------------------------------- per-case checks


def _suggestion_ok(label: dict, result: CaseResult, fixture: Fixture) -> tuple[bool, str]:
    last = result.last
    shown = [s for t in result.turns for s in t.suggested] if last else []
    names = [str(s["name"]).casefold() for s in shown]
    problems: list[str] = []
    for want in label.get("must_include", []):
        if want.casefold() not in names:
            problems.append(f"missing {want!r}")
    for bad in label.get("must_not_include", []):
        if bad.casefold() in names:
            problems.append(f"suggested {bad!r}")
    if "max_price" in label:
        over = [s["name"] for s in shown if s.get("price") is not None and Decimal(str(s["price"])) > Decimal(str(label["max_price"]))]
        if over:
            problems.append(f"over budget: {over}")
    if label.get("expect_none") and shown:
        problems.append(f"expected no suggestion, got {[s['name'] for s in shown]}")
    return not problems, "; ".join(problems)


def checks_for_case(result: CaseResult, fixture: Fixture) -> list[Check]:
    case, labels = result.case, result.case.labels
    lang = case.language

    def check(metric: str, ok: bool, expected: Any = None, actual: Any = None, detail: str = "") -> Check:
        return Check(metric, case.id, lang, ok, expected, actual, detail)

    if result.error:  # the engine crashed: every labelled item fails
        out: list[Check] = []
        if "intent" in labels:
            out.append(check("intent_accuracy", False, labels["intent"], None, result.error))
        if "answer" in labels:
            a = labels["answer"]
            n = len(a.get("prices", [])) + len(a.get("stock_counts", [])) + (1 if "available" in a else 0)
            out += [check("price_stock_accuracy", False, "value", None, result.error) for _ in range(max(n, 1))]
        if "order" in labels:
            fields = labels["order"].get("fields", {})
            out += [check("order_field_accuracy", False, v, None, result.error) for v in fields.values()]
            if labels["order"].get("phone_invalid"):
                out.append(check("phone_reask", False, "asked again", None, result.error))
        if "handover" in labels:
            out.append(check("flag_recall" if labels["handover"]["flag"] else "flag_precision", False, labels["handover"]["flag"], None, result.error))
        return out

    last = result.last
    assert last is not None
    checks: list[Check] = []
    checks.append(check("language_match", result.turns[0].language_style == lang, lang, result.turns[0].language_style))

    if "intent" in labels:
        checks.append(check("intent_accuracy", last.intent == labels["intent"], labels["intent"], last.intent))

    if "answer" in labels:
        a, reply = labels["answer"], last.reply
        found = set(numbers_in(reply))
        for kind in ("prices", "stock_counts"):
            for value in a.get(kind, []):
                checks.append(check("price_stock_accuracy", _dec(value) in found, f"{value}", sorted(map(str, found)) or "no number", f"expected {kind[:-1].replace('_', ' ')} {value} in the reply"))
        if "available" in a:
            claim = availability_claim(reply)
            want = "available" if a["available"] else "unavailable"
            checks.append(check("price_stock_accuracy", claim == want, want, claim or "no claim", "availability stated in the reply"))
        allowed = fixture_numbers(fixture) | {n for m in case.messages for n in numbers_in(m)} | {_dec(v) for k in ("prices", "stock_counts") for v in a.get(k, [])}
        for n in sorted(found - allowed):
            checks.append(check("price_stock_accuracy", False, "a number from the catalogue", str(n), "the reply states a number that is not in the catalogue or policy"))

    if "order" in labels:
        o, actual = labels["order"], final_order_fields(result)
        for fname, want in o.get("fields", {}).items():
            got = None if actual is None else actual.get(fname)
            checks.append(check("order_field_accuracy", order_field_matches(fname, want, got), want, got, fname))
        ready = any(t.order_ready for t in result.turns)
        if "ready" in o:
            checks.append(check("order_completion", ready == o["ready"], o["ready"], ready))
        if o.get("phone_invalid"):
            asked = (not ready) and any("phone" in t.order_missing for t in result.turns) and not any(t.flagged for t in result.turns)
            checks.append(check("phone_reask", asked, "not drafted, phone asked again", f"drafted={ready}, asked={asked}", "an invalid phone number must be asked for again"))

    # zero-stock suggestions are checked in EVERY case, whatever its type (AI-R06)
    stock = {p.id: p.stock_count for p in fixture.products}
    for t in result.turns:
        for s in t.suggested:
            count = stock.get(s["id"])
            checks.append(check("zero_stock_suggestions", count is not None and count > 0, "in stock", f"{s['name']} (stock {count})", "a product with no stock was suggested"))

    if "suggestion" in labels:
        ok, why = _suggestion_ok(labels["suggestion"], result, fixture)
        checks.append(check("suggestion_quality", ok, labels["suggestion"], [s["name"] for t in result.turns for s in t.suggested], why))

    if "handover" in labels:
        want = labels["handover"]["flag"]
        flagged = any(t.flagged for t in result.turns)
        # precision counts the chats the AI flagged, recall the chats that needed a person
        if flagged:
            checks.append(check("flag_precision", want, "needed a person" if want else "should not be flagged", next(t.flag_reason for t in result.turns if t.flagged)))
        if want:
            checks.append(check("flag_recall", flagged, "flagged", "flagged" if flagged else "not flagged"))
        reason = labels["handover"].get("reason")
        if want and reason:
            got = next((t.flag_reason for t in result.turns if t.flagged), None)
            checks.append(check("flag_reason_accuracy", got == reason, reason, got))
    return checks


# ----------------------------------------------------------------------------- aggregation


def summarize(checks: list[Check]) -> dict[str, dict[str, Any]]:
    """{metric: {"overall": stat, "bangla": stat, ...}}. A stat is {n, passed, value, target, ok}.
    ok: True/False against the target, None when there is no data or no target."""
    out: dict[str, dict[str, Any]] = {}
    for key, meta in METRICS.items():
        groups: dict[str, dict[str, Any]] = {}
        for group in ("overall", *LANGUAGES):
            rows = [c for c in checks if c.metric == key and (group == "overall" or c.language == group)]
            n, passed = len(rows), sum(1 for c in rows if c.ok)
            if meta["kind"] == "zero":
                violations = n - passed
                ok = None if n == 0 else violations == 0
                groups[group] = {"n": n, "passed": passed, "value": violations, "target": 0, "ok": ok, "unit": "violations"}
                continue
            value = passed / n if n else None
            if meta["target"] is None or value is None:
                ok = None
            else:
                ok = value + 1e-12 >= meta["target"]
            groups[group] = {"n": n, "passed": passed, "value": value, "target": meta["target"], "ok": ok, "unit": "share"}
        out[key] = groups
    return out


@dataclass
class Evaluation:
    checks: list[Check] = field(default_factory=list)
    metrics: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    @property
    def targets_failed(self) -> list[str]:
        return [k for k, g in self.metrics.items() if METRICS[k]["kind"] != "info" and g["overall"]["ok"] is False]


def evaluate(results: list[CaseResult], fixture: Fixture) -> Evaluation:
    checks: list[Check] = []
    for r in results:
        checks += checks_for_case(r, fixture)
    return Evaluation(checks=checks, metrics=summarize(checks))


def flag_stats(checks: list[Check]) -> dict[str, int]:
    """Counts behind flag precision/recall: tp, fp, fn over the labelled handover cases."""
    flagged = [c for c in checks if c.metric == "flag_precision"]
    needed = [c for c in checks if c.metric == "flag_recall"]
    tp = sum(1 for c in flagged if c.ok)
    return {"flagged": len(flagged), "true_flags": tp, "false_flags": len(flagged) - tp, "needed_a_person": len(needed), "missed": sum(1 for c in needed if not c.ok)}
