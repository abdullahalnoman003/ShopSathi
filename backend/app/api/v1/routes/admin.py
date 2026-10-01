import logging
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.config import get_settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.roles import PLATFORM_ADMIN
from app.models import AdminAction, AiUsageLog, Chat, FacebookPage, Order, Plan, Product, Shop, ShopMessageUsage, User
from app.schemas.admin import (
    AdminPlan,
    AdminPlanRef,
    AdminShop,
    AdminShopDetail,
    AdminShopPage,
    AiUsageReport,
    ComponentHealth,
    OperationUsage,
    PlanChange,
    PlanUpdate,
    ShopAiUsage,
    SystemHealth,
)
from app.services.plans import assign_plan, get_plan_by_code, list_plans
from app.services.usage import current_period

# Platform admin panel (FR-16). Only the platform admin; shop users get 403. The admin sees shops, plans, AI cost and
# system health. It never reads a shop's chats or messages and cannot act as a shop user.
router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger("shopsathi.admin")

DHAKA = ZoneInfo("Asia/Dhaka")
CELERY_QUEUE = "celery"  # the default Celery queue (a Redis list)
WORKER_PING_SECONDS = 3


def _record(db: Session, admin: User, action: str, shop_id: int | None, **detail) -> None:
    db.add(AdminAction(admin_user_id=admin.id, shop_id=shop_id, action=action, detail=detail))


def _get_shop(db: Session, shop_id: int) -> Shop:
    shop = db.get(Shop, shop_id)
    if shop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shop not found")
    return shop


# --------------------------------------------------------------------------- shops


def _shop_rows(db: Session, shops: list[Shop]) -> list[AdminShop]:
    ids = [s.id for s in shops]
    period = current_period()
    owners: dict[int, User] = {}
    pages: dict[int, str] = {}
    used: dict[int, int] = {}
    if ids:
        for u in db.scalars(select(User).where(User.shop_id.in_(ids), User.role == "owner").order_by(User.id.desc())):
            owners[u.shop_id] = u  # type: ignore[index]  # the oldest owner wins (ordered newest first)
        pages = dict(db.execute(select(FacebookPage.shop_id, FacebookPage.page_name).where(FacebookPage.shop_id.in_(ids))).all())
        used = dict(
            db.execute(
                select(ShopMessageUsage.shop_id, ShopMessageUsage.ai_messages_count).where(
                    ShopMessageUsage.shop_id.in_(ids), ShopMessageUsage.period == period
                )
            ).all()
        )
    return [
        AdminShop(
            id=s.id,
            name=s.name,
            owner_email=owners[s.id].email if s.id in owners else None,
            owner_name=owners[s.id].full_name if s.id in owners else None,
            plan=AdminPlanRef(code=s.plan.code, name=s.plan.name),
            status=s.status,
            created_at=s.created_at,
            connected_page_name=pages.get(s.id),
            ai_messages_used=used.get(s.id, 0),
            ai_messages_limit=s.plan.monthly_message_limit,
            usage_period=period,
        )
        for s in shops
    ]


def _detail(db: Session, shop: Shop) -> AdminShopDetail:
    base = _shop_rows(db, [shop])[0]
    counts = dict(
        product_count=db.scalar(select(func.count()).select_from(Product).where(Product.shop_id == shop.id)) or 0,
        chat_count=db.scalar(select(func.count()).select_from(Chat).where(Chat.shop_id == shop.id, Chat.channel == "messenger")) or 0,
        order_count=db.scalar(select(func.count()).select_from(Order).where(Order.shop_id == shop.id, Order.is_test.is_(False))) or 0,
    )
    return AdminShopDetail(**base.model_dump(), **counts)


@router.get("/shops", response_model=AdminShopPage)
def list_shops(
    q: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_roles(PLATFORM_ADMIN)),
    db: Session = Depends(get_db),
):
    query = select(Shop)
    term = q.strip()
    if term:
        like = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            or_(Shop.name.ilike(like, escape="\\"), Shop.id.in_(select(User.shop_id).where(User.email.ilike(like, escape="\\"))))
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    shops = db.scalars(query.order_by(Shop.created_at.desc(), Shop.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return AdminShopPage(items=_shop_rows(db, list(shops)), total=total, page=page, page_size=page_size)


@router.get("/shops/{shop_id}", response_model=AdminShopDetail)
def get_shop(shop_id: int, _: User = Depends(require_roles(PLATFORM_ADMIN)), db: Session = Depends(get_db)):
    return _detail(db, _get_shop(db, shop_id))


@router.post("/shops/{shop_id}/suspend", response_model=AdminShopDetail)
def suspend_shop(shop_id: int, admin: User = Depends(require_roles(PLATFORM_ADMIN)), db: Session = Depends(get_db)):
    """The shop's users are refused at once (login and every request) and the AI stops answering its customers."""
    shop = _get_shop(db, shop_id)
    if shop.status != "suspended":
        shop.status = "suspended"
        _record(db, admin, "suspend", shop.id)
        db.commit()
        logger.info("admin %s suspended shop %s", admin.id, shop.id)
    return _detail(db, shop)


@router.post("/shops/{shop_id}/reactivate", response_model=AdminShopDetail)
def reactivate_shop(shop_id: int, admin: User = Depends(require_roles(PLATFORM_ADMIN)), db: Session = Depends(get_db)):
    shop = _get_shop(db, shop_id)
    if shop.status != "active":
        shop.status = "active"
        _record(db, admin, "reactivate", shop.id)
        db.commit()
        logger.info("admin %s reactivated shop %s", admin.id, shop.id)
    return _detail(db, shop)


@router.post("/shops/{shop_id}/plan", response_model=AdminShopDetail)
def change_plan(shop_id: int, body: PlanChange, admin: User = Depends(require_roles(PLATFORM_ADMIN)), db: Session = Depends(get_db)):
    """An admin action: no simulated payment is recorded."""
    shop = _get_shop(db, shop_id)
    plan = get_plan_by_code(db, body.plan_code)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown plan")
    old = shop.plan.code
    if old != plan.code:
        assign_plan(db, shop, plan, record_simulated_payment=False)
        _record(db, admin, "change_plan", shop.id, **{"from": old, "to": plan.code})
        db.commit()
        db.refresh(shop)
    return _detail(db, shop)


# --------------------------------------------------------------------------- plans


@router.get("/plans", response_model=list[AdminPlan])
def get_plans(_: User = Depends(require_roles(PLATFORM_ADMIN)), db: Session = Depends(get_db)):
    return [AdminPlan(code=p.code, name=p.name, monthly_message_limit=p.monthly_message_limit, monthly_price=p.monthly_price) for p in list_plans(db)]


@router.put("/plans/{code}", response_model=AdminPlan)
def update_plan(code: str, body: PlanUpdate, admin: User = Depends(require_roles(PLATFORM_ADMIN)), db: Session = Depends(get_db)):
    """Edit the monthly message limit and the display price. Applies to every shop on the plan from now on."""
    plan = get_plan_by_code(db, code)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown plan")
    before = dict(monthly_message_limit=plan.monthly_message_limit, monthly_price=plan.monthly_price)
    plan.monthly_message_limit = body.monthly_message_limit
    plan.monthly_price = body.monthly_price
    _record(db, admin, "update_plan", None, plan=plan.code, before=before, after=body.model_dump())
    db.commit()
    return AdminPlan(code=plan.code, name=plan.name, monthly_message_limit=plan.monthly_message_limit, monthly_price=plan.monthly_price)


# --------------------------------------------------------------------------- AI usage and cost


def _usage(calls: int, tin: int | None, tout: int | None, cost: Decimal | None) -> OperationUsage:
    return OperationUsage(calls=calls, input_tokens=tin or 0, output_tokens=tout or 0, estimated_cost=cost or Decimal(0))


@router.get("/ai-usage", response_model=AiUsageReport)
def ai_usage(
    from_: date = Query(alias="from"),
    to: date = Query(),
    _: User = Depends(require_roles(PLATFORM_ADMIN)),
    db: Session = Depends(get_db),
):
    """AI calls, tokens and estimated cost (USD) per shop from ai_usage_logs, for Asia/Dhaka days from..to inclusive."""
    if from_ > to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The start date must not be after the end date.")
    max_days = get_settings().report_max_range_days
    if (to - from_).days + 1 > max_days:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Choose a range of at most {max_days} days.")
    start = datetime.combine(from_, time.min, tzinfo=DHAKA)
    end = datetime.combine(to + timedelta(days=1), time.min, tzinfo=DHAKA)
    rows = db.execute(
        select(
            AiUsageLog.shop_id,
            AiUsageLog.operation,
            func.count(),
            func.sum(AiUsageLog.input_tokens),
            func.sum(AiUsageLog.output_tokens),
            func.sum(AiUsageLog.estimated_cost),
        )
        .where(AiUsageLog.created_at >= start, AiUsageLog.created_at < end)
        .group_by(AiUsageLog.shop_id, AiUsageLog.operation)
    ).all()
    names = dict(db.execute(select(Shop.id, Shop.name).where(Shop.id.in_({r[0] for r in rows}))).all()) if rows else {}

    per_shop: dict[int, dict[str, OperationUsage]] = {}
    per_op: dict[str, list] = {}
    for shop_id, op, calls, tin, tout, cost in rows:
        per_shop.setdefault(shop_id, {})[op] = _usage(calls, tin, tout, cost)
        acc = per_op.setdefault(op, [0, 0, 0, Decimal(0)])
        acc[0] += calls
        acc[1] += int(tin or 0)
        acc[2] += int(tout or 0)
        acc[3] += cost or Decimal(0)

    shops = []
    for shop_id, ops in per_shop.items():
        shops.append(
            ShopAiUsage(
                shop_id=shop_id,
                shop_name=names.get(shop_id, f"Shop {shop_id}"),
                calls=sum(o.calls for o in ops.values()),
                input_tokens=sum(o.input_tokens for o in ops.values()),
                output_tokens=sum(o.output_tokens for o in ops.values()),
                estimated_cost=sum((o.estimated_cost for o in ops.values()), Decimal(0)),
                by_operation=ops,
            )
        )
    shops.sort(key=lambda s: (-s.estimated_cost, -s.calls, s.shop_id))
    by_operation = {op: _usage(*acc) for op, acc in sorted(per_op.items())}
    total = _usage(
        sum(s.calls for s in shops),
        sum(s.input_tokens for s in shops),
        sum(s.output_tokens for s in shops),
        sum((s.estimated_cost for s in shops), Decimal(0)),
    )
    return AiUsageReport(from_date=from_, to_date=to, shops=shops, total=total, by_operation=by_operation)


# --------------------------------------------------------------------------- system health


def _worker_health() -> ComponentHealth:
    from app.workers.celery_app import celery_app, ping

    try:
        if celery_app.conf.task_always_eager:
            return ComponentHealth(status="ok", detail="tasks run inline (test mode)")
        answer = ping.apply_async().get(timeout=WORKER_PING_SECONDS)
        return ComponentHealth(status="ok" if answer == "pong" else "error", detail=None if answer == "pong" else "unexpected answer")
    except Exception:  # no worker running, broker down, timeout
        return ComponentHealth(status="error", detail=f"no worker answered within {WORKER_PING_SECONDS} seconds")


@router.get("/system-health", response_model=SystemHealth)
def system_health(_: User = Depends(require_roles(PLATFORM_ADMIN)), db: Session = Depends(get_db)):
    try:
        db.execute(select(1))
        database = ComponentHealth(status="ok")
    except Exception:
        database = ComponentHealth(status="error", detail="the database did not answer")
    queue_length: int | None = None
    try:
        redis = get_redis()
        redis_health = ComponentHealth(status="ok" if redis.ping() else "error")
        queue_length = int(redis.llen(CELERY_QUEUE))
    except Exception:
        redis_health = ComponentHealth(status="error", detail="Redis did not answer")
    worker = _worker_health() if redis_health.status == "ok" else ComponentHealth(status="error", detail="the queue (Redis) is down")
    parts = [database, redis_health, worker]
    return SystemHealth(
        status="ok" if all(p.status == "ok" for p in parts) else "degraded",
        api=ComponentHealth(status="ok"),
        database=database,
        redis=redis_health,
        celery_worker=worker,
        celery_queue_length=queue_length,
    )
