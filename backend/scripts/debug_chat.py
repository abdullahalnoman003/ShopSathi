"""Developer helper: run messages through the pipeline and print what the AI understood and found.

    python scripts/debug_chat.py "Cotton Panjabi XL ache?" "eta ki XL e pawa jabe?" "লাল শাড়ির দাম কত?"

Messages go into one throw-away test chat of the demo shop (deleted afterwards).
"""

import argparse
import sys

sys.path.insert(0, ".")
from sqlalchemy import delete, select  # noqa: E402

from app.ai_adapters.factory import get_embedder  # noqa: E402
from app.ai_adapters.gateway import BackendShopDataGateway  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models import Chat, User  # noqa: E402
from app.services.conversation import ConversationService  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("messages", nargs="+")
    ap.add_argument("--email", default="rina.demo@example.com")
    args = ap.parse_args()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email))
        chat = Chat(shop_id=user.shop_id, channel="test", customer_name="Debug", created_by_user_id=user.id)
        db.add(chat)
        db.commit()
        service = ConversationService(db)
        gateway, embedder = BackendShopDataGateway(db), get_embedder()
        for message in args.messages:
            r = service.handle_customer_message(chat, message).engine_result
            print(f"> {message}")
            print(f"  intent={r.intent} ({r.confidence}) style={r.language_style} entities={r.entities}")
            print(f"  handover={r.handover.needed}({r.handover.reason}) tools={[(t['name'], t['result']) for t in r.extras['tools']]}")
            vec = embedder.embed_with_usage([message], is_query=True).vectors[0]
            hits = gateway.vector_search(user.shop_id, vec, 4)
            print("  retrieval scores:", [(round(h.score, 3), h.content.splitlines()[0][:40]) for h in hits])
            if "suggested_products" in r.extras:
                print("  needs:", r.extras.get("needs"))
                print("  cards:", [(c["name"], c["price"], bool(c["photo"])) for c in r.extras["suggested_products"]])
            print(f"  reply: {r.reply_text.split(chr(10))[-1]!r}\n")
        db.execute(delete(Chat).where(Chat.id == chat.id))
        db.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
