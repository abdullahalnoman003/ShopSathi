import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from shopsathi_ai.ordering import MAX_QUANTITY
from shopsathi_ai.validators import normalize_and_validate_bd_phone
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_shop_id, require_shop_user
from app.core.database import get_db
from app.models import Order, Product, User
from app.schemas.orders import OrderOut, OrderPage, OrderPatch, ProductOption
from app.services.tenant import scoped_select

# Order dashboard (FR-12, FR-13): owner and moderator, always scoped to the caller's shop. Orders made in the
# Test chat window (is_test) never appear. Only a person confirms (AI-R11). ShopSathi ends at confirmation:
# no courier booking, payment, invoice or stock deduction.
router = APIRouter(prefix="/orders", tags=["orders"], dependencies=[Depends(require_shop_user)])

DHAKA = ZoneInfo("Asia/Dhaka")
CSV_COLUMNS = [
    "order_id", "confirmed_at", "customer_name", "customer_phone", "customer_address",
    "product_name", "size", "colour", "quantity", "unit_price", "total_price",
]
MAX_EXPORT_DAYS = 366


def _base(shop_id: int):
    return scoped_select(Order, shop_id).where(Order.is_test.is_(False))


def _get_order(db: Session, shop_id: int, order_id: int) -> Order:
    order = db.scalars(_base(shop_id).where(Order.id == order_id)).first()
    if order is None:  # also hides other shops' orders and test orders
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


def _out(db: Session, shop_id: int, order: Order) -> OrderOut:
    sizes = colours = None
    if order.product_id is not None:
        product = db.scalars(scoped_select(Product, shop_id).where(Product.id == order.product_id)).first()
        if product is not None:
            sizes, colours = list(product.sizes), list(product.colours)
    return OrderOut.model_validate(
        {
            **{c: getattr(order, c) for c in OrderOut.model_fields if hasattr(order, c)},
            "total_price": order.unit_price * order.quantity,
            "product_sizes": sizes,
            "product_colours": colours,
        }
    )


def _need_draft(order: Order, action: str) -> None:
    if order.status != "draft":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This order is already {order.status}, so it cannot be {action}. Only draft orders can be {action}.",
        )


def _match(value: str, options: list[str]) -> str | None:
    return next((o for o in options if o.lower() == value.strip().lower()), None)


@router.get("", response_model=OrderPage)
def list_orders(
    status_: Literal["draft", "confirmed", "cancelled"] = Query(default="draft", alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    shop_id: int = Depends(get_current_shop_id),
    db: Session = Depends(get_db),
):
    base = _base(shop_id)
    counts = dict(db.execute(select(Order.status, func.count()).where(Order.shop_id == shop_id, Order.is_test.is_(False)).group_by(Order.status)).all())
    rows = db.scalars(
        base.where(Order.status == status_).order_by(Order.created_at.desc(), Order.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return OrderPage(
        items=[_out(db, shop_id, o) for o in rows],
        total=counts.get(status_, 0),
        page=page,
        page_size=page_size,
        counts={s: counts.get(s, 0) for s in ("draft", "confirmed", "cancelled")},
    )


def _safe_cell(value: object) -> str:
    """Customer-written text must not turn into a spreadsheet formula when the CSV is opened."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get("/export")
def export_confirmed(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = None,
    shop_id: int = Depends(get_current_shop_id),
    db: Session = Depends(get_db),
):
    """Confirmed orders whose confirmation date (Asia/Dhaka, both days included) is in the range, as a CSV for the courier."""
    if from_ and to and from_ > to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The start date must not be after the end date.")
    if from_ and to and (to - from_).days > MAX_EXPORT_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Choose a range of at most {MAX_EXPORT_DAYS} days.")
    q = _base(shop_id).where(Order.status == "confirmed")
    if from_:
        q = q.where(Order.confirmed_at >= datetime.combine(from_, time.min, tzinfo=DHAKA))
    if to:
        q = q.where(Order.confirmed_at < datetime.combine(to + timedelta(days=1), time.min, tzinfo=DHAKA))
    orders = db.scalars(q.order_by(Order.confirmed_at, Order.id)).all()

    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for o in orders:
        total: Decimal = o.unit_price * o.quantity
        writer.writerow([
            o.id,
            o.confirmed_at.astimezone(DHAKA).strftime("%Y-%m-%d %H:%M") if o.confirmed_at else "",
            _safe_cell(o.customer_name),
            o.customer_phone,
            _safe_cell(o.customer_address),
            _safe_cell(o.product_name),
            _safe_cell(o.size),
            _safe_cell(o.colour),
            o.quantity,
            f"{o.unit_price:.2f}",
            f"{total:.2f}",
        ])
    name = f"confirmed-orders-{from_.isoformat() if from_ else 'start'}-to-{to.isoformat() if to else 'today'}.csv"
    return Response(
        content=("﻿" + out.getvalue()).encode("utf-8"),  # BOM: Excel opens Bangla text correctly
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/product-options", response_model=list[ProductOption])
def product_options(shop_id: int = Depends(get_current_shop_id), db: Session = Depends(get_db)):
    """The shop's products with their options, for the edit form (moderators cannot use the products API)."""
    rows = db.scalars(scoped_select(Product, shop_id).order_by(Product.name, Product.id).limit(500)).all()
    return [ProductOption(id=p.id, name=p.name, price=p.price, sizes=list(p.sizes), colours=list(p.colours), stock_count=p.stock_count) for p in rows]


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, shop_id: int = Depends(get_current_shop_id), db: Session = Depends(get_db)):
    return _out(db, shop_id, _get_order(db, shop_id, order_id))


@router.patch("/{order_id}", response_model=OrderOut)
def edit_order(
    order_id: int,
    body: OrderPatch,
    shop_id: int = Depends(get_current_shop_id),
    db: Session = Depends(get_db),
):
    """Edit a draft with the same rules as drafting. Changing the product takes the catalogue price again."""
    order = _get_order(db, shop_id, order_id)
    _need_draft(order, "edited")
    sent = body.model_fields_set
    errors: dict[str, str] = {}

    product = None
    product_changed = "product_id" in sent and body.product_id is not None and body.product_id != order.product_id
    if "product_id" in sent and body.product_id is None:
        errors["product_id"] = "A product is required."
    target_id = body.product_id if product_changed else order.product_id
    if target_id is not None:
        product = db.scalars(scoped_select(Product, shop_id).where(Product.id == target_id)).first()
        if product is None and product_changed:
            errors["product_id"] = "This product does not exist in your shop."

    size = body.size if "size" in sent else order.size
    colour = body.colour if "colour" in sent else order.colour
    if product_changed and product is not None:  # the old product's size/colour rarely fit the new one
        size = body.size if "size" in sent else None
        colour = body.colour if "colour" in sent else None
    if product is not None:
        for key, value, options in (("size", size, list(product.sizes)), ("colour", colour, list(product.colours))):
            if not options:
                if value:
                    errors[key] = f"{product.name} has no {key} options."
                value = None
            elif not value:
                errors[key] = f"Choose a {key}: {', '.join(options)}."
            elif _match(value, options) is None:
                errors[key] = f"{value} is not available for {product.name}. Choose one of: {', '.join(options)}."
            else:
                value = _match(value, options)
            if key == "size":
                size = value
            else:
                colour = value

    quantity = body.quantity if "quantity" in sent and body.quantity is not None else order.quantity
    if "quantity" in sent and body.quantity is None:
        errors["quantity"] = "Quantity must be a whole number above 0."
    elif quantity > MAX_QUANTITY:
        errors["quantity"] = f"Quantity must be at most {MAX_QUANTITY}."
    elif product is not None and (product_changed or quantity != order.quantity) and quantity > product.stock_count:
        errors["quantity"] = f"Only {product.stock_count} of {product.name} in stock."

    values: dict[str, str] = {}
    for key, label in (("customer_name", "Name"), ("customer_address", "Address")):
        if key in sent:
            v = getattr(body, key)
            if not v:
                errors[key] = f"{label} must not be empty."
            else:
                values[key] = v
    if "customer_phone" in sent:
        phone = normalize_and_validate_bd_phone(body.customer_phone)
        if phone is None:
            errors["customer_phone"] = "Enter a valid Bangladeshi mobile number, like 01712345678."
        else:
            values["customer_phone"] = phone

    if errors:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [{"loc": ["body", k], "msg": m, "type": "value_error"} for k, m in errors.items()],
        )

    if product is not None and product_changed:
        order.product_id = product.id
        order.product_name = product.name
        order.unit_price = product.price  # catalogue price, never typed in
    order.size, order.colour, order.quantity = size, colour, quantity
    for key, v in values.items():
        setattr(order, key, v)
    db.commit()
    return _out(db, shop_id, order)


@router.post("/{order_id}/confirm", response_model=OrderOut)
def confirm_order(
    order_id: int,
    user: User = Depends(require_shop_user),
    shop_id: int = Depends(get_current_shop_id),
    db: Session = Depends(get_db),
):
    order = _get_order(db, shop_id, order_id)
    _need_draft(order, "confirmed")
    order.status = "confirmed"
    order.confirmed_at = datetime.now(timezone.utc)
    order.confirmed_by_user_id = user.id
    db.commit()
    return _out(db, shop_id, order)


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel_order(order_id: int, shop_id: int = Depends(get_current_shop_id), db: Session = Depends(get_db)):
    order = _get_order(db, shop_id, order_id)
    _need_draft(order, "cancelled")
    order.status = "cancelled"
    order.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    return _out(db, shop_id, order)
