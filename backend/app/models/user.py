from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.shop import Shop


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'moderator', 'platform_admin')", name="ck_users_role"),
        # shop_id may be NULL only for platform_admin
        CheckConstraint(
            "(role = 'platform_admin') = (shop_id IS NULL)", name="ck_users_shop_id_by_role"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    shop_id: Mapped[int | None] = mapped_column(
        ForeignKey("shops.id", ondelete="CASCADE"), index=True, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    shop: Mapped[Shop | None] = relationship()
