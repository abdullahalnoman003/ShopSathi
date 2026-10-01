"""Short-term chat memory in Redis: the last N turns of a chat, with a TTL.

Only these recent turns (never the whole history) are given to the AI. If the Redis key has expired, the
turns are rebuilt from the database so a returning customer keeps context.
"""

import json

from shopsathi_ai.understanding import Turn
from sqlalchemy import select
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

    def load(self, chat: Chat) -> list[Turn]:
        key = _key(chat.shop_id, chat.id)
        raw = self.redis.lrange(key, -self.limit, -1)
        if raw:
            return [_from_json(r) for r in raw]
        turns = self._rebuild(chat)
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

    def _rebuild(self, chat: Chat) -> list[Turn]:
        rows = self.db.scalars(
            scoped_select(Message, chat.shop_id)
            .where(Message.chat_id == chat.id)
            .order_by(Message.id.desc())
            .limit(self.limit)
        ).all()
        return [
            Turn(role=m.sender, text=m.text, entities=(m.extras or {}).get("entities") or {})  # type: ignore[arg-type]
            for m in reversed(rows)
        ]
