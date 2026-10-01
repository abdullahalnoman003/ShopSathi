from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_shop_id, require_owner
from app.core.database import get_db
from app.schemas.policy import PolicyIn, PolicyOut
from app.services.policy import PolicyData, PolicyService

# Owner only (access matrix). The shop always comes from the token via get_current_shop_id.
router = APIRouter(prefix="/shop/policy", tags=["policy"], dependencies=[Depends(require_owner)])


def get_service(shop_id: int = Depends(get_current_shop_id), db: Session = Depends(get_db)) -> PolicyService:
    return PolicyService(db, shop_id)


def to_out(p: PolicyData) -> PolicyOut:
    return PolicyOut(
        delivery_time=p.delivery_time,
        return_rules=p.return_rules,
        payment_options=p.payment_options,
        delivery_areas=[{"area_name": n, "charge": c} for n, c in p.delivery_areas],
        updated_at=p.updated_at,
    )


@router.get("", response_model=PolicyOut)
def get_policy(svc: PolicyService = Depends(get_service)):
    return to_out(svc.get())


@router.put("", response_model=PolicyOut)
def save_policy(body: PolicyIn, svc: PolicyService = Depends(get_service)):
    return to_out(svc.save(body))
