"""Runs the proposal's example customer messages against a seeded demo shop and prints each reply with its
time (NFR-01 target: a reply within 8 seconds).

With LLM_PROVIDER=mock this only proves the plumbing (the mock is a keyword test double). To judge real
quality set LLM_PROVIDER=openai (OPENAI_API_KEY) or gemini (GEMINI_API_KEY), EMBEDDING_PROVIDER=openai or local,
rebuild the shop's embeddings (python -m app.cli reembed-shop --shop-id N), then:

    python scripts/check_chat_examples.py --email rina.demo@example.com

The conversation is stored as a test chat of that shop and deleted afterwards (use --keep to keep it).
"""

import argparse
import sys
import time

sys.path.insert(0, ".")
from sqlalchemy import delete, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models import Chat, User  # noqa: E402
from app.services.conversation import ConversationService  # noqa: E402

# (message, what a correct answer must contain / do)
EXAMPLES = [
    ("Red Jamdani Saree price koto?", "price 4800"),
    ("price koto?", "price of the product just discussed (from memory)"),
    ("Cotton Panjabi XL ache?", "XL offered, stock 24"),
    ("eta ki XL e pawa jabe?", "still the panjabi (from memory)"),
    ("XL size ache?", "still the panjabi"),
    ("Khagan e delivery charge koto?", "delivery charge 100"),
    ("লাল শাড়ির দাম কত?", "reply in Bangla script, price 4800"),
    ("Do you sell laptops?", "I'll check with the shop"),
    ("Matte Lipstick ache?", "out of stock"),
]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # Bangla output on Windows consoles
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="rina.demo@example.com")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    s = get_settings()
    print(f"LLM_PROVIDER={s.llm_provider} LLM_MODEL={s.llm_model} EMBEDDING_PROVIDER={s.embedding_provider}")
    if s.llm_provider == "mock":
        print("NOTE: mock = rule-based test double. Replies below prove the plumbing, not AI quality.\n")

    slowest = 0.0
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email))
        chat = Chat(shop_id=user.shop_id, channel="test", customer_name="Test customer", created_by_user_id=user.id)
        db.add(chat)
        db.commit()
        service = ConversationService(db)
        for message, expect in EXAMPLES:
            t0 = time.perf_counter()
            result = service.handle_customer_message(chat, message)
            took = time.perf_counter() - t0
            slowest = max(slowest, took)
            r = result.engine_result
            print(f"> {message}   [expect: {expect}]")
            print(f"  intent={r.intent} style={r.language_style} handover={r.handover.needed}({r.handover.reason})  {took:.2f}s")
            print(f"  {result.ai_message.text!r}\n")
        if not args.keep:
            db.execute(delete(Chat).where(Chat.id == chat.id))
            db.commit()
    print(f"slowest reply: {slowest:.2f}s -> {'within' if slowest <= 8 else 'OVER'} the 8-second target (NFR-01)")
    return 0 if slowest <= 8 else 1


if __name__ == "__main__":
    sys.exit(main())
