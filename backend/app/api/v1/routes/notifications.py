from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_shop_id, require_shop_user
from app.core.database import get_db
from app.models import Chat, Notification
from app.schemas.notifications import MarkedRead, NotificationList, NotificationOut

# Owner and moderator (access matrix: flagged chats). Always scoped to the caller's shop.
router = APIRouter(prefix="/notifications", tags=["notifications"], dependencies=[Depends(require_shop_user)])

MAX_ITEMS = 50


def _out(n: Notification, customer_name: str | None) -> NotificationOut:
    return NotificationOut(
        id=n.id,
        type=n.type,
        chat_id=n.chat_id,
        reason=n.reason,
        customer_name=customer_name,
        created_at=n.created_at,
        read_at=n.read_at,
    )


@router.get("", response_model=NotificationList)
def list_notifications(shop_id: int = Depends(get_current_shop_id), db: Session = Depends(get_db)):
    """Unread first, then newest first."""
    rows = db.execute(
        select(Notification, Chat.customer_name)
        .join(Chat, Chat.id == Notification.chat_id)
        .where(Notification.shop_id == shop_id)
        .order_by(Notification.read_at.is_(None).desc(), Notification.created_at.desc(), Notification.id.desc())
        .limit(MAX_ITEMS)
    ).all()
    unread = db.scalar(
        select(func.count()).select_from(Notification).where(Notification.shop_id == shop_id, Notification.read_at.is_(None))
    )
    return NotificationList(unread_count=unread or 0, items=[_out(n, name) for n, name in rows])


@router.post("/read-all", response_model=MarkedRead)
def mark_all_read(shop_id: int = Depends(get_current_shop_id), db: Session = Depends(get_db)):
    result = db.execute(
        update(Notification)
        .where(Notification.shop_id == shop_id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(timezone.utc))
    )
    db.commit()
    return MarkedRead(marked=result.rowcount or 0)


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: int, shop_id: int = Depends(get_current_shop_id), db: Session = Depends(get_db)):
    n = db.scalars(select(Notification).where(Notification.id == notification_id, Notification.shop_id == shop_id)).first()
    if n is None:  # also hides other shops' notifications
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    if n.read_at is None:
        n.read_at = datetime.now(timezone.utc)
        db.commit()
    name = db.scalar(select(Chat.customer_name).where(Chat.id == n.chat_id))
    return _out(n, name)
