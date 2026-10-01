from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

OrderStatus = Literal["draft", "confirmed", "cancelled"]


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    chat_id: int | None  # the source chat (the inbox route /dashboard/inbox/{chat_id})
    product_id: int | None
    product_name: str
    size: str | None
    colour: str | None
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    customer_name: str
    customer_phone: str
    customer_address: str
    status: OrderStatus
    created_at: datetime
    confirmed_at: datetime | None
    cancelled_at: datetime | None
    #: the product's current options, so the edit form can offer them (None if the product was deleted)
    product_sizes: list[str] | None = None
    product_colours: list[str] | None = None

    @field_serializer("unit_price", "total_price")
    def _money(self, v: Decimal) -> float:
        return float(v)


class OrderPage(BaseModel):
    items: list[OrderOut]
    total: int
    page: int
    page_size: int
    counts: dict[str, int]  # orders per status (drafts, confirmed, cancelled) for the tabs


class OrderPatch(BaseModel):
    """Only the listed fields can change. The price cannot: it always comes from the catalogue."""

    model_config = ConfigDict(extra="forbid")
    product_id: int | None = None
    size: str | None = None
    colour: str | None = None
    quantity: int | None = Field(default=None, ge=1)
    customer_name: str | None = Field(default=None, max_length=200)
    customer_phone: str | None = Field(default=None, max_length=40)
    customer_address: str | None = Field(default=None, max_length=1000)

    @field_validator("customer_name", "customer_phone", "customer_address", "size", "colour")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


class ProductOption(BaseModel):
    id: int
    name: str
    price: Decimal
    sizes: list[str]
    colours: list[str]
    stock_count: int

    @field_serializer("price")
    def _money(self, v: Decimal) -> float:
        return float(v)
