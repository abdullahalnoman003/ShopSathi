"""Shows that semantic search finds "Red Jamdani Saree" for "lal saree" (Bangla/English mix).

Requires a REAL embedding provider (EMBEDDING_PROVIDER=openai with OPENAI_API_KEY, or local), because the
mock provider has no semantics. Rebuild the demo shop's embeddings with it first:

    python -m app.cli reembed-shop --shop-id <id>
    python scripts/check_semantic_search.py --email rina.demo@example.com
"""

import argparse
import sys

sys.path.insert(0, ".")
from shopsathi_ai.retrieval import retrieve  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.ai_adapters.factory import get_embedder  # noqa: E402
from app.ai_adapters.gateway import BackendShopDataGateway  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402

QUERIES = {"lal saree": "Red Jamdani Saree", "red saree": "Red Jamdani Saree", "panjabi": "Cotton Panjabi"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="rina.demo@example.com")
    args = ap.parse_args()
    s = get_settings()
    if s.embedding_provider == "mock":
        print("EMBEDDING_PROVIDER is 'mock': it has no semantics. Set EMBEDDING_PROVIDER=openai (and OPENAI_API_KEY) or local.")
        return 2
    embedder = get_embedder()
    ok = True
    with SessionLocal() as db:
        shop_id = db.scalar(select(User.shop_id).where(User.email == args.email))
        gateway = BackendShopDataGateway(db)
        for query, expected in QUERIES.items():
            hits = retrieve(shop_id, query, 3, embedder=embedder, gateway=gateway)
            print(f"\n'{query}' -> top {len(hits)}")
            for h in hits:
                print(f"  {h.score:.3f}  {h.content.splitlines()[0]}")
            found = bool(hits) and expected in hits[0].content
            ok &= found
            print("  OK" if found else f"  MISSING: expected '{expected}' first")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
