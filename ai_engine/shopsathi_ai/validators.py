"""Pure validators shared by the AI engine and the backend (Prompt 16 reuses the phone check)."""

import re

from shopsathi_ai.language import normalise_digits

_BD_MOBILE = re.compile(r"^01[3-9]\d{8}$")
_SEPARATORS = re.compile(r"[\s\-().]")


def normalize_and_validate_bd_phone(text: str | None) -> str | None:
    """Return the customer's number as 11 digits (``01XXXXXXXXX``), or ``None`` if it is not a valid
    Bangladeshi mobile number.

    Accepts Bangla digits (০১৭১২৩৪৫৬৭৮), spaces, dashes and dots, and a leading ``+88`` / ``88`` country code.
    Anything else (letters, a different length, a prefix outside 013-019) is invalid.
    """
    if not text:
        return None
    value = _SEPARATORS.sub("", normalise_digits(text.strip()))
    if value.startswith("+88"):
        value = value[3:]
    elif value.startswith("88") and len(value) == 13:
        value = value[2:]
    return value if _BD_MOBILE.fullmatch(value) else None


def is_valid_bd_phone(text: str | None) -> bool:
    return normalize_and_validate_bd_phone(text) is not None
