import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_shop_id, require_shop_user
from app.core.database import get_db
from app.integrations.facebook.messenger_sender import (
    MESSAGING_WINDOW,
    MessengerSender,
    MessengerSendError,
    OutsideMessagingWindow,
    window_open,
)
from app.models import Chat, FacebookPage, Message, Notification, User
from app.schemas.inbox import InboxChat, InboxChatDetail, InboxMessage, InboxPage, ReplyIn
from app.services.tenant import scoped_select

# Inbox (FR-10, FR-11): Messenger chats only (test chats never appear), owner and moderator, always scoped to the
# caller's shop. Manual replies go through MessengerSender so Meta's 24-hour window applies (NFR-09) and are
# never counted as AI messages.
router = APIRouter(prefix="/chats", tags=["chats"], dependencies=[Depends(require_shop_user)])
logger = logging.getLogger("shopsathi.inbox")

PREVIEW_CHARS = 80
MAX_MESSAGES = 500
WINDOW_CLOSED_TEXT = (
    "Facebook only allows a reply within 24 hours of the customer's last message. "
    "This window has closed, so nothing was sent."
)


def _label(chat: Chat) -> str:
    if chat.customer_name:
        return chat.customer_name
    tail = (chat.customer_psid or "")[-4:]
    return f"Customer ...{tail}" if tail else "Customer"


def _out(chat: Chat, last: Message | None) -> dict:
    return dict(
        id=chat.id,
        customer_name=chat.customer_name,
        customer_label=_label(chat),
        last_message=last.text[:PREVIEW_CHARS] if last is not None else None,
        last_message_sender=last.sender if last is not None else None,
        is_flagged=chat.is_flagged,
        flag_reason=chat.flag_reason if chat.is_flagged else None,
        flagged_at=chat.flagged_at if chat.is_flagged else None,
        ai_paused=chat.ai_paused,
        last_activity_at=last.created_at if last is not None else chat.created_at,
        window_open=window_open(chat.last_customer_message_at),
        window_closes_at=(chat.last_customer_message_at + MESSAGING_WINDOW) if chat.last_customer_message_at else None,
    )


def _get_chat(db: Session, shop_id: int, chat_id: int) -> Chat:
    chat = db.scalars(scoped_select(Chat, shop_id).where(Chat.id == chat_id, Chat.channel == "messenger")).first()
    if chat is None:  # also hides other shops' chats and test chats
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
    return chat


def _detail(db: Session, shop_id: int, chat: Chat) -> InboxChatDetail:
    db.refresh(chat)
    msgs = list(
        db.scalars(scoped_select(Message, shop_id).where(Message.chat_id == chat.id).order_by(Message.id).limit(MAX_MESSAGES))
    )
    return InboxChatDetail(**_out(chat, msgs[-1] if msgs else None), messages=[InboxMessage.model_validate(m) for m in msgs])


@router.get("", response_model=InboxPage)
def list_chats(
    filter: Literal["flagged", "all"] = "all",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    shop_id: int = Depends(get_current_shop_id),
    db: Session = Depends(get_db),
):
    """Flagged chats first (oldest flag first: they have waited longest), then by latest activity."""
    base = scoped_select(Chat, shop_id).where(Chat.channel == "messenger")
    flagged_count = db.scalar(select(func.count()).select_from(base.where(Chat.is_flagged.is_(True)).subquery())) or 0
    if filter == "flagged":
        base = base.where(Chat.is_flagged.is_(True))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    last_msg = (
        select(Message.chat_id, func.max(Message.id).label("mid"))
        .where(Message.shop_id == shop_id)
        .group_by(Message.chat_id)
        .subquery()
    )
    activity = func.coalesce(select(Message.created_at).where(Message.id == last_msg.c.mid).scalar_subquery(), Chat.created_at)
    chats = db.scalars(
        base.outerjoin(last_msg, last_msg.c.chat_id == Chat.id)
        .order_by(Chat.is_flagged.desc(), Chat.flagged_at.asc().nulls_last(), activity.desc(), Chat.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    ids = [c.id for c in chats]
    lasts: dict[int, Message] = {}
    if ids:
        newest = select(func.max(Message.id)).where(Message.shop_id == shop_id, Message.chat_id.in_(ids)).group_by(Message.chat_id)
        lasts = {m.chat_id: m for m in db.scalars(select(Message).where(Message.shop_id == shop_id, Message.id.in_(newest)))}
    return InboxPage(
        items=[InboxChat(**_out(c, lasts.get(c.id))) for c in chats],
        total=total,
        page=page,
        page_size=page_size,
        flagged_count=flagged_count,
    )


@router.get("/{chat_id}", response_model=InboxChatDetail)
def get_chat(chat_id: int, shop_id: int = Depends(get_current_shop_id), db: Session = Depends(get_db)):
    return _detail(db, shop_id, _get_chat(db, shop_id, chat_id))


@router.post("/{chat_id}/pause", response_model=InboxChatDetail)
def pause_ai(chat_id: int, shop_id: int = Depends(get_current_shop_id), db: Session = Depends(get_db)):
    """The seller takes over: the AI stops answering this chat (customer messages are still saved)."""
    chat = _get_chat(db, shop_id, chat_id)
    if not chat.ai_paused:
        chat.ai_paused = True
        db.commit()
    return _detail(db, shop_id, chat)


@router.post("/{chat_id}/resume", response_model=InboxChatDetail)
def resume_ai(chat_id: int, shop_id: int = Depends(get_current_shop_id), db: Session = Depends(get_db)):
    """Hand the chat back to the AI. Does not change the flag (see resolve-flag)."""
    chat = _get_chat(db, shop_id, chat_id)
    if chat.ai_paused:
        chat.ai_paused = False
        db.commit()
    return _detail(db, shop_id, chat)


@router.post("/{chat_id}/resolve-flag", response_model=InboxChatDetail)
def resolve_flag(chat_id: int, shop_id: int = Depends(get_current_shop_id), db: Session = Depends(get_db)):
    """Mark the flagged chat as handled and its notifications as read. The AI pause stays as it is."""
    chat = _get_chat(db, shop_id, chat_id)
    chat.is_flagged = False
    db.execute(
        update(Notification)
        .where(Notification.shop_id == shop_id, Notification.chat_id == chat.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(timezone.utc))
    )
    db.commit()
    return _detail(db, shop_id, chat)


@router.post("/{chat_id}/reply", response_model=InboxMessage, status_code=status.HTTP_201_CREATED)
def reply(
    chat_id: int,
    body: ReplyIn,
    user: User = Depends(require_shop_user),
    shop_id: int = Depends(get_current_shop_id),
    db: Session = Depends(get_db),
):
    """The seller's own reply. Only while the AI is paused for the chat, only within Meta's 24-hour window."""
    chat = _get_chat(db, shop_id, chat_id)
    if not chat.ai_paused:
        raise HTTPException(status.HTTP_409_CONFLICT, "Pause the AI for this chat before replying yourself.")
    if not window_open(chat.last_customer_message_at):
        raise HTTPException(status.HTTP_409_CONFLICT, WINDOW_CLOSED_TEXT)
    page = db.scalars(scoped_select(FacebookPage, shop_id)).first()
    if page is None or not chat.customer_psid:
        raise HTTPException(status.HTTP_409_CONFLICT, "No Facebook Page is connected, so the reply cannot be sent.")
    try:
        fb_mid = MessengerSender().send_text(page, chat.customer_psid, body.text, chat.last_customer_message_at)
    except OutsideMessagingWindow:
        raise HTTPException(status.HTTP_409_CONFLICT, WINDOW_CLOSED_TEXT)
    except MessengerSendError as e:
        logger.warning("manual reply to chat %s not sent (%s)", chat.id, e.reason)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Facebook did not accept the message, so it was not sent. Please try again.")

    now = datetime.now(timezone.utc)
    msg = Message(
        shop_id=shop_id,
        chat_id=chat.id,
        sender="seller",
        text=body.text,
        sent_at=now,
        extras={"sent_by_user_id": user.id, "delivery": {"status": "sent", "facebook_message_id": fb_mid}},
    )
    db.add(msg)
    chat.updated_at = now
    db.commit()  # not counted by UsageLimitService: only AI replies are
    return InboxMessage.model_validate(msg)
