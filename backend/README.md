# ShopSathi backend

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows (source .venv/bin/activate elsewhere)
pip install -r requirements.txt                     # also installs ../ai_engine in editable mode
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload                       # http://localhost:8000/api/v1/health
celery -A app.workers.celery_app worker --loglevel=info --pool=solo   # --pool=solo is needed on Windows (one message at a time)
# for many chats at once use threads, and size the database pool to match (see docs/TEST_REPORT.md):
#   DB_POOL_SIZE=30 DB_MAX_OVERFLOW=30 celery -A app.workers.celery_app worker --pool=threads --concurrency=50
celery -A app.workers.celery_app beat --loglevel=info                    # the weekly AI summary (Monday 02:00 Dhaka); keep it running next to the worker
pytest
python -m app.cli --help
python -m app.cli reembed-all                       # (re)build all embeddings; needs no worker
```

AI checks (see docs/PROGRESS.md): `python scripts/check_chat_examples.py` (proposal example messages and reply time), `python scripts/check_semantic_search.py`, `python scripts/check_embedding_latency.py`.

Local demo of the Facebook Page connection without a Meta app: `uvicorn --app-dir scripts fake_facebook:app --port 8099` (see the header of `scripts/fake_facebook.py` for the backend settings to use).
Weekly AI summary by hand (uses the AI provider): `python -m app.cli generate-insights --shop-id 3 --week-start 2026-09-21` (the Monday that starts the week; default: last week).
Try the Messenger webhook locally (needs the API, a Celery worker and the fake Facebook): `python scripts/simulate_messenger_event.py --page-id <connected page id> --text "Saree er dam koto?"`; replies show at `http://localhost:8099/_debug/messages`.

Load test (NFR-01/NFR-07) with a stub instead of Facebook: `scripts/loadtest/README.md`. Security tests: `pytest tests/security`. Results: `docs/TEST_REPORT.md`.
