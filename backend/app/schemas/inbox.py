from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_REPLY_CHARS = 2000  # Messenger's limit for one text message


class InboxChat(BaseModel):
    id: int
    customer_name: str | None
    customer_label: str  # the name if known, otherwise "Customer ...1234"
    last_message: str | None  # preview
    last_message_sender: str | None  # customer | ai | seller
    is_flagged: bool
    flag_reason: str | None
    flagged_at: datetime | None
    ai_paused: bool
    last_activity_at: datetime
    window_open: bool  # a manual reply can still be sent (Meta's 24-hour window, NFR-09)
    window_closes_at: datetime | None


class InboxPage(BaseModel):
    items: list[InboxChat]
    total: int
    page: int
    page_size: int
    flagged_count: int  # all flagged chats of the shop, whatever the filter


class InboxMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sender: str
    text: str
    intent: str | None
    confidence: float | None
    language_style: str | None
    extras: dict[str, Any]
    created_at: datetime
    sent_at: datetime | None


class InboxChatDetail(InboxChat):
    messages: list[InboxMessage]


class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_REPLY_CHARS)

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Reply must not be empty")
        return v
