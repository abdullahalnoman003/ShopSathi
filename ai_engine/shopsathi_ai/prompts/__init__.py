"""Prompt templates and fixed phrases live in this folder as files (not inline strings)."""

import json
import re
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=None)
def load(name: str) -> str:
    """Text of ``prompts/<name>`` (e.g. ``reply_system.md``)."""
    return resources.files(__package__).joinpath(name).read_text(encoding="utf-8")


def render(template: str, **values: str) -> str:
    """Replace ``{{name}}`` markers (plain replace: JSON braces in templates are safe)."""
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(values[m.group(1)]), template)


@lru_cache(maxsize=1)
def phrases() -> dict:
    return json.loads(load("phrases.json"))
