from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Chat(Base):
    """A conversation between a customer and the shop's AI. channel 'test' = the seller's Test chat window.

    Inbox, reports and exports (later prompts) must exclude channel 'test'.
    """

    __tablename__ = "chats"
    __table_args__ = (
        CheckConstraint("channel IN ('messenger', 'test')", name="ck_chats_channel"),
        Index("ix_chats_shop_channel_updated", "shop_id", "channel", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(20))
    customer_psid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ai_paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    flag_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: validated order fields collected so far in this chat (cleared when the draft is created)
    pending_order: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ai_disclosure_sent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_customer_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("sender IN ('customer', 'ai', 'seller')", name="ck_messages_sender"),
        UniqueConstraint("shop_id", "external_message_id", name="uq_messages_shop_external_id"),
        Index("ix_messages_shop_chat", "shop_id", "chat_id"),
        Index("ix_messages_chat_id", "chat_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"))
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    sender: Mapped[str] = mapped_column(String(20))
    text: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    language_style: Mapped[str | None] = mapped_column(String(20), nullable=True)
    extras: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    external_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
