from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_shop_id, require_owner
from app.core.config import get_settings
from app.core.database import get_db
from app.models import Chat, HandoverEvent, Message, Order
from app.schemas.reports import ReportSummary

# Reports (FR-14): owner only. Counts come straight from the records, always for the caller's shop, and never
# include Test chat window data (chat channel 'test', orders with is_test).
router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_owner)])

DHAKA = ZoneInfo("Asia/Dhaka")


def day_range(start: date, end: date) -> tuple[datetime, datetime]:
    """[start 00:00, end + 1 day 00:00) in Asia/Dhaka: both days are included."""
    return datetime.combine(start, time.min, tzinfo=DHAKA), datetime.combine(end + timedelta(days=1), time.min, tzinfo=DHAKA)


@router.get("/summary", response_model=ReportSummary)
def summary(
    from_: date = Query(alias="from"),
    to: date = Query(),
    shop_id: int = Depends(get_current_shop_id),
    db: Session = Depends(get_db),
):
    if from_ > to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The start date must not be after the end date.")
    max_days = get_settings().report_max_range_days
    if (to - from_).days + 1 > max_days:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Choose a range of at most {max_days} days.")
    start, end = day_range(from_, to)

    messages = db.scalar(
        select(func.count())
        .select_from(Message)
        .join(Chat, Chat.id == Message.chat_id)
        .where(
            Message.shop_id == shop_id,
            Chat.shop_id == shop_id,
            Chat.channel == "messenger",
            Message.sender == "ai",
            Message.sent_at.is_not(None),
            Message.sent_at >= start,
            Message.sent_at < end,
        )
    )
    handed = db.scalar(
        select(func.count(func.distinct(HandoverEvent.chat_id)))
        .join(Chat, Chat.id == HandoverEvent.chat_id)
        .where(
            HandoverEvent.shop_id == shop_id,
            Chat.shop_id == shop_id,
            Chat.channel == "messenger",
            HandoverEvent.created_at >= start,
            HandoverEvent.created_at < end,
        )
    )
    base = select(func.count()).select_from(Order).where(Order.shop_id == shop_id, Order.is_test.is_(False))
    drafted = db.scalar(base.where(Order.created_at >= start, Order.created_at < end))
    confirmed = db.scalar(base.where(Order.confirmed_at.is_not(None), Order.confirmed_at >= start, Order.confirmed_at < end))
    return ReportSummary(
        from_date=from_,
        to_date=to,
        messages_handled_by_ai=messages or 0,
        chats_handed_to_humans=handed or 0,
        orders_drafted=drafted or 0,
        orders_confirmed=confirmed or 0,
    )
