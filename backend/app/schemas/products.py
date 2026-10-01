from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer, field_validator

MAX_OPTIONS = 20


def _clean_options(values: list[str], label: str) -> list[str]:
    """Trim; reject blanks, too-long values and case-insensitive duplicates."""
    if len(values) > MAX_OPTIONS:
        raise ValueError(f"At most {MAX_OPTIONS} {label}s are allowed")
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        v = raw.strip()
        if not v:
            raise ValueError(f"A {label} must not be blank")
        if len(v) > 50:
            raise ValueError(f"A {label} must be at most 50 characters")
        if v.lower() in seen:
            raise ValueError(f"Duplicate {label}: {v}")
        seen.add(v.lower())
        out.append(v)
    return out


class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)  # BDT
    sizes: list[str] = Field(default_factory=list)
    colours: list[str] = Field(default_factory=list)
    stock_count: int = Field(default=0, ge=0, le=10_000_000)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v

    @field_validator("description")
    @classmethod
    def _description(cls, v: str) -> str:
        return v.strip()

    @field_validator("sizes")
    @classmethod
    def _sizes(cls, v: list[str]) -> list[str]:
        return _clean_options(v, "size")

    @field_validator("colours")
    @classmethod
    def _colours(cls, v: list[str]) -> list[str]:
        return _clean_options(v, "colour")


class ProductOut(BaseModel):
    id: int
    name: str
    description: str
    price: Decimal
    sizes: list[str]
    colours: list[str]
    stock_count: int
    photos: list[str]  # full URLs, in order
    created_at: datetime
    updated_at: datetime

    @field_serializer("price")
    def _price(self, v: Decimal) -> float:
        return float(v)


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int
