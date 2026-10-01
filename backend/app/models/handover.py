from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

FLAG_REASONS = (
    "complaint",
    "refund",
    "abusive_language",
    "low_confidence",
    "off_topic",
    "not_in_shop_data",
    "human_requested",
)
_REASONS_SQL = ", ".join(f"'{r}'" for r in FLAG_REASONS)


class HandoverEvent(Base):
    """One row each time the AI handed a chat to a human. Reports (Prompt 17) count "chats handed to humans" here."""

    __tablename__ = "handover_events"
    __table_args__ = (
        CheckConstraint(f"reason IN ({_REASONS_SQL})", name="ck_handover_events_reason"),
        Index("ix_handover_events_shop_created", "shop_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    """An in-dashboard notification for the shop's staff. Only Messenger chats create them: flags in the Test
    chat window are shown in that window only."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("type IN ('chat_flagged')", name="ck_notifications_type"),
        Index("ix_notifications_shop_read_created", "shop_id", "read_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(30), default="chat_flagged")
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
