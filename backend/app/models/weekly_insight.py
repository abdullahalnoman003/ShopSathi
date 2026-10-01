from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WeeklyInsight(Base):
    """The AI summary of one shop's chats for one week (AI-6, AI-R12). One row per shop and week; a week starts on
    Monday (Asia/Dhaka)."""

    __tablename__ = "weekly_insights"
    __table_args__ = (UniqueConstraint("shop_id", "week_start", name="uq_weekly_insights_shop_week"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date)
    #: [{"question": str, "count": int}], at most 5, most asked first
    top_questions: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    #: [{"name": str, "count": int}]: products customers asked for that the shop does not have, most asked first
    missing_products: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
