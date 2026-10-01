import re

_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)


def normalise_area(text: str) -> str:
    """Case-fold, turn punctuation into spaces and collapse whitespace (keeps Bangla letters).

    "Inside  Dhaka", "inside-dhaka" and "INSIDE DHAKA" all become "inside dhaka".
    """
    return _NON_WORD.sub(" ", text.casefold()).strip()
