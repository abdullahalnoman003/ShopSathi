"""Order drafting rules (AI-4, AI-R07 to AI-R09, AI-R11).

``process_order`` checks what the model extracted against the shop's own data and merges it into the pending
order of the chat. ``compose_order_reply`` writes the customer-facing text from fixed phrases, so the AI can
never say an order is confirmed, mention a discount, or quote anything but the catalogue price.
The order is only ever a *draft*: the seller gives final approval.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from shopsathi_ai.chunking import format_money
from shopsathi_ai.extraction import ORDER_FIELDS, OrderExtraction
from shopsathi_ai.interfaces import ProductInfo
from shopsathi_ai.language import LanguageStyle, normalise_digits
from shopsathi_ai.prompts import phrases, render
from shopsathi_ai.tools import ShopTools
from shopsathi_ai.validators import normalize_and_validate_bd_phone

#: keys of the pending order stored for a chat
STATE_KEYS = ("product_id", "product_name", "size", "colour", "quantity", "name", "phone", "address")
MIN_ADDRESS_CHARS = 5
MAX_QUANTITY = 1000

_WORDS = re.compile(r"[\wঀ-৿]+")


@dataclass
class OrderCheck:
    #: validated order fields to keep for the next turn (see STATE_KEYS)
    state: dict[str, Any]
    #: fields still needed, in asking order (ORDER_FIELDS names)
    ask: list[str]
    #: specific problems to tell the customer about
    issues: dict[str, Any] = field(default_factory=dict)
    ready: bool = False
    #: something new or something wrong was said in this message
    progressed: bool = False
    product: ProductInfo | None = None


def core(state: dict | None) -> dict[str, Any]:
    state = state or {}
    return {k: state.get(k) for k in STATE_KEYS}


# ---------------------------------------------------------------- grounding


def _tokens(text: str) -> list[str]:
    return _WORDS.findall(normalise_digits(text).casefold())


def grounded_text(value: str, customer_text: str, ratio: float = 0.8) -> bool:
    """A name or address must really come from the customer's own messages (the model may not invent it)."""
    wanted = [t for t in _tokens(value) if len(t) > 1 or t.isdigit()]
    if not wanted:
        return False
    have = set(_tokens(customer_text))
    return sum(1 for t in wanted if t in have) / len(wanted) >= ratio


def grounded_phone(value: str, customer_text: str) -> bool:
    """The customer really wrote this phone value (digits, or at least the same text)."""
    digits = re.sub(r"\D", "", normalise_digits(value))
    if digits:
        return digits in re.sub(r"\D", "", normalise_digits(customer_text))
    return value.strip().casefold() in customer_text.casefold()


# ------------------------------------------------------------------ product


def _same_product(query: str, name: str) -> bool:
    q, n = set(_tokens(query)), set(_tokens(name))
    return bool(q) and bool(n) and (q <= n or n <= q)


def resolve_product(tools: ShopTools, query: str, min_name_match: float = 0.5) -> tuple[str, list[ProductInfo]]:
    """("ok", [product]) | ("ambiguous", [in-stock products]) | ("unknown", [])  -- products of THIS shop only."""
    hits = [p for p in tools.search_products(query, None, 8) if p.match == "name" and p.score >= min_name_match]
    if not hits:
        return "unknown", []
    exact = [p for p in hits if p.name.casefold() == query.casefold()]
    if len(exact) == 1:
        return "ok", exact
    best = max(p.score for p in hits)
    top = [p for p in hits if p.score == best]
    if len(top) == 1:
        return "ok", top
    in_stock = [p for p in top if p.stock_count > 0]
    if len(in_stock) == 1:
        return "ok", in_stock
    return ("ambiguous", in_stock) if in_stock else ("ok", top[:1])


def _match_option(value: str | None, options: list[str]) -> str | None:
    if not value:
        return None
    for o in options:
        if o.casefold() == value.strip().casefold():
            return o
    return None


# ------------------------------------------------------------------- process


def process_order(
    tools: ShopTools,
    extraction: OrderExtraction,
    pending: dict | None,
    customer_text: str,
    product_hint: str | None = None,
    min_name_match: float = 0.5,
) -> OrderCheck:
    """Merge the extraction into the pending order, validating every field against the shop's data."""
    before = core(pending)
    state = dict(before)
    issues: dict[str, Any] = {}

    # --- product (must resolve to a product of this shop)
    query = extraction.product_en or extraction.product
    if query and state["product_name"] and _same_product(query, state["product_name"]):
        query = None  # still the same product
    if not query and not state["product_id"] and product_hint:
        query = product_hint
    if query:
        kind, found = resolve_product(tools, query, min_name_match)
        if kind == "ok":
            if state["product_id"] != found[0].id:  # a different product: its sizes/colours differ
                state.update(product_id=found[0].id, product_name=found[0].name)
                if before["product_id"] is not None:
                    state.update(size=None, colour=None)
        elif kind == "ambiguous":
            issues["choose_product"] = [p.name for p in found]
        else:
            issues["unknown_product"] = query

    product: ProductInfo | None = None
    if state["product_id"] is not None:
        live = tools.get_products([state["product_id"]])
        product = live[0] if live else None
        if product is None:
            state.update(product_id=None, product_name=None, size=None, colour=None)
        elif product.stock_count <= 0:  # the catalogue says it is gone: do not draft this item
            issues["out_of_stock"] = product.name
            state.update(product_id=None, product_name=None, size=None, colour=None, quantity=None)
            product = None
        else:
            state["product_name"] = product.name

    # --- size and colour: must be one of the product's listed options (not needed if it has none)
    for key, options_of in (("size", lambda p: p.sizes), ("colour", lambda p: p.colours)):
        given = getattr(extraction, key) or state[key]
        if product is None:
            state[key] = given  # checked once the product is known
            continue
        options = options_of(product)
        if not options:
            state[key] = None
        elif given is None:
            state[key] = None
        else:
            matched = _match_option(given, options)
            if matched:
                state[key] = matched
            else:
                state[key] = None
                issues[f"{key}_invalid"] = {"value": given, "options": options}

    # --- quantity: positive whole number, within the catalogue stock
    qty = extraction.quantity if extraction.quantity is not None else state["quantity"]
    if qty is not None and not (1 <= int(qty) <= MAX_QUANTITY):
        if extraction.quantity is not None:
            issues["quantity_invalid"] = extraction.quantity  # asked for again, with the generic question
        qty = None
    if qty is not None and product is not None and qty > product.stock_count:
        issues["qty_too_many"] = {"stock": product.stock_count, "product": product.name}
        qty = None
    state["quantity"] = qty

    # --- name, phone, address: only what the customer really wrote
    if extraction.name and len(extraction.name) >= 2 and grounded_text(extraction.name, customer_text):
        state["name"] = extraction.name
    if extraction.address and len(extraction.address) >= MIN_ADDRESS_CHARS and grounded_text(extraction.address, customer_text):
        state["address"] = extraction.address
    if extraction.phone and grounded_phone(extraction.phone, customer_text):
        valid = normalize_and_validate_bd_phone(extraction.phone)
        if valid:
            state["phone"] = valid
        else:
            state["phone"] = None
            issues["phone_invalid"] = True  # AI-R08: ask again

    # --- what is still missing (AI-R09)
    ask: list[str] = []
    for name in ORDER_FIELDS:
        if name == "product":
            missing = state["product_id"] is None
        elif name in ("size", "colour"):
            missing = bool(product) and bool(getattr(product, "sizes" if name == "size" else "colours")) and state[name] is None
        elif name == "quantity":
            missing = state["quantity"] is None
        else:
            missing = not state[name]
        if missing:
            ask.append(name)

    ready = not ask and not issues
    progressed = core(state) != before or bool(issues)
    return OrderCheck(state=core(state), ask=ask, issues=issues, ready=ready, progressed=progressed, product=product)


def order_ready_fields(check: OrderCheck) -> dict[str, Any]:
    """The complete, validated order for the seller to confirm (catalogue price at draft time)."""
    s, p = check.state, check.product
    assert check.ready and p is not None
    return {
        "product_id": s["product_id"],
        "product_name": s["product_name"],
        "size": s["size"],
        "colour": s["colour"],
        "quantity": s["quantity"],
        "unit_price": float(p.price),
        "customer_name": s["name"],
        "customer_phone": s["phone"],
        "customer_address": s["address"],
    }


# ------------------------------------------------------------------- replies


def _ph(name: str, style: LanguageStyle, **values: str) -> str:
    return render(phrases()[name][style], **values)


def order_summary(check: OrderCheck, style: LanguageStyle) -> str:
    labels = phrases()["order_summary_labels"][style]
    s, p = check.state, check.product
    rows = [(labels["product"], s["product_name"])]
    if s["size"]:
        rows.append((labels["size"], s["size"]))
    if s["colour"]:
        rows.append((labels["colour"], s["colour"]))
    rows.append((labels["quantity"], str(s["quantity"])))
    if p is not None:
        rows.append((labels["price"], render(labels["price_value"], price=format_money(p.price))))
    rows += [(labels["name"], s["name"]), (labels["phone"], s["phone"]), (labels["address"], s["address"])]
    return "\n".join(f"{k}: {v}" for k, v in rows)


def compose_order_reply(check: OrderCheck, style: LanguageStyle) -> str:
    """Text for the customer, from fixed phrases only."""
    if check.ready:
        return _ph("order_ready", style, summary=order_summary(check, style))

    issues, parts, handled = check.issues, [], set()
    names = phrases()["order_option_names"][style]
    if "out_of_stock" in issues:
        parts.append(_ph("order_out_of_stock", style, product=issues["out_of_stock"]))
        return " ".join(parts)  # nothing more to collect for an item we cannot draft
    if "choose_product" in issues:
        parts.append(_ph("order_choose_product", style, names=", ".join(issues["choose_product"])))
        handled.add("product")
    if "phone_invalid" in issues:
        parts.append(_ph("order_phone_invalid", style))
        handled.add("phone")
    for key in ("size", "colour"):
        bad = issues.get(f"{key}_invalid")
        if bad:
            name = (check.state.get("product_name") or "")
            parts.append(_ph("order_option_invalid", style, what=names[key], value=bad["value"], product=name, options=", ".join(bad["options"])))
            handled.add(key)
    if "qty_too_many" in issues:
        parts.append(_ph("order_qty_too_many", style, stock=str(issues["qty_too_many"]["stock"]), product=issues["qty_too_many"]["product"]))
        handled.add("quantity")

    remaining = [f for f in check.ask if f not in handled]
    if remaining:
        prompts = phrases()["order_field_prompts"][style]
        product = check.product
        items = []
        for f in remaining:
            text = prompts[f]
            if product is not None and f == "size" and product.sizes:
                text += f" ({', '.join(product.sizes)})"
            if product is not None and f == "colour" and product.colours:
                text += f" ({', '.join(product.colours)})"
            items.append(text)
        parts.append(_ph("order_ask", style, items=", ".join(items)))
    return " ".join(parts)
