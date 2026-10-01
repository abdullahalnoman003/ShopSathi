# Load test (NFR-01 and NFR-07)

Sends signed Messenger webhook events for many chats at the same moment and measures how long the AI takes to answer.
**It never talks to Facebook**: replies go to `stub_send_api.py`, a tiny local server that plays the Send API.

| What | Target (proposal) |
|---|---|
| NFR-01 | an AI reply within 8 seconds for 90% of messages (time from `received_at` to `sent_at`) |
| NFR-07 | at least 20 shops and 50 chats at the same time |

## Run it (from `backend/`)

Four processes, each in its own terminal. On Windows use `127.0.0.1` rather than `localhost` for the stub: `localhost` tries
IPv6 first and adds about 2 seconds to every new connection.

```bash
# 1. the stand-in for Facebook's Send API (STUB_LATENCY_MS is how long Facebook "takes", default 150)
uvicorn scripts.loadtest.stub_send_api:app --port 8098

# 2. the API (it stores the message and queues the AI work)
uvicorn app.main:app --port 8001

# 3. the worker, pointed at the stub. Use a THREAD pool: the default 'solo' pool handles one message at a time.
#    The pool size must be at least the number of threads (an AI reply holds a database connection while it waits).
FB_GRAPH_BASE_URL=http://127.0.0.1:8098 DB_POOL_SIZE=30 DB_MAX_OVERFLOW=30 \
  celery -A app.workers.celery_app worker --pool=threads --concurrency=50 --loglevel=warning

# 4. the load
export FB_GRAPH_BASE_URL=http://127.0.0.1:8098
python -m scripts.loadtest.run_loadtest setup                      # 20 shops with products, policy, a connected fake Page
python -m scripts.loadtest.run_loadtest run --chats 50 --messages 3 --label mock
python -m scripts.loadtest.run_loadtest cleanup                    # delete the load-test shops again
```

* **Mock model** (system overhead): start the worker, `setup` and `run` with `LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock`.
* **Real model** (the true NFR-01 check): leave the provider settings from `backend/.env` (`openai`). Run `cleanup` and `setup` first so the shops' embeddings are real. Keep it small: 50 chats x 2 messages is about 100 messages and costs a few cents; the script refuses more than 150 messages with a paid model unless you add `--yes-spend`.
* `run` options: `--chats` (concurrent chats, default 50), `--messages` (per chat), `--interval` (seconds between a chat's messages), `--shops`, `--questions simple|varied|auto`, `--timeout`, `--seed`, `--label`.
* The script refuses to run unless `FB_GRAPH_BASE_URL` points at the stub. The Page tokens it creates are fake.

## What it prints (and saves to `results/*.json`)

* webhook answer time (p50/p90/p99) and webhook errors;
* **received -> sent** per reply (p50/p90/p99/max), split into queue (waiting for a worker), AI and send time;
* the outcome of every message (`replied`, `skipped:ai_paused` after a chat was handed to a person, `failed`, `pending`);
* the Celery queue backlog, sampled four times a second (max and mean), and when everything was handled;
* what the stub received, so replies sent can be compared with replies stored;
* `NFR-01` (p90 <= 8 s) and `NFR-07` (every chat answered, nothing failed or left waiting) as PASS/FAIL.

The mock model answers only simple price questions without handing the chat to a person, so `--questions auto` uses a simple
list for it and a varied one (price, stock, delivery, return policy, Banglish/English/Bangla) for a real model.
The results of the runs made for the report are in `docs/TEST_REPORT.md`.
