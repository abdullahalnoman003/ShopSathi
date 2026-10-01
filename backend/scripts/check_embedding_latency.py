"""AI-R13 check: edit a product through the API and time how long until its embedding is updated.

Needs the API, the Celery worker, Redis and Postgres running, and the demo data (python -m app.cli seed).

    python scripts/check_embedding_latency.py --api http://localhost:8000 --email rina.demo@example.com --password ...
"""

import argparse
import sys
import time

import httpx
from sqlalchemy import select

sys.path.insert(0, ".")
from app.core.database import SessionLocal  # noqa: E402
from app.models import EmbeddingChunk  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--limit-seconds", type=float, default=60.0)
    args = ap.parse_args()

    client = httpx.Client(base_url=f"{args.api}/api/v1", timeout=15)
    token = client.post("/auth/login", json={"email": args.email, "password": args.password}).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    product = client.get("/products", params={"page_size": 1}).json()["items"][0]

    marker = f"{int(time.time()) % 100000}"
    payload = {k: product[k] for k in ("name", "description", "price", "sizes", "colours", "stock_count")}
    payload["description"] = f"Latency check {marker}. " + product["description"].split(". ", 1)[-1]

    started = time.perf_counter()
    r = client.put(f"/products/{product['id']}", json=payload)
    r.raise_for_status()
    api_done = time.perf_counter() - started

    while True:
        with SessionLocal() as db:
            contents = list(
                db.scalars(
                    select(EmbeddingChunk.content).where(
                        EmbeddingChunk.source_type == "product", EmbeddingChunk.source_id == product["id"]
                    )
                )
            )
        if any(f"Latency check {marker}" in c for c in contents):
            elapsed = time.perf_counter() - started
            break
        if time.perf_counter() - started > args.limit_seconds:
            print(f"FAIL: embedding not updated within {args.limit_seconds:.0f}s (is the Celery worker running?)")
            return 1
        time.sleep(0.1)

    print(f"product {product['id']} '{product['name']}': API answered in {api_done:.2f}s, embedding updated {elapsed:.2f}s after the edit")
    print("PASS (< 60 s, AI-R13)" if elapsed < 60 else "FAIL (>= 60 s)")
    return 0 if elapsed < 60 else 1


if __name__ == "__main__":
    sys.exit(main())
