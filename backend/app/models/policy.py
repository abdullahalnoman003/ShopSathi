from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ShopPolicy(Base):
    """One policy per shop: delivery time, return rules and payment options (FR-06)."""

    __tablename__ = "shop_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), unique=True)
    delivery_time: Mapped[str] = mapped_column(Text, default="", server_default="")
    return_rules: Mapped[str] = mapped_column(Text, default="", server_default="")
    payment_options: Mapped[str] = mapped_column(Text, default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DeliveryArea(Base):
    """Delivery charge for one area (BDT)."""

    __tablename__ = "delivery_areas"
    __table_args__ = (CheckConstraint("charge >= 0", name="ck_delivery_areas_charge_non_negative"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    area_name: Mapped[str] = mapped_column(String(100))
    charge: Mapped[Decimal] = mapped_column(Numeric(10, 2))


# Area names are unique per shop, ignoring case.
Index("uq_delivery_areas_shop_area", DeliveryArea.shop_id, func.lower(DeliveryArea.area_name), unique=True)
