from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Plan(Base):
    """Subscription plan (Free / Basic / Pro). Global, not shop-owned."""

    __tablename__ = "plans"
    __table_args__ = (CheckConstraint("code IN ('free', 'basic', 'pro')", name="ck_plans_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(50))
    monthly_message_limit: Mapped[int] = mapped_column(Integer)
    monthly_price: Mapped[int] = mapped_column(Integer, default=0)  # display only (BDT)


class SimulatedPayment(Base):
    """Records that a simulated payment happened. No card/bKash/Nagad data, no gateway."""

    __tablename__ = "simulated_payments"
    __table_args__ = (
        CheckConstraint("status IN ('simulated_success')", name="ck_simulated_payments_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="simulated_success")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShopMessageUsage(Base):
    """AI replies sent per shop per calendar month (Asia/Dhaka), period like '2026-10'."""

    __tablename__ = "shop_message_usage"
    __table_args__ = (UniqueConstraint("shop_id", "period", name="uq_shop_message_usage_shop_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    period: Mapped[str] = mapped_column(String(7))
    ai_messages_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
