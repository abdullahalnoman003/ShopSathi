"""Command entry point: python -m app.cli <command>. Later prompts add commands."""

import argparse
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Product, Shop, ShopPolicy, User
from app.schemas.policy import PolicyIn
from app.services.plans import get_plan_by_code, seed_plans
from app.services.policy import PolicyService

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
        for item in products:
            if item["name"] in existing:
                continue
            db.add(Product(shop_id=owner.shop_id, photos=[], **item))
            created += 1
        db.commit()
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
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="ShopSathi commands")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    p_admin = sub.add_parser("create-admin", help="create a platform_admin user")
    p_admin.add_argument("--email", required=True)
    p_admin.add_argument("--full-name", default="Platform Admin")
    sub.add_parser("seed", help="create fictional demo shops and owners (idempotent)")
    args = parser.parse_args(argv)
    if args.command == "create-admin":
        return create_admin(args.email, args.full_name)
    if args.command == "seed":
        return seed()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
