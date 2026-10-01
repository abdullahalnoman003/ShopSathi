# ShopSathi backend

```bash
python -m venv .venv && .venv\Scripts\activate     # Windows (source .venv/bin/activate elsewhere)
pip install -r requirements.txt                     # also installs ../ai_engine in editable mode
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload                       # http://localhost:8000/api/v1/health
celery -A app.workers.celery_app worker --loglevel=info --pool=solo   # --pool=solo is needed on Windows
pytest
python -m app.cli --help
python -m app.cli reembed-all                       # (re)build all embeddings; needs no worker
```

AI checks (see docs/PROGRESS.md): `python scripts/check_chat_examples.py` (proposal example messages and reply time), `python scripts/check_semantic_search.py`, `python scripts/check_embedding_latency.py`.
