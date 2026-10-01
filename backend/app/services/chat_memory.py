"""Short-term chat memory in Redis: the last N turns of a chat, with a TTL.

Only these recent turns (never the whole history) are given to the AI. If the Redis key has expired, the
turns are rebuilt from the database so a returning customer keeps context.
"""

import json

from shopsathi_ai.understanding import Turn
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.redis import get_redis
from app.models import Chat, Message
from app.services.tenant import scoped_select


def _key(shop_id: int, chat_id: int) -> str:
    return f"chatmem:{shop_id}:{chat_id}"


def _to_json(t: Turn) -> str:
    return json.dumps({"role": t.role, "text": t.text, "entities": t.entities}, ensure_ascii=False)


def _from_json(raw: bytes | str) -> Turn:
    d = json.loads(raw)
    return Turn(role=d["role"], text=d["text"], entities=d.get("entities") or {})


class ChatMemoryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        s = get_settings()
        self.limit = s.chat_memory_turns
        self.ttl = s.chat_memory_ttl_seconds
        self.redis = get_redis()

    def load(self, chat: Chat, before_message_id: int | None = None) -> list[Turn]:
        """The last turns of the chat. ``before_message_id`` leaves out the message being answered (it is already
        stored when it came in through a webhook) when the turns have to be rebuilt from the database."""
        key = _key(chat.shop_id, chat.id)
        raw = self.redis.lrange(key, -self.limit, -1)
        if raw:
            return [_from_json(r) for r in raw]
        turns = self._rebuild(chat, before_message_id)
        if turns:  # put them back so the next message does not lose this context
            self.append(chat, turns)
        return turns

    def append(self, chat: Chat, turns: list[Turn]) -> None:
        key = _key(chat.shop_id, chat.id)
        pipe = self.redis.pipeline()
        pipe.rpush(key, *[_to_json(t) for t in turns])
        pipe.ltrim(key, -self.limit, -1)
        pipe.expire(key, self.ttl)
        pipe.execute()

    def clear(self, chat: Chat) -> None:
        self.redis.delete(_key(chat.shop_id, chat.id))

    def _rebuild(self, chat: Chat, before_message_id: int | None = None) -> list[Turn]:
        # Messages up to the one that created an order draft are not context any more: the details in them
        # were used. This also stops the AI from re-reading them and drafting the same order twice.
        boundary = self.db.scalar(
            select(func.max(Message.id)).where(
                Message.shop_id == chat.shop_id, Message.chat_id == chat.id, Message.extras.has_key("order_id")
            )
        )
        query = scoped_select(Message, chat.shop_id).where(Message.chat_id == chat.id)
        if boundary is not None:
            query = query.where(Message.id > boundary)
        if before_message_id is not None:
            query = query.where(Message.id < before_message_id)
        rows = self.db.scalars(query.order_by(Message.id.desc()).limit(self.limit)).all()
        return [
            Turn(role=m.sender, text=m.text, entities=(m.extras or {}).get("entities") or {})  # type: ignore[arg-type]
            for m in reversed(rows)
        ]
