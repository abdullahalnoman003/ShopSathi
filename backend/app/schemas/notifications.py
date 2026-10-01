from datetime import datetime

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: int
    type: str
    chat_id: int
    reason: str
    customer_name: str | None  # the customer of the flagged chat, if known
    created_at: datetime
    read_at: datetime | None


class NotificationList(BaseModel):
    unread_count: int
    items: list[NotificationOut]


class MarkedRead(BaseModel):
    marked: int
