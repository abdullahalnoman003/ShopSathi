from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_MESSAGE_CHARS = 1000


class SessionOut(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime
    message_count: int
    last_message: str | None  # preview of the latest message
    is_flagged: bool = False  # the AI handed this conversation to the shop
    flag_reason: str | None = None
    ai_paused: bool = False


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message must not be empty")
        return v


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sender: str
    text: str
    intent: str | None
    confidence: float | None
    language_style: str | None
    extras: dict[str, Any]
    created_at: datetime


class HandoverOut(BaseModel):
    needed: bool
    reason: str | None


class ChatStateOut(BaseModel):
    is_flagged: bool
    flag_reason: str | None
    ai_paused: bool


class SendMessageResponse(BaseModel):
    customer_message: MessageOut
    #: None while the AI is paused for this conversation (a flagged chat): no reply is written
    ai_message: MessageOut | None
    handover: HandoverOut
    chat: ChatStateOut
