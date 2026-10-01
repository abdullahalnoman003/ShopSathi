"""Fixed customer-facing phrases in the three message styles (texts live in prompts/phrases.json)."""

from shopsathi_ai.language import LanguageStyle
from shopsathi_ai.prompts import phrases, render


def phrase(name: str, style: LanguageStyle, **values: str) -> str:
    return render(phrases()[name][style], **values)


def is_greeting(text: str) -> bool:
    """A short message made only of greeting / thanks words (no question about the shop)."""
    import re

    words = re.findall(r"[\wঀ-৿]+", text.lower())
    if not words or len(words) > 5:
        return False
    greeting = set(phrases()["greeting_words"])
    return all(w in greeting for w in words)
