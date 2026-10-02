"""Command entry point: python -m app.cli <command>. Later prompts add commands."""

import argparse
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Chat, HandoverEvent, Message, Notification, Order, Product, Shop, ShopPolicy, User
from app.schemas.policy import PolicyIn
from app.services.plans import get_plan_by_code, seed_plans
from app.services.embeddings import DimensionMismatch, EmbeddingService
from app.services.policy import PolicyService
from app.services.products import product_hooks

SEED_DIR = Path(__file__).resolve().parents[2] / "database" / "seed"


def create_admin(email: str, full_name: str) -> int:
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
    min_len = get_settings().password_min_length
    if len(password) < min_len or len(password.encode()) > 72:
        print(f"Password must be {min_len}-72 bytes long.", file=sys.stderr)
        return 1
    email = email.strip().lower()
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            print(f"A user with email {email} already exists.", file=sys.stderr)
            return 1
        db.add(
            User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role="platform_admin",
                shop_id=None,
            )
        )
        db.commit()
    print(f"Created platform admin {email}")
    return 0


def seed_demo_products(db) -> None:
    """Create demo products for the demo shops (skips products whose name already exists in that shop)."""
    data = json.loads((SEED_DIR / "demo_products.json").read_text(encoding="utf-8"))
    for owner_email, products in data.items():
        if owner_email.startswith("_"):
            continue
        owner = db.scalar(select(User).where(User.email == owner_email.lower()))
        if owner is None or owner.shop_id is None:
            continue
        existing = set(db.scalars(select(Product.name).where(Product.shop_id == owner.shop_id)))
        created = 0
        new_products: list[Product] = []
        for item in products:
            if item["name"] in existing:
                continue
            product = Product(shop_id=owner.shop_id, photos=[], **item)
            db.add(product)
            db.flush()
            new_products.append(product)
            created += 1
        db.commit()
        for product in new_products:  # queue the embedding job for each new product
            product_hooks.product_changed(owner.shop_id, product.id)
        print(f"products: {created} created for {owner_email}")


def seed_demo_policies(db) -> None:
    """Create demo shop policies (skips shops that already have one)."""
    data = json.loads((SEED_DIR / "demo_policies.json").read_text(encoding="utf-8"))
    for owner_email, policy in data.items():
        if owner_email.startswith("_"):
            continue
        owner = db.scalar(select(User).where(User.email == owner_email.lower()))
        if owner is None or owner.shop_id is None:
            continue
        if db.scalar(select(ShopPolicy.id).where(ShopPolicy.shop_id == owner.shop_id)) is not None:
            print(f"policy: skip {owner_email} (already set)")
            continue
        PolicyService(db, owner.shop_id).save(PolicyIn(**policy))
        print(f"policy: created for {owner_email}")


def seed_demo_chats(db) -> None:
    """Fictional Messenger conversations, some flagged (AI paused, notification created). Skips existing ones."""
    data = json.loads((SEED_DIR / "demo_chats.json").read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    for owner_email, chats in data.items():
        if owner_email.startswith("_"):
            continue
        owner = db.scalar(select(User).where(User.email == owner_email.lower()))
        if owner is None or owner.shop_id is None:
            continue
        created = 0
        for item in chats:
            exists = db.scalar(select(Chat.id).where(Chat.shop_id == owner.shop_id, Chat.customer_psid == item["psid"]))
            if exists is not None:
                continue
            last = now - timedelta(minutes=item["minutes_ago"])
            reason = item["flag_reason"]
            chat = Chat(
                shop_id=owner.shop_id,
                channel="messenger",
                customer_psid=item["psid"],
                customer_name=item["name"],
                ai_disclosure_sent=True,
                last_customer_message_at=last,
                is_flagged=bool(reason),
                flag_reason=reason,
                flagged_at=last if reason else None,
                ai_paused=bool(reason),
            )
            db.add(chat)
            db.flush()
            for i, m in enumerate(item["messages"]):
                at = last + timedelta(seconds=i)
                db.add(
                    Message(
                        shop_id=owner.shop_id,
                        chat_id=chat.id,
                        sender=m["sender"],
                        text=m["text"],
                        received_at=at if m["sender"] == "customer" else None,
                        sent_at=at if m["sender"] != "customer" else None,
                    )
                )
            if reason:
                db.add(HandoverEvent(shop_id=owner.shop_id, chat_id=chat.id, reason=reason, created_at=last))
                db.add(
                    Notification(
                        shop_id=owner.shop_id,
                        type="chat_flagged",
                        chat_id=chat.id,
                        reason=reason,
                        created_at=last,
                        read_at=last + timedelta(minutes=1) if item["notification_read"] else None,
                    )
                )
            created += 1
        db.commit()
        print(f"chats: {created} created for {owner_email}")


def seed_demo_history(db) -> None:
    """About six weeks of fictional Messenger history (chats, AI replies, handovers, orders in every status) so the
    Reports page and the weekly AI summary can be shown. Skips chats that already exist."""
    data = json.loads((SEED_DIR / "demo_history.json").read_text(encoding="utf-8"))
    dhaka = ZoneInfo("Asia/Dhaka")
    now = datetime.now(timezone.utc)
    today = now.astimezone(dhaka).date()
    for owner_email, chats in data.items():
        if owner_email.startswith("_"):
            continue
        owner = db.scalar(select(User).where(User.email == owner_email.lower()))
        if owner is None or owner.shop_id is None:
            continue
        shop_id = owner.shop_id
        created = 0
        for item in chats:
            if db.scalar(select(Chat.id).where(Chat.shop_id == shop_id, Chat.customer_psid == item["psid"])) is not None:
                continue
            start = datetime.combine(today - timedelta(days=item["days_ago"]), time(item["hour"], 5), tzinfo=dhaka).astimezone(timezone.utc)
            start = min(start, now - timedelta(minutes=30))
            msgs = item["messages"]
            times = [start + timedelta(seconds=40 * i) for i in range(len(msgs))]
            last_customer = max(t for t, m in zip(times, msgs) if m["sender"] == "customer")
            chat = Chat(shop_id=shop_id, channel="messenger", customer_psid=item["psid"], customer_name=item["name"],
                        ai_disclosure_sent=True, last_customer_message_at=last_customer, created_at=start)
            db.add(chat)
            db.flush()
            for at, m in zip(times, msgs):
                is_customer = m["sender"] == "customer"
                db.add(Message(shop_id=shop_id, chat_id=chat.id, sender=m["sender"], text=m["text"], created_at=at,
                               received_at=at if is_customer else None, sent_at=None if is_customer else at))
            if item["handover"]:
                db.add(HandoverEvent(shop_id=shop_id, chat_id=chat.id, reason=item["handover"], created_at=times[-1]))
            o = item["order"]
            if o:
                product = db.scalar(select(Product).where(Product.shop_id == shop_id, Product.name == o["product"]))
                drafted = times[-1]
                order = Order(shop_id=shop_id, chat_id=chat.id, product_id=product.id if product else None, product_name=o["product"],
                              size=o["size"], colour=o["colour"], quantity=o["quantity"], unit_price=product.price if product else 0,
                              customer_name=o["customer_name"], customer_phone=o["customer_phone"], customer_address=o["customer_address"],
                              status=o["status"], created_at=drafted)
                if o["status"] == "confirmed":
                    order.confirmed_at = min(drafted + timedelta(hours=o["confirmed_after_hours"] or 1), now - timedelta(minutes=1))
                    order.confirmed_by_user_id = owner.id
                elif o["status"] == "cancelled":
                    order.cancelled_at = min(drafted + timedelta(hours=2), now - timedelta(minutes=1))
                db.add(order)
            created += 1
        db.commit()
        print(f"history: {created} chats created for {owner_email}")


def _reembed(shop_ids: list[int], resize_column: bool = False) -> int:
    with SessionLocal() as db:
        svc = EmbeddingService(db)
        if resize_column:
            want = get_settings().embedding_dim
            # The column holds derived data only, so it is safe to empty it before changing its size.
            db.execute(text("TRUNCATE embedding_chunks"))
            db.execute(text(f"ALTER TABLE embedding_chunks ALTER COLUMN embedding TYPE vector({int(want)})"))
            db.commit()
            print(f"embedding column resized to vector({want})")
        try:
            for shop_id in shop_ids:
                r = svc.reembed_shop(shop_id)
                print(
                    f"shop {shop_id}: {r['products']} products -> {r['product_chunks']} chunks, "
                    f"{r['policy_chunks']} policy chunks, {r['orphans_removed']} orphans removed"
                )
        except DimensionMismatch as e:
            print(str(e), file=sys.stderr)
            return 1
    return 0


def reembed_shop(shop_id: int) -> int:
    with SessionLocal() as db:
        if db.get(Shop, shop_id) is None:
            print(f"No shop with id {shop_id}", file=sys.stderr)
            return 1
    return _reembed([shop_id])


def reembed_all(resize_column: bool) -> int:
    with SessionLocal() as db:
        ids = list(db.scalars(select(Shop.id).order_by(Shop.id)))
    return _reembed(ids, resize_column)


def generate_insights(shop_id: int, week_start: str | None) -> int:
    """Generate the weekly AI summary for one shop (testing and demos). Prints the result."""
    from app.services.insights import InsightsService, monday_of, previous_week_start

    week = date.fromisoformat(week_start) if week_start else previous_week_start()
    if week != monday_of(week):
        print(f"{week} is not a Monday: use the Monday that starts the week.", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        if db.get(Shop, shop_id) is None:
            print(f"No shop with id {shop_id}.", file=sys.stderr)
            return 2
        row = InsightsService(db).generate_for_shop(shop_id, week)
        print(f"shop {shop_id}, week starting {row.week_start}")
        print("Top questions:")
        for q in row.top_questions:
            print(f"  {q['count']:>3} x {q['question']}")
        print("Products customers asked for that the shop does not have:")
        for p in row.missing_products:
            print(f"  {p['count']:>3} x {p['name']}")
    return 0


def seed() -> int:
    """Upsert the plans, create the fictional demo shops with their demo products and policies from database/seed/demo_shops.json (idempotent)."""
    demos = json.loads((SEED_DIR / "demo_shops.json").read_text(encoding="utf-8"))
    env_password = os.environ.get("DEMO_PASSWORD")
    with SessionLocal() as db:
        print(f"plans: {seed_plans(db)} upserted (placeholder values, see database/seed/plans.json)")
        free = get_plan_by_code(db, "free")
        for demo in demos:
            email = demo["owner_email"].lower()
            if db.scalar(select(User.id).where(User.email == email)) is not None:
                print(f"skip   {email} (already exists)")
                continue
            password = env_password or secrets.token_urlsafe(12)
            shop = Shop(name=demo["shop_name"], plan=free)
            db.add_all(
                [
                    shop,
                    User(
                        email=email,
                        password_hash=hash_password(password),
                        full_name=demo["owner_name"],
                        role="owner",
                        shop=shop,
                    ),
                ]
            )
            db.commit()
            if env_password:
                print(f"create {email} (password from DEMO_PASSWORD)")
            else:
                print(f"create {email}  password: {password}   (shown once)")
        seed_demo_products(db)
        seed_demo_policies(db)
        seed_demo_chats(db)
        seed_demo_history(db)
    return 0


DEMO_LOGIN_PASSWORD = "Demo@12345"
DEMO_MODERATOR_EMAIL = "mod.demo@example.com"
DEMO_ADMIN_EMAIL = "admin.demo@example.com"


def demo_accounts() -> int:
    """Local demos only: give the demo owners a known password and create a demo moderator and a demo platform admin,
    so that the login page can fill them in with one click (frontend NEXT_PUBLIC_DEMO_LOGINS=true).
    Refuses to run outside a local environment (APP_ENV)."""
    settings = get_settings()
    if not settings.is_local:
        print("demo-accounts only runs when APP_ENV is local/dev/development.", file=sys.stderr)
        return 1
    demos = json.loads((SEED_DIR / "demo_shops.json").read_text(encoding="utf-8"))
    with SessionLocal() as db:
        hashed = hash_password(DEMO_LOGIN_PASSWORD)
        first_shop_id = None
        for demo in demos:
            owner = db.scalar(select(User).where(User.email == demo["owner_email"].lower()))
            if owner is None:
                print(f"missing {demo['owner_email']}: run 'python -m app.cli seed' first", file=sys.stderr)
                return 1
            owner.password_hash = hashed
            first_shop_id = first_shop_id or owner.shop_id
        for email, name, role, shop_id in ((DEMO_MODERATOR_EMAIL, "Demo Moderator", "moderator", first_shop_id), (DEMO_ADMIN_EMAIL, "Demo Platform Admin", "platform_admin", None)):
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                db.add(User(email=email, password_hash=hashed, full_name=name, role=role, shop_id=shop_id))
            else:
                user.password_hash = hashed
        db.commit()
    print("demo accounts ready (owners, moderator, platform admin)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="ShopSathi commands")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    p_admin = sub.add_parser("create-admin", help="create a platform_admin user")
    p_admin.add_argument("--email", required=True)
    p_admin.add_argument("--full-name", default="Platform Admin")
    p_shop = sub.add_parser("reembed-shop", help="rebuild all embeddings of one shop (synchronously)")
    p_shop.add_argument("--shop-id", type=int, required=True)
    p_all = sub.add_parser("reembed-all", help="rebuild embeddings of every shop (after changing the model)")
    p_all.add_argument(
        "--resize-column",
        action="store_true",
        help="also change the vector column to EMBEDDING_DIM (empties and rebuilds all embeddings)",
    )
    p_ins = sub.add_parser("generate-insights", help="generate the weekly AI summary of one shop (uses the AI provider)")
    p_ins.add_argument("--shop-id", type=int, required=True)
    p_ins.add_argument("--week-start", help="the Monday that starts the week, YYYY-MM-DD (default: last week)")
    sub.add_parser("seed", help="create fictional demo shops and owners (idempotent)")
    sub.add_parser("demo-accounts", help="local demos: known password for the demo owners, plus a demo moderator and admin (for the login page buttons)")
    args = parser.parse_args(argv)
    if args.command == "create-admin":
        return create_admin(args.email, args.full_name)
    if args.command == "reembed-shop":
        return reembed_shop(args.shop_id)
    if args.command == "reembed-all":
        return reembed_all(args.resize_column)
    if args.command == "generate-insights":
        return generate_insights(args.shop_id, args.week_start)
    if args.command == "seed":
        return seed()
    if args.command == "demo-accounts":
        return demo_accounts()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
