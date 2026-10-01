from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import DENYLIST_PREFIX, get_current_shop_id, get_token_payload, require_owner
from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import check_rate_limit
from app.core.redis import get_redis
from app.core.roles import MODERATOR
from app.core.security import hash_password, verify_password
from app.models import Shop, User
from app.schemas.auth import MessageResponse
from app.schemas.staff import ShopDelete, StaffCreate, StaffOut
from app.schemas.plans import PlanChangeRequest, ShopPlanResponse
from app.services.shop_deletion import ShopDeletionService
from app.services.plans import PlanSelectionError, assign_plan, is_paid, resolve_plan_choice
from app.services.tenant import scoped_select
from app.services.usage import UsageLimitService

router = APIRouter(prefix="/shop", tags=["shop"])


def _plan_response(db: Session, shop: Shop) -> ShopPlanResponse:
    usage = UsageLimitService(db).get_usage(shop.id)
    return ShopPlanResponse.model_validate(
        {
            "plan": shop.plan,
            "usage": {
                "period": usage.period,
                "used": usage.used,
                "limit": usage.limit,
                "remaining": usage.remaining,
            },
        },
        from_attributes=True,
    )


@router.get("/plan", response_model=ShopPlanResponse)
def get_shop_plan(shop_id: int = Depends(get_current_shop_id), db: Session = Depends(get_db)):
    return _plan_response(db, db.get(Shop, shop_id))


@router.post("/plan/change", response_model=ShopPlanResponse)
def change_shop_plan(
    body: PlanChangeRequest,
    user: User = Depends(require_owner),
    shop_id: int = Depends(get_current_shop_id),
    db: Session = Depends(get_db),
):
    shop = db.get(Shop, shop_id)
    try:
        plan = resolve_plan_choice(db, body.plan_code, body.simulated_payment_confirmed)
    except PlanSelectionError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    if plan.id == shop.plan_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You are already on this plan")
    assign_plan(db, shop, plan, record_simulated_payment=is_paid(plan))
    db.commit()
    return _plan_response(db, shop)


@router.get("/staff", response_model=list[StaffOut])
def list_staff(
    _: User = Depends(require_owner),
    shop_id: int = Depends(get_current_shop_id),
    db: Session = Depends(get_db),
):
    q = scoped_select(User, shop_id).where(User.role == MODERATOR).order_by(User.id)
    return list(db.scalars(q))


@router.post("/staff", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
def add_staff(
    body: StaffCreate,
    _: User = Depends(require_owner),
    shop_id: int = Depends(get_current_shop_id),
    db: Session = Depends(get_db),
):
    """Create a Moderator in the owner's shop. They can change the password via the reset flow."""
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=MODERATOR,
        shop_id=shop_id,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email is already registered")
    return user


@router.delete("", response_model=MessageResponse)
def delete_shop(
    body: ShopDelete,
    user: User = Depends(require_owner),
    shop_id: int = Depends(get_current_shop_id),
    payload: dict[str, Any] = Depends(get_token_payload),
    db: Session = Depends(get_db),
):
    """Permanently delete this shop and ALL its data (products, chats, messages, orders, customers' details ...).
    Needs the owner's current password and the exact shop name. Cannot be undone."""
    s = get_settings()
    check_rate_limit("shop-delete", str(user.id), s.login_rate_limit, s.login_rate_window_seconds)  # no password guessing
    shop = db.get(Shop, shop_id)
    if body.shop_name != shop.name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The shop name does not match. Type it exactly as shown.")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Incorrect password.")
    ShopDeletionService(db).delete_shop(shop_id)
    ttl = int(payload["exp"] - datetime.now(timezone.utc).timestamp())  # the current token stops working at once
    if ttl > 0:
        get_redis().set(DENYLIST_PREFIX + payload["jti"], 1, ex=ttl)
    return MessageResponse(message="Your shop and all its data were deleted.")
