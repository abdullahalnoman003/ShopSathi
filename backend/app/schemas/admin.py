from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer


class AdminPlanRef(BaseModel):
    code: str
    name: str


class AdminShop(BaseModel):
    id: int
    name: str
    owner_email: str | None
    owner_name: str | None
    plan: AdminPlanRef
    status: str  # active | suspended
    created_at: datetime
    connected_page_name: str | None
    ai_messages_used: int  # this month (Asia/Dhaka)
    ai_messages_limit: int
    usage_period: str


class AdminShopDetail(AdminShop):
    product_count: int
    chat_count: int  # Messenger chats (the test chat window is not counted)
    order_count: int  # orders, not counting test orders


class AdminShopPage(BaseModel):
    items: list[AdminShop]
    total: int
    page: int
    page_size: int


class PlanChange(BaseModel):
    plan_code: str


class AdminPlan(BaseModel):
    code: str
    name: str
    monthly_message_limit: int
    monthly_price: int  # display only (BDT)


class PlanUpdate(BaseModel):
    monthly_message_limit: int = Field(ge=1, le=100_000_000)
    monthly_price: int = Field(ge=0, le=10_000_000)


class OperationUsage(BaseModel):
    calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal

    @field_serializer("estimated_cost")
    def _cost(self, v: Decimal) -> float:
        return float(v)


class ShopAiUsage(BaseModel):
    shop_id: int
    shop_name: str
    calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal  # USD
    by_operation: dict[str, OperationUsage]

    @field_serializer("estimated_cost")
    def _cost(self, v: Decimal) -> float:
        return float(v)


class AiUsageReport(BaseModel):
    from_date: date
    to_date: date
    shops: list[ShopAiUsage]  # shops with usage in the range, most expensive first
    total: OperationUsage
    by_operation: dict[str, OperationUsage]


class ComponentHealth(BaseModel):
    status: str  # ok | error
    detail: str | None = None


class SystemHealth(BaseModel):
    status: str  # ok | degraded
    api: ComponentHealth
    database: ComponentHealth
    redis: ComponentHealth
    celery_worker: ComponentHealth
    celery_queue_length: int | None
