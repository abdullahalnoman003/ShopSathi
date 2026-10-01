from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from app.services.policy_text import normalise_area

MAX_TEXT = 2000
MAX_AREAS = 100


class DeliveryAreaIn(BaseModel):
    area_name: str = Field(min_length=1, max_length=100)
    charge: Decimal = Field(ge=0, max_digits=10, decimal_places=2)  # BDT

    @field_validator("area_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Area name is required")
        return v


class PolicyIn(BaseModel):
    delivery_time: str = Field(default="", max_length=MAX_TEXT)
    return_rules: str = Field(default="", max_length=MAX_TEXT)
    payment_options: str = Field(default="", max_length=MAX_TEXT)
    delivery_areas: list[DeliveryAreaIn] = Field(default_factory=list, max_length=MAX_AREAS)

    @field_validator("delivery_time", "return_rules", "payment_options")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def _unique_areas(self) -> "PolicyIn":
        seen: set[str] = set()
        for area in self.delivery_areas:
            key = normalise_area(area.area_name)
            if key in seen:
                raise ValueError(f"Duplicate area: {area.area_name}")
            seen.add(key)
        return self


class DeliveryAreaOut(BaseModel):
    area_name: str
    charge: Decimal

    @field_serializer("charge")
    def _charge(self, v: Decimal) -> float:
        return float(v)


class PolicyOut(BaseModel):
    delivery_time: str
    return_rules: str
    payment_options: str
    delivery_areas: list[DeliveryAreaOut]
    updated_at: datetime | None  # None until the seller saves a policy for the first time
