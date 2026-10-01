from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_shop_id, require_owner
from app.core.database import get_db
from app.models import Chat, Message, User
from app.schemas.test_chat import ChatStateOut, HandoverOut, MessageIn, MessageOut, SendMessageResponse, SessionOut
from app.services.conversation import ConversationService
from app.services.tenant import scoped_select

# Test chat window (FR-09): owner only (access matrix). Chats here have channel "test": they are not
# counted by UsageLimitService, and inbox / reports / exports must exclude them. Nothing is sent to Facebook.
router = APIRouter(prefix="/test-chat", tags=["test-chat"])

PREVIEW_CHARS = 80


def _get_test_chat(db: Session, shop_id: int, session_id: int) -> Chat:
    chat = db.scalars(
        scoped_select(Chat, shop_id).where(Chat.id == session_id, Chat.channel == "test")
    ).first()
    if chat is None:  # also hides other shops' chats
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test conversation not found")
    return chat


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def start_session(
    user: User = Depends(require_owner),
    shop_id: int = Depends(get_current_shop_id),
    db: Session = Depends(get_db),
):
    chat = Chat(shop_id=shop_id, channel="test", customer_name="Test customer", created_by_user_id=user.id)
    db.add(chat)
    db.commit()
    return SessionOut(
        id=chat.id, created_at=chat.created_at, updated_at=chat.updated_at, message_count=0, last_message=None
    )


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    _: User = Depends(require_owner),
    shop_id: int = Depends(get_current_shop_id),
    db: Session = Depends(get_db),
):
    chats = db.scalars(
        scoped_select(Chat, shop_id).where(Chat.channel == "test").order_by(Chat.updated_at.desc(), Chat.id.desc()).limit(50)
    ).all()
    ids = [c.id for c in chats]
    counts = dict(
        db.execute(
            select(Message.chat_id, func.count()).where(Message.shop_id == shop_id, Message.chat_id.in_(ids)).group_by(Message.chat_id)
        ).all()
    ) if ids else {}
    last_ids = (
        select(func.max(Message.id)).where(Message.shop_id == shop_id, Message.chat_id.in_(ids)).group_by(Message.chat_id)
    )
    last = {
        m.chat_id: m.text
        for m in db.scalars(select(Message).where(Message.id.in_(last_ids)))
    } if ids else {}
    return [
        SessionOut(
            id=c.id,
            created_at=c.created_at,
            updated_at=c.updated_at,
            message_count=counts.get(c.id, 0),
            last_message=(last[c.id][:PREVIEW_CHARS] if c.id in last else None),
            is_flagged=c.is_flagged,
            flag_reason=c.flag_reason,
            ai_paused=c.ai_paused,
        )
        for c in chats
    ]


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def list_messages(
    session_id: int,
    _: User = Depends(require_owner),
    shop_id: int = Depends(get_current_shop_id),
    db: Session = Depends(get_db),
):
    chat = _get_test_chat(db, shop_id, session_id)
    return list(
        db.scalars(scoped_select(Message, shop_id).where(Message.chat_id == chat.id).order_by(Message.id).limit(500))
    )


@router.post("/sessions/{session_id}/messages", response_model=SendMessageResponse)
def send_message(
    session_id: int,
    body: MessageIn,
    _: User = Depends(require_owner),
    shop_id: int = Depends(get_current_shop_id),
    db: Session = Depends(get_db),
):
    """Send a message as the customer; the AI's reply is in the response."""
    chat = _get_test_chat(db, shop_id, session_id)
    result = ConversationService(db).handle_customer_message(chat, body.text)
    db.refresh(chat)
    engine = result.engine_result
    return SendMessageResponse(
        customer_message=MessageOut.model_validate(result.customer_message),
        ai_message=MessageOut.model_validate(result.ai_message) if result.ai_message is not None else None,
        handover=HandoverOut(
            needed=bool(engine and engine.handover.needed), reason=engine.handover.reason if engine else None
        ),
        chat=ChatStateOut(is_flagged=chat.is_flagged, flag_reason=chat.flag_reason, ai_paused=chat.ai_paused),
    )
