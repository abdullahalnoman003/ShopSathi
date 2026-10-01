from pydantic import BaseModel, ConfigDict


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    monthly_message_limit: int
    monthly_price: int  # display only (BDT)


class UsageOut(BaseModel):
    period: str
    used: int
    limit: int
    remaining: int


class ShopPlanResponse(BaseModel):
    plan: PlanOut
    usage: UsageOut


class PlanChangeRequest(BaseModel):
    plan_code: str
    simulated_payment_confirmed: bool = False
