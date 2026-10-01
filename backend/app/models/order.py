from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Order(Base):
    """An order the AI collected from a chat. The AI only ever creates drafts: the seller confirms (Prompt 16).

    Rows created from the Test chat window have is_test = true; reports and exports must exclude them.
    """

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'confirmed', 'cancelled')", name="ck_orders_status"),
        CheckConstraint("quantity > 0", name="ck_orders_quantity_positive"),
        Index("ix_orders_shop_status_created", "shop_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    chat_id: Mapped[int | None] = mapped_column(ForeignKey("chats.id", ondelete="SET NULL"), index=True, nullable=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_name: Mapped[str] = mapped_column(String(200))  # snapshot
    size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    colour: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # catalogue price at draft time (BDT)
    customer_name: Mapped[str] = mapped_column(String(200))
    customer_phone: Mapped[str] = mapped_column(String(20))  # normalised 11-digit mobile number
    customer_address: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft")
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
