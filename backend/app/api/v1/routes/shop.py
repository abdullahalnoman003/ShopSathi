from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_shop_id, require_owner
from app.core.database import get_db
from app.core.roles import MODERATOR
from app.core.security import hash_password
from app.models import Shop, User
from app.schemas.staff import StaffCreate, StaffOut
from app.schemas.plans import PlanChangeRequest, ShopPlanResponse
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
