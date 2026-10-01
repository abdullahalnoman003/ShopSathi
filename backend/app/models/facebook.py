from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FacebookPage(Base):
    """The one Facebook Page connected to a shop. The Page access token is stored encrypted (NFR-03)."""

    __tablename__ = "facebook_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), unique=True)  # one Page per shop
    page_id: Mapped[str] = mapped_column(String(64), unique=True)  # a Page cannot be connected to two shops
    page_name: Mapped[str] = mapped_column(String(200))
    encrypted_page_token: Mapped[str] = mapped_column(Text)  # Fernet token, never the plaintext
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
