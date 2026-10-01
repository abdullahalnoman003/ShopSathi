from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.plans import PlanOut
from app.services.plans import list_plans

router = APIRouter(tags=["plans"])


@router.get("/plans", response_model=list[PlanOut])
def get_plans(db: Session = Depends(get_db)):
    """Public: used on the sign-up page."""
    return list_plans(db)
