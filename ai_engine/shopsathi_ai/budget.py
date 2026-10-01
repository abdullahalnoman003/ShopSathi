"""Reading a budget ("1500 er moddhe", "under 2000", "১৫০০ টাকার মধ্যে", "1.5k") out of a customer message."""

import re
from decimal import Decimal, InvalidOperation

from shopsathi_ai.language import normalise_digits

_NUMBER = re.compile(r"(\d+(?:\.\d+)?)\s*(k\b|hajar\b|হাজার)?", re.IGNORECASE)
_BEFORE = re.compile(r"(under|below|within|upto|up to|max|maximum|budget|less than|not more than|বাজেট|\btk\b|taka|bdt|৳)\s*(of|is|:)?\s*$", re.IGNORECASE)
_AFTER = re.compile(
    r"^\s*(tk\b|taka|bdt|৳|টাকা|er\s+moddhe|er\s+modhye|moddhe|modhye|er\s+niche|niche|nichay|এর\s+মধ্যে|এর\s+মধ্যে|মধ্যে|নিচে|কম|or less|or below|and below|e\s+hobe|er moddhe)",
    re.IGNORECASE,
)


def parse_budget(message: str) -> Decimal | None:
    """The maximum price the customer wrote, e.g. "1500 er moddhe", "under 2000", "১৫০০ টাকার মধ্যে", "1.5k".

    A number only counts as a budget when it is next to a budget word or a currency word, so sizes and
    quantities ("38", "2 ta") are not mistaken for one.
    """
    text = normalise_digits(message).replace(",", "")
    for m in _NUMBER.finditer(text):
        before = text[max(0, m.start() - 20) : m.start()]
        after = text[m.end() : m.end() + 25]
        if not (_BEFORE.search(before) or _AFTER.match(after)):
            continue
        try:
            value = Decimal(m.group(1))
        except InvalidOperation:
            continue
        if m.group(2):
            value *= 1000
        return value if value > 0 else None
    return None


def resolve_budget(message: str, llm_budget: Decimal | None) -> Decimal | None:
    """Prefer the code's reading of the message. Accept the model's number only if the customer wrote it."""
    parsed = parse_budget(message)
    if parsed is not None:
        return parsed
    if llm_budget is None:
        return None
    numbers = {Decimal(n) for n in re.findall(r"\d+(?:\.\d+)?", normalise_digits(message).replace(",", ""))}
    return llm_budget if llm_budget in numbers else None


