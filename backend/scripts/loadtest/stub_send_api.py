"""A tiny stand-in for Facebook's Graph API, FOR LOAD TESTS ONLY (no real Facebook call is ever made).

    uvicorn scripts.loadtest.stub_send_api:app --port 8098        (run from backend/)

and start the API and the Celery worker with  FB_GRAPH_BASE_URL=http://localhost:8098

It accepts a message from any Page token, answers like the Send API (after STUB_LATENCY_MS, default 150 ms, about what
Facebook takes) and counts what it received. GET /_stats shows the counts, POST /_reset clears them. It answers the
customer profile lookup and the subscription calls too. It does NOT check windows or tokens: the AI side does.
"""

import asyncio
import os
import time
from collections import Counter

from fastapi import FastAPI, Request

app = FastAPI(title="Stub Send API (load tests only)")
LATENCY = float(os.environ.get("STUB_LATENCY_MS", "150")) / 1000
state = {"sends": 0, "texts": 0, "images": 0, "profiles": 0, "unsubscribes": 0, "started": time.time()}
by_recipient: Counter[str] = Counter()
by_token: Counter[str] = Counter()


@app.post("/{version}/me/messages")
async def send_api(version: str, request: Request):
    body = await request.json()
    if LATENCY:
        await asyncio.sleep(LATENCY)
    recipient = str(body.get("recipient", {}).get("id", ""))
    message = body.get("message", {})
    state["sends"] += 1
    state["images" if "attachment" in message else "texts"] += 1
    by_recipient[recipient] += 1
    token = (request.headers.get("authorization") or "")[-12:]  # only a short tail, enough to tell Pages apart
    by_token[token] += 1
    return {"recipient_id": recipient, "message_id": f"m_stub_{state['sends']}"}


@app.get("/_stats")
def stats():
    return {**state, "recipients": len(by_recipient), "pages": len(by_token), "max_per_recipient": max(by_recipient.values(), default=0), "latency_ms": LATENCY * 1000}


@app.get("/_recipients")
def recipients():
    return dict(by_recipient)


@app.post("/_reset")
def reset():
    for k in ("sends", "texts", "images", "profiles", "unsubscribes"):
        state[k] = 0
    by_recipient.clear()
    by_token.clear()
    return {"ok": True}


@app.get("/{version}/{psid}")
async def profile(version: str, psid: str):
    state["profiles"] += 1
    return {"id": psid, "first_name": "Load", "last_name": f"Customer {psid[-4:]}"}


@app.delete("/{version}/{page_id}/subscribed_apps")
async def unsubscribe(version: str, page_id: str):
    state["unsubscribes"] += 1
    return {"success": True}
