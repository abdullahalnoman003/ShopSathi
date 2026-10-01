"""Turn a shop's products and policy into small text chunks for embedding (pure functions, no I/O)."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

SourceType = Literal["product", "policy"]

#: long text is split so that one chunk stays small and focused
MAX_CHUNK_CHARS = 600


@dataclass(frozen=True)
class Chunk:
    source_type: SourceType
    #: product id for products; the shop id for the (single) shop policy
    source_id: int
    content: str


@dataclass(frozen=True)
class ProductData:
    id: int
    name: str
    description: str
    price: Decimal | float | int | str
    sizes: list[str] = field(default_factory=list)
    colours: list[str] = field(default_factory=list)
    stock_count: int = 0


@dataclass(frozen=True)
class PolicyData:
    shop_id: int
    delivery_time: str = ""
    return_rules: str = ""
    payment_options: str = ""
    #: (area name, charge in BDT)
    delivery_areas: list[tuple[str, Decimal | float | int | str]] = field(default_factory=list)


def format_money(value: Decimal | float | int | str) -> str:
    """4800.00 -> '4800', 1250.5 -> '1250.5'."""
    d = Decimal(str(value))
    text = format(d.normalize(), "f")
    return text


def split_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split on paragraph then sentence boundaries into pieces of at most ``max_chars`` (long words are cut)."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    current = ""
    # sentences keep their end punctuation (. ! ? and the Bangla danda)
    sentences: list[str] = []
    for para in text.splitlines():
        buf = ""
        for ch in para:
            buf += ch
            if ch in ".!?।":
                sentences.append(buf.strip())
                buf = ""
        if buf.strip():
            sentences.append(buf.strip())
    for sentence in sentences:
        while len(sentence) > max_chars:  # one huge sentence: cut at a space if possible
            cut = sentence.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if not sentence:
            continue
        if current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def product_chunks(p: ProductData) -> list[Chunk]:
    """One chunk with the facts the AI must not get wrong (name, price, sizes, colours, stock),
    plus extra chunks only if the description is long."""
    stock = f"In stock ({p.stock_count} available)" if p.stock_count > 0 else "Out of stock"
    description_parts = split_text(p.description)
    lines = [
        f"Product: {p.name}",
        f"Price: {format_money(p.price)} BDT",
        f"Sizes: {', '.join(p.sizes) if p.sizes else 'not applicable'}",
        f"Colours: {', '.join(p.colours) if p.colours else 'not applicable'}",
        f"Stock: {stock}",
    ]
    if description_parts:
        lines.insert(1, f"Description: {description_parts[0]}")
    chunks = [Chunk("product", p.id, "\n".join(lines))]
    for part in description_parts[1:]:
        chunks.append(Chunk("product", p.id, f"Product: {p.name} (more details)\nDescription: {part}"))
    return chunks


def policy_chunks(p: PolicyData) -> list[Chunk]:
    """Delivery time, return rules and payment options (split if long), plus one chunk per delivery area."""
    chunks: list[Chunk] = []
    for label, text in (
        ("Delivery time", p.delivery_time),
        ("Return rules", p.return_rules),
        ("Payment options", p.payment_options),
    ):
        for i, part in enumerate(split_text(text)):
            suffix = " (continued)" if i else ""
            chunks.append(Chunk("policy", p.shop_id, f"Shop policy - {label}{suffix}: {part}"))
    for area, charge in p.delivery_areas:
        chunks.append(Chunk("policy", p.shop_id, f"Shop policy - Delivery charge for {area}: {format_money(charge)} BDT"))
    return chunks
