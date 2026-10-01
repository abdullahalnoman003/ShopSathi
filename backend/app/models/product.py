from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Product(Base):
    """A catalogue item. The AI's source of truth for price, size, colour and stock (Prompt 8 embeds it)."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_products_price_positive"),
        CheckConstraint("stock_count >= 0", name="ck_products_stock_non_negative"),
        CheckConstraint("cardinality(photos) <= 5", name="ck_products_max_photos"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # BDT
    sizes: Mapped[list[str]] = mapped_column(ARRAY(String(50)), default=list, server_default="{}")
    colours: Mapped[list[str]] = mapped_column(ARRAY(String(50)), default=list, server_default="{}")
    stock_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Ordered storage keys like "shops/1/products/<uuid>.jpg" (not URLs; the API turns them into URLs)
    photos: Mapped[list[str]] = mapped_column(ARRAY(String(300)), default=list, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
