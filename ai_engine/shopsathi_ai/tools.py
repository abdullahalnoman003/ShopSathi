"""The AI agent's tools: search products, check stock, get delivery charge.

They are thin, shop-scoped wrappers over the ShopDataGateway and record what was called, so the result can
say which data a reply was based on. The engine calls them from the understood intent and entities, which
keeps every answer grounded in the shop's data. (Update order draft arrives in Prompt 11.)
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Sequence

from shopsathi_ai.interfaces import DeliveryChargeInfo, ProductInfo, ShopDataGateway, StockInfo

TOOL_DESCRIPTIONS = {
    "search_products": "Find the shop's products matching the customer's words.",
    "check_stock": "Check stock and whether a size/colour is offered for one product.",
    "get_delivery_charge": "Look up the delivery charge for an area in the shop policy.",
    "get_products": "Read the current price, stock and photos of specific products.",
    "browse_products": "List in-stock products, optionally within a budget.",
    "update_order_draft": "Merge validated order fields into the chat's pending order.",
}


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    result: str  # short human-readable summary


@dataclass
class ShopTools:
    gateway: ShopDataGateway
    shop_id: int
    calls: list[ToolCall] = field(default_factory=list)

    def search_products(self, query_text: str, query_vector: list[float] | None, top_k: int = 3) -> list[ProductInfo]:
        found = self.gateway.search_products(self.shop_id, query_text, query_vector, top_k)
        self.calls.append(ToolCall("search_products", {"query": query_text}, f"{len(found)} product(s)"))
        return found

    def check_stock(self, product_id: int, size: str | None = None, colour: str | None = None) -> StockInfo | None:
        info = self.gateway.check_stock(self.shop_id, product_id, size, colour)
        summary = "not found" if info is None else f"stock {info.stock_count}"
        self.calls.append(ToolCall("check_stock", {"product_id": product_id, "size": size, "colour": colour}, summary))
        return info

    def get_delivery_charge(self, area_text: str) -> DeliveryChargeInfo:
        info = self.gateway.get_delivery_charge(self.shop_id, area_text)
        self.calls.append(ToolCall("get_delivery_charge", {"area": area_text}, "found" if info.found else "not found"))
        return info

    def get_products(self, product_ids: Sequence[int]) -> list[ProductInfo]:
        found = self.gateway.get_products(self.shop_id, list(product_ids))
        self.calls.append(ToolCall("get_products", {"ids": list(product_ids)}, f"{len(found)} product(s)"))
        return found

    def browse_products(self, max_price: Decimal | None, limit: int) -> list[ProductInfo]:
        found = self.gateway.browse_products(self.shop_id, max_price, limit)
        self.calls.append(
            ToolCall("browse_products", {"max_price": None if max_price is None else str(max_price)}, f"{len(found)} product(s)")
        )
        return found

    def update_order_draft(self, pending: dict | None, fields: dict[str, Any]) -> dict[str, Any]:
        """Merge the validated order fields into the chat's pending order and return the new pending state.

        The engine returns it to the backend, which stores it in ``chats.pending_order``.
        """
        merged = {**(pending or {}), **fields}
        changed = sorted(k for k, v in fields.items() if (pending or {}).get(k) != v)
        self.calls.append(ToolCall("update_order_draft", {"fields": changed}, f"{len(changed)} field(s) updated"))
        return merged
