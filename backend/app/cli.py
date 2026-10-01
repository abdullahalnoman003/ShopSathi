"""Command entry point: python -m app.cli <command>. Later prompts add commands."""

import argparse
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Chat, HandoverEvent, Message, Notification, Product, Shop, ShopPolicy, User
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
    sub.add_parser("seed", help="create fictional demo shops and owners (idempotent)")
    args = parser.parse_args(argv)
    if args.command == "create-admin":
        return create_admin(args.email, args.full_name)
    if args.command == "reembed-shop":
        return reembed_shop(args.shop_id)
    if args.command == "reembed-all":
        return reembed_all(args.resize_column)
    if args.command == "seed":
        return seed()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
