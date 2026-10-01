"""Weekly AI chat insights (AI-6, AI-R12): the top customer questions of a week and the products customers asked for
that the shop does not have. The language work is in the AI engine (shopsathi_ai.insights); this service loads the
week's Messenger customer messages of ONE shop, stores the result and logs the AI usage (NFR-08)."""

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from shopsathi_ai.insights import WeeklyInsights, summarize_week
from shopsathi_ai.providers import EmbeddingProviderError, LLMProvider, LLMProviderError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ai_adapters.factory import get_embedder, get_llm
from app.ai_adapters.gateway import BackendShopDataGateway
from app.core.config import get_settings
from app.models import Chat, Message, Shop, WeeklyInsight
from app.services.ai_usage import log_ai_usage
from app.services.tenant import scoped_select

logger = logging.getLogger("shopsathi.insights")

DHAKA = ZoneInfo("Asia/Dhaka")
OPERATION = "weekly_insights"
MIN_NAME_MATCH = 0.5  # same rule as the chat: at least half of the words are in the product name


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def previous_week_start(now: datetime | None = None) -> date:
    """Monday of the last complete week (Asia/Dhaka)."""
    today = (now or datetime.now(DHAKA)).astimezone(DHAKA).date()
    return monday_of(today) - timedelta(days=7)


def week_window(week_start: date) -> tuple[datetime, datetime]:
    """[Monday 00:00, next Monday 00:00) in Asia/Dhaka."""
    return (
        datetime.combine(week_start, time.min, tzinfo=DHAKA),
        datetime.combine(week_start + timedelta(days=7), time.min, tzinfo=DHAKA),
    )


class InsightsService:
    def __init__(self, db: Session, llm: LLMProvider | None = None) -> None:
        self.db = db
        self._llm = llm

    @property
    def llm(self) -> LLMProvider:
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    # ------------------------------------------------------------------ input

    def _messages(self, shop_id: int, week_start: date) -> tuple[list[str], list[str]]:
        """(customer message texts, customer names to remove) of this shop's Messenger chats in that week.
        Test chat window messages are never used."""
        start, end = week_window(week_start)
        when = func.coalesce(Message.received_at, Message.created_at)
        rows = self.db.execute(
            select(Message.text, Chat.customer_name)
            .join(Chat, Chat.id == Message.chat_id)
            .where(
                Message.shop_id == shop_id,
                Chat.shop_id == shop_id,
                Chat.channel == "messenger",
                Message.sender == "customer",
                when >= start,
                when < end,
            )
            .order_by(Message.id)
        ).all()
        names: set[str] = set()
        for _, full in rows:  # the whole name and each part of it ("Nasrin Sultana" -> also "Nasrin")
            if full:
                names.add(full)
                names.update(part for part in full.split() if len(part) >= 3)
        names = sorted(names)
        return [t for t, _ in rows], names

    def _product_lookup(self, shop_id: int):
        """True if the shop's catalogue has a product matching the name: by name words first, then by meaning (the
        same two checks the chat uses). The catalogue decides, never the model."""
        gateway = BackendShopDataGateway(self.db)
        s = get_settings()

        def lookup(name: str) -> bool:
            hits = gateway.search_products(shop_id, name, None, 5)
            if any(p.match == "name" and p.score >= MIN_NAME_MATCH for p in hits):
                return True
            try:
                embedded = get_embedder().embed_with_usage([name], is_query=True)
            except EmbeddingProviderError:
                return False
            gateway.log_ai_usage(shop_id, OPERATION, embedded.provider, embedded.model, embedded.input_tokens)
            hits = gateway.search_products(shop_id, name, embedded.vectors[0], 5)
            return any(p.match == "semantic" and p.score >= s.rag_min_product_score for p in hits)

        return lookup

    # ------------------------------------------------------------------ generate

    def generate_for_shop(self, shop_id: int, week_start: date) -> WeeklyInsight:
        """Summarise that week for this shop and store it (replacing an earlier summary of the same week).
        A shop without messages gets an empty summary. Raises LLMProviderError if the model cannot be used: no
        made-up summary is stored."""
        if week_start.weekday() != 0:
            raise ValueError("week_start must be a Monday")
        texts, names = self._messages(shop_id, week_start)
        try:
            result: WeeklyInsights = summarize_week(self.llm, texts, self._product_lookup(shop_id), known_terms=names)
        except LLMProviderError as e:
            self._log_usage(shop_id, getattr(e, "usage", []))  # the calls made before the failure still cost money
            raise
        self._log_usage(shop_id, result.usage)
        values = dict(
            top_questions=[{"question": q.question, "count": q.count} for q in result.top_questions],
            missing_products=[{"name": p.name, "count": p.count} for p in result.missing_products],
        )
        stmt = (
            insert(WeeklyInsight)
            .values(shop_id=shop_id, week_start=week_start, **values)
            .on_conflict_do_update(constraint="uq_weekly_insights_shop_week", set_={**values, "created_at": func.now()})
            .returning(WeeklyInsight.id)
        )
        row_id = self.db.execute(stmt).scalar_one()
        self.db.commit()
        row = self.db.get(WeeklyInsight, row_id)
        self.db.refresh(row)
        logger.info("weekly insights for shop %s, week %s: %s questions, %s missing products (%s messages)",
                    shop_id, week_start, len(values["top_questions"]), len(values["missing_products"]), result.messages_used)
        return row

    def _log_usage(self, shop_id: int, calls) -> None:
        for call in calls:
            log_ai_usage(self.db, shop_id, OPERATION, call.provider, call.model, call.input_tokens, call.output_tokens)

    def generate_for_all(self, week_start: date, *, replace: bool = False) -> dict[str, int]:
        """The weekly job: every active shop, one after the other. A failing shop never stops the others."""
        done = skipped = failed = 0
        shop_ids = list(self.db.scalars(select(Shop.id).where(Shop.status == "active").order_by(Shop.id)))
        for shop_id in shop_ids:
            exists = self.db.scalar(
                scoped_select(WeeklyInsight, shop_id).where(WeeklyInsight.week_start == week_start).with_only_columns(WeeklyInsight.id)
            )
            if exists is not None and not replace:
                skipped += 1
                continue
            try:
                self.generate_for_shop(shop_id, week_start)
                done += 1
            except Exception as e:  # noqa: BLE001 - one shop's failure (model down, ...) must not stop the rest
                self.db.rollback()
                failed += 1
                logger.error("weekly insights failed for shop %s: %s", shop_id, e.__class__.__name__)
        return {"generated": done, "skipped": skipped, "failed": failed}
