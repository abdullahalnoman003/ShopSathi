"""Monthly AI-reply limit service (FR-15).

Counting rule: one count = one AI reply sent to a customer on Messenger. Test chat window
messages are not counted. Counts reset per calendar month in Asia/Dhaka.

Prompt 14 calls can_send_ai_reply() before sending and record_ai_reply() after a reply is sent.
Nothing calls this service from a message flow yet.
"""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Plan, Shop, ShopMessageUsage
from app.services.tenant import scoped_select

DHAKA = ZoneInfo("Asia/Dhaka")


@dataclass(frozen=True)
class Usage:
    period: str
    used: int
    limit: int

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)


def current_period(now: datetime | None = None) -> str:
    """Calendar month in Asia/Dhaka, like '2026-10'. `now` must be timezone-aware (injectable for tests)."""
    now = now or datetime.now(DHAKA)
    return now.astimezone(DHAKA).strftime("%Y-%m")


class UsageLimitService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _limit(self, shop_id: int) -> int:
        limit = self.db.query(Plan.monthly_message_limit).join(Shop, Shop.plan_id == Plan.id).filter(Shop.id == shop_id).scalar()
        if limit is None:
            raise LookupError(f"Shop {shop_id} not found")
        return limit

    def get_usage(self, shop_id: int, now: datetime | None = None) -> Usage:
        period = current_period(now)
        row = self.db.scalars(
            scoped_select(ShopMessageUsage, shop_id).where(ShopMessageUsage.period == period)
        ).first()
        return Usage(period=period, used=row.ai_messages_count if row else 0, limit=self._limit(shop_id))

    def can_send_ai_reply(self, shop_id: int, now: datetime | None = None) -> bool:
        usage = self.get_usage(shop_id, now)
        return usage.used < usage.limit

    def record_ai_reply(self, shop_id: int, now: datetime | None = None) -> int:
        """Atomically add one to this month's count (single upsert, safe under concurrency).

        Commits, so the increment is durable and visible immediately. Returns the new count.
        """
        stmt = insert(ShopMessageUsage).values(
            shop_id=shop_id, period=current_period(now), ai_messages_count=1
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_shop_message_usage_shop_period",
            set_={"ai_messages_count": ShopMessageUsage.ai_messages_count + 1},
        ).returning(ShopMessageUsage.ai_messages_count)
        count = self.db.execute(stmt).scalar_one()
        self.db.commit()
        return count
