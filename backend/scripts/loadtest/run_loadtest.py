"""Load test of the Messenger pipeline (NFR-01: 8 s for 90% of replies; NFR-07: 20 shops and 50 chats at once).

Run from backend/ with the API, a Celery worker and the stub Send API running (see README.md):

    python -m scripts.loadtest.run_loadtest setup                  # 20 shops with products, policy, a connected fake Page
    python -m scripts.loadtest.run_loadtest run --chats 50 --messages 3 --label mock
    python -m scripts.loadtest.run_loadtest cleanup                # delete the load-test shops again

`run` sends signed webhook events (as Facebook would) for N concurrent chats, waits until every message was handled,
then measures from the database: time from `received_at` to `sent_at` of each reply (p50/p90/p99), the outcome of
every message, the Celery queue backlog (sampled while it runs) and what the stub received. Nothing here talks to
Facebook: the Page tokens are fake and the Graph base URL must point at the stub.
"""

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, ".")
from sqlalchemy import select, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.crypto import TokenCipher  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.integrations.facebook.webhook import sign  # noqa: E402
from app.models import DeliveryArea, FacebookPage, Plan, Product, Shop, ShopPolicy, User  # noqa: E402
from app.services.embeddings import EmbeddingService  # noqa: E402
from app.services.shop_deletion import ShopDeletionService  # noqa: E402

PREFIX = "LoadTest Shop"
RESULTS = Path(__file__).resolve().parent / "results"
PRODUCTS = [("Cotton Panjabi", 1850, ["M", "L", "XL"], ["White", "Navy"]), ("Wireless Earbuds", 1450, [], ["Black", "White"]), ("Red Jamdani Saree", 4800, [], ["Red"])]
AREAS = [("Inside Dhaka", 60), ("Khagan", 100), ("Chattogram", 130)]
#: what customers write, in the three styles; {p} is a product of the shop. Each chat sends the first N of its own shuffled list
QUESTIONS = [
    "{p} er dam koto?", "What is the price of the {p}?", "{p} ache? stock e ki ache?", "Do you have {p} in stock?",
    "Khagan e delivery charge koto?", "How much is delivery to Chattogram?", "return policy ki?", "{p} dekhao, 2000 er moddhe",
    "দাম কত {p}?", "ডেলিভারি চার্জ কত ঢাকায়?", "{p} নিব, সাইজ কি কি আছে?", "Cash on delivery ache?",
]


#: questions the offline mock model answers without handing the chat to a person (a flagged chat pauses the AI, which would
#: make the mock run measure nothing). A real model gets the varied list above.
SIMPLE_QUESTIONS = ["{p} er dam koto?", "What is the price of the {p}?", "{p} price koto?", "{p} er price koto?", "{p} dam koto bolen", "Price of {p}?"]


# --------------------------------------------------------------------------- setup


def shop_names(n: int) -> list[str]:
    return [f"{PREFIX} {i:02d}" for i in range(1, n + 1)]


def setup(n_shops: int, plan_code: str = "pro", monthly_limit: int | None = None) -> list[dict[str, Any]]:
    """Create (or reuse) n load-test shops. Direct database inserts, embeddings made synchronously: no worker needed."""
    cipher = TokenCipher()
    out: list[dict[str, Any]] = []
    with SessionLocal() as db:
        plan = db.scalar(select(Plan).where(Plan.code == plan_code))
        if plan is None:
            raise SystemExit(f"Plan '{plan_code}' is missing: run 'python -m app.cli seed' first.")
        if monthly_limit is not None:
            plan.monthly_message_limit = monthly_limit
            db.commit()
        for i, name in enumerate(shop_names(n_shops), start=1):
            shop = db.scalar(select(Shop).where(Shop.name == name))
            if shop is None:
                shop = Shop(name=name, plan=plan)
                db.add(shop)
                db.flush()
                db.add(User(email=f"loadtest{i:02d}@loadtest.example", password_hash=hash_password("load-test-not-a-real-password"), full_name=f"Load Owner {i}", role="owner", shop=shop))
                for pname, price, sizes, colours in PRODUCTS:
                    db.add(Product(shop_id=shop.id, name=pname, description=f"{pname} of {name}", price=price, sizes=sizes, colours=colours, stock_count=50))
                db.add(ShopPolicy(shop_id=shop.id, delivery_time="Inside Dhaka 1-2 days, outside Dhaka 3-5 days", return_rules="Return within 3 days if damaged", payment_options="Cash on delivery and bKash"))
                for area, charge in AREAS:
                    db.add(DeliveryArea(shop_id=shop.id, area_name=area, charge=charge))
                db.add(FacebookPage(shop_id=shop.id, page_id=f"load-page-{i:02d}", page_name=f"Load Page {i}", encrypted_page_token=cipher.encrypt(f"LOADTEST-TOKEN-{i:02d}")))
                db.commit()
                svc = EmbeddingService(db)
                for p in db.scalars(select(Product).where(Product.shop_id == shop.id)):
                    svc.embed_product(shop.id, p.id)
                svc.embed_policy(shop.id)
            page = db.scalar(select(FacebookPage.page_id).where(FacebookPage.shop_id == shop.id))
            names = list(db.scalars(select(Product.name).where(Product.shop_id == shop.id).order_by(Product.id)))
            out.append({"shop_id": shop.id, "name": name, "page_id": page, "products": names})
    return out


def existing_shops() -> list[dict[str, Any]]:
    with SessionLocal() as db:
        out = []
        for shop in db.scalars(select(Shop).where(Shop.name.like(f"{PREFIX} %")).order_by(Shop.name)):
            page = db.scalar(select(FacebookPage.page_id).where(FacebookPage.shop_id == shop.id))
            names = list(db.scalars(select(Product.name).where(Product.shop_id == shop.id).order_by(Product.id)))
            out.append({"shop_id": shop.id, "name": shop.name, "page_id": page, "products": names})
        return out


def cleanup() -> int:
    n = 0
    with SessionLocal() as db:
        ids = list(db.scalars(select(Shop.id).where(Shop.name.like(f"{PREFIX} %"))))
    for shop_id in ids:
        with SessionLocal() as db:
            ShopDeletionService(db).delete_shop(shop_id)
            n += 1
    return n


# --------------------------------------------------------------------------- the run


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def summary(values: list[float]) -> dict[str, float | int | None]:
    return {"n": len(values), "p50": percentile(values, 50), "p90": percentile(values, 90), "p99": percentile(values, 99), "max": max(values) if values else None,
            "mean": statistics.fmean(values) if values else None}


def event(page_id: str, psid: str, mid: str, text_: str, ts_ms: int | None = None) -> bytes:
    ts = ts_ms or int(time.time() * 1000)
    body = {"object": "page", "entry": [{"id": page_id, "time": ts, "messaging": [{"sender": {"id": psid}, "recipient": {"id": page_id}, "timestamp": ts, "message": {"mid": mid, "text": text_}}]}]}
    return json.dumps(body, ensure_ascii=False).encode()


async def one_chat(client: httpx.AsyncClient, api: str, secret: str, shop: dict, k: int, run_id: str, n_messages: int, interval: float, rng: random.Random, webhook_ms: list[float], errors: list[str], pool: list[str]) -> None:
    psid = f"load-{run_id}-{k:03d}"
    qs = [q.format(p=rng.choice(shop["products"])) for q in rng.sample(pool, n_messages)]
    await asyncio.sleep(rng.random() * 0.5)  # chats do not all start in the same millisecond
    for j, q in enumerate(qs):
        body = event(shop["page_id"], psid, f"m_load_{run_id}_{k:03d}_{j}", q)
        started = time.perf_counter()
        try:
            r = await client.post(f"{api}/api/v1/webhooks/messenger", content=body, headers={"X-Hub-Signature-256": sign(secret, body), "Content-Type": "application/json"})
            webhook_ms.append((time.perf_counter() - started) * 1000)
            if r.status_code != 200:
                errors.append(f"webhook {r.status_code} for chat {k}")
        except httpx.HTTPError as e:
            errors.append(f"webhook {e.__class__.__name__} for chat {k}")
        if j < len(qs) - 1:
            await asyncio.sleep(interval)


async def sample_queue(stop: asyncio.Event, samples: list[tuple[float, int]], t0: float) -> None:
    redis = get_redis()
    while not stop.is_set():
        try:
            samples.append((time.perf_counter() - t0, int(redis.llen("celery"))))
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.25)
        except asyncio.TimeoutError:
            pass


def collect(run_id: str) -> dict[str, Any]:
    """Outcome and latency of every message of this run, from the database."""
    like = f"m_load_{run_id}_%"
    with SessionLocal() as db:
        rows = db.execute(
            text(
                """
                select c.id, c.extras->>'ai_status', c.extras->>'ai_skip_reason', a.sent_at is not null,
                       extract(epoch from (a.sent_at - c.received_at)) * 1000,
                       (a.extras->'delivery'->'timings_ms'->>'queue')::float, (a.extras->'delivery'->'timings_ms'->>'ai')::float,
                       (a.extras->'delivery'->'timings_ms'->>'send')::float, c.shop_id
                from messages c left join messages a on a.sender = 'ai' and a.extras->>'in_reply_to' = c.id::text
                where c.sender = 'customer' and c.external_message_id like :like
                """
            ),
            {"like": like},
        ).all()
    status: dict[str, int] = {}
    total, queue, ai, send = [], [], [], []
    with SessionLocal() as db:
        chats_total = db.scalar(text("select count(distinct chat_id) from messages where sender = 'customer' and external_message_id like :like"), {"like": like}) or 0
        chats_replied = db.scalar(
            text("select count(distinct a.chat_id) from messages a join messages c on a.extras->>'in_reply_to' = c.id::text where a.sender = 'ai' and a.sent_at is not null and c.external_message_id like :like"),
            {"like": like},
        ) or 0
    for _, st, reason, sent, ms, q, a, s, _shop in rows:
        key = st or "missing" if st != "skipped" else f"skipped:{reason}"
        status[key] = status.get(key, 0) + 1
        if sent and ms is not None:
            total.append(float(ms))
            queue.append(q or 0)
            ai.append(a or 0)
            send.append(s or 0)
    return {"messages": len(rows), "chats": chats_total, "chats_replied": chats_replied, "status": status, "replies_sent": len(total), "total_ms": summary(total), "queue_ms": summary(queue), "ai_ms": summary(ai), "send_ms": summary(send)}


async def run(args: argparse.Namespace) -> dict[str, Any]:
    shops = existing_shops()
    if len(shops) < args.shops:
        raise SystemExit(f"Only {len(shops)} load-test shops exist: run 'setup --shops {args.shops}' first.")
    shops = shops[: args.shops]
    s = get_settings()
    run_id = datetime.now().strftime("%H%M%S") + f"{random.randrange(100):02d}"
    rng = random.Random(args.seed)
    pool = SIMPLE_QUESTIONS if (args.questions == "simple" or (args.questions == "auto" and s.llm_provider == "mock")) else QUESTIONS
    stub = args.stub.rstrip("/")
    async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=200)) as client:
        try:
            await client.post(f"{stub}/_reset")
        except httpx.HTTPError:
            raise SystemExit(f"The stub Send API is not running at {stub} (see README.md).")
        r = await client.get(f"{args.api}/api/v1/health")
        if r.status_code != 200:
            raise SystemExit(f"The API at {args.api} is not healthy.")
        get_redis().delete("celery")  # no old jobs
        print(f"run {run_id}: {args.chats} concurrent chats on {len(shops)} shops, {args.messages} messages each, every {args.interval}s ...")
        webhook_ms: list[float] = []
        errors: list[str] = []
        samples: list[tuple[float, int]] = []
        stop = asyncio.Event()
        t0 = time.perf_counter()
        sampler = asyncio.create_task(sample_queue(stop, samples, t0))
        chats = [one_chat(client, args.api, s.fb_app_secret, shops[k % len(shops)], k, run_id, args.messages, args.interval, rng, webhook_ms, errors, pool) for k in range(args.chats)]
        await asyncio.gather(*chats)
        sent_all = time.perf_counter() - t0
        expected = args.chats * args.messages
        deadline = time.perf_counter() + args.timeout
        while time.perf_counter() < deadline:
            with SessionLocal() as db:
                pending = db.scalar(text("select count(*) from messages where external_message_id like :l and sender='customer' and (extras->>'ai_status' = 'pending' or extras->>'ai_status' is null)"), {"l": f"m_load_{run_id}_%"}) or 0
                seen = db.scalar(text("select count(*) from messages where external_message_id like :l and sender='customer'"), {"l": f"m_load_{run_id}_%"}) or 0
            if seen >= expected - len(errors) and pending == 0:
                break
            await asyncio.sleep(0.5)
        drained = time.perf_counter() - t0
        stop.set()
        await sampler
        stub_stats = (await client.get(f"{stub}/_stats")).json()
    result = collect(run_id)
    backlog = [q for _, q in samples]
    timed_out = pending != 0
    out = {
        "run_id": run_id, "label": args.label, "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {"shops": len(shops), "chats": args.chats, "messages_per_chat": args.messages, "interval_s": args.interval, "questions": "simple" if pool is SIMPLE_QUESTIONS else "varied", "expected_messages": expected,
                   "llm_provider": s.llm_provider, "llm_model": s.llm_model, "embedding_provider": s.embedding_provider},
        "webhook_ms": summary(webhook_ms), "webhook_errors": errors[:20], "webhook_error_count": len(errors),
        "seconds_to_send_all": round(sent_all, 2), "seconds_until_all_handled": round(drained, 2), "timed_out": timed_out,
        "queue_backlog": {"max": max(backlog, default=0), "mean": round(statistics.fmean(backlog), 2) if backlog else 0, "samples": len(backlog)},
        "result": result, "stub": stub_stats,
        "nfr01_p90_under_8s": (result["total_ms"]["p90"] is not None and result["total_ms"]["p90"] <= 8000 and not timed_out),
        # every chat got an answer, nothing failed, nothing was left waiting (a chat paused after a flag is a normal outcome)
        "nfr07_all_chats_served": (result["chats_replied"] == args.chats and not errors and not timed_out and not any(k in ("failed", "pending", "missing") or k.startswith("skipped:") and k != "skipped:ai_paused" for k in result["status"])),
    }
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"loadtest_{args.label}_{run_id}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print_summary(out)
    print(f"saved: {path}")
    return out


def ms(v: float | None) -> str:
    return "-" if v is None else f"{v:,.0f}"


def print_summary(o: dict[str, Any]) -> None:
    r, c = o["result"], o["config"]
    print(f"\n== {o['label']}: {c['llm_provider']}/{c['llm_model']}, {c['chats']} chats x {c['messages_per_chat']} messages on {c['shops']} shops ==")
    print(f"webhook answer (ms)   p50 {ms(o['webhook_ms']['p50'])}  p90 {ms(o['webhook_ms']['p90'])}  p99 {ms(o['webhook_ms']['p99'])}  errors {o['webhook_error_count']}")
    t = r["total_ms"]
    print(f"received->sent (ms)   p50 {ms(t['p50'])}  p90 {ms(t['p90'])}  p99 {ms(t['p99'])}  max {ms(t['max'])}   (n={t['n']})")
    for k in ("queue_ms", "ai_ms", "send_ms"):
        v = r[k]
        print(f"  {k[:-3]:<6} (ms)        p50 {ms(v['p50'])}  p90 {ms(v['p90'])}  p99 {ms(v['p99'])}")
    print(f"messages {r['messages']}/{c['expected_messages']}  replies sent {r['replies_sent']}  chats answered {r['chats_replied']}/{c['chats']}  outcomes {r['status']}")
    print(f"queue backlog max {o['queue_backlog']['max']} (mean {o['queue_backlog']['mean']}); all sent in {o['seconds_to_send_all']}s, all handled after {o['seconds_until_all_handled']}s{'  TIMED OUT' if o['timed_out'] else ''}")
    print(f"stub received {o['stub']['sends']} sends ({o['stub']['texts']} text, {o['stub']['images']} image) for {o['stub']['recipients']} customers on {o['stub']['pages']} pages")
    print(f"NFR-01 (p90 <= 8 s): {'PASS' if o['nfr01_p90_under_8s'] else 'FAIL'}   NFR-07 (20 shops / 50 chats all served): {'PASS' if o['nfr07_all_chats_served'] else 'FAIL'}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("setup", help="create the load-test shops")
    p.add_argument("--shops", type=int, default=20)
    p.add_argument("--plan", default="pro")
    p.add_argument("--limit", type=int, default=None, help="set the plan's monthly message limit (e.g. to try FR-15 under load)")
    sub.add_parser("cleanup", help="delete the load-test shops and all their data")
    r = sub.add_parser("run", help="send the load")
    r.add_argument("--api", default="http://localhost:8001")
    r.add_argument("--stub", default="http://localhost:8098")
    r.add_argument("--shops", type=int, default=20)
    r.add_argument("--chats", type=int, default=50)
    r.add_argument("--messages", type=int, default=3, help="messages per chat")
    r.add_argument("--interval", type=float, default=4.0, help="seconds between a chat's messages")
    r.add_argument("--timeout", type=float, default=240.0, help="seconds to wait for all messages to be handled")
    r.add_argument("--questions", choices=["auto", "simple", "varied"], default="auto", help="auto: simple for the mock model, varied for a real one")
    r.add_argument("--label", default="run")
    r.add_argument("--seed", type=int, default=7)
    r.add_argument("--yes-spend", action="store_true", help="allow more than 150 messages with a real (paid) LLM")
    args = ap.parse_args()

    if args.cmd == "setup":
        shops = setup(args.shops, args.plan, args.limit)
        print(f"{len(shops)} load-test shops ready (pages load-page-01 ...).")
        return 0
    if args.cmd == "cleanup":
        print(f"deleted {cleanup()} load-test shops")
        return 0
    s = get_settings()
    if s.llm_provider != "mock" and args.chats * args.messages > 150 and not args.yes_spend:
        print(f"{s.llm_provider} is a paid model: {args.chats * args.messages} messages is more than 150. Use fewer, or --yes-spend.", file=sys.stderr)
        return 2
    if "localhost:8098" not in s.fb_graph_base_url and "127.0.0.1:8098" not in s.fb_graph_base_url and not s.fb_graph_base_url.startswith("http://localhost"):
        print(f"FB_GRAPH_BASE_URL is {s.fb_graph_base_url}: load tests must only talk to the stub (set FB_GRAPH_BASE_URL=http://localhost:8098).", file=sys.stderr)
        return 2
    asyncio.run(run(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
