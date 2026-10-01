"""Plan lookup, assignment (with simulated payment record) and seeding. Reused by Prompt 19 (admin plan change)."""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Plan, Shop, SimulatedPayment

PLANS_SEED_FILE = Path(__file__).resolve().parents[3] / "database" / "seed" / "plans.json"


def list_plans(db: Session) -> list[Plan]:
    return list(db.scalars(select(Plan).order_by(Plan.monthly_price, Plan.id)))


def get_plan_by_code(db: Session, code: str) -> Plan | None:
    return db.scalar(select(Plan).where(Plan.code == code))


def is_paid(plan: Plan) -> bool:
    return plan.monthly_price > 0


def assign_plan(db: Session, shop: Shop, plan: Plan, *, record_simulated_payment: bool) -> None:
    """Set the shop's plan; optionally record a simulated payment. The shop must be flushed. Does not commit."""
    shop.plan = plan
    if record_simulated_payment:
        db.add(
            SimulatedPayment(
                shop_id=shop.id,
                plan_id=plan.id,
                amount=plan.monthly_price,
                status="simulated_success",
            )
        )


def seed_plans(db: Session, path: Path = PLANS_SEED_FILE) -> int:
    """Upsert the plans from database/seed/plans.json by code. Returns the number of plans."""
    items = json.loads(path.read_text(encoding="utf-8"))["plans"]
    for item in items:
        plan = get_plan_by_code(db, item["code"])
        if plan is None:
            plan = Plan(code=item["code"])
            db.add(plan)
        plan.name = item["name"]
        plan.monthly_message_limit = item["monthly_message_limit"]
        plan.monthly_price = item["monthly_price"]
    db.commit()
    return len(items)


class PlanSelectionError(ValueError):
    """Invalid plan choice (unknown plan, or a paid plan without simulated payment confirmation)."""


def resolve_plan_choice(db: Session, code: str, simulated_payment_confirmed: bool) -> Plan:
    plan = get_plan_by_code(db, code)
    if plan is None:
        raise PlanSelectionError("Unknown plan")
    if is_paid(plan) and not simulated_payment_confirmed:
        raise PlanSelectionError("Paid plans need the simulated payment confirmation")
    return plan
