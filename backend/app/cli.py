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
from app.models import Shop, User
from app.services.plans import get_plan_by_code, seed_plans

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


def seed() -> int:
    """Upsert the plans, then create the fictional demo shops from database/seed/demo_shops.json (idempotent)."""
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
