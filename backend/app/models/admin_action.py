from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AdminAction(Base):
    """A change the platform admin made (suspend, reactivate, plan change, plan limits). Not shop-owned data: the
    shop and the admin are kept as plain references so the history survives if either is deleted."""

    __tablename__ = "admin_actions"
    __table_args__ = (Index("ix_admin_actions_created", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(30))  # suspend | reactivate | change_plan | update_plan
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
