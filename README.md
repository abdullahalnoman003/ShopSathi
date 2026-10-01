# ShopSathi

ShopSathi is an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh. It answers customers' questions in Messenger using each shop's own products and policies, creates order drafts, hands difficult chats over to the shop owner (human takeover), and gives owners a dashboard to manage everything, with Free/Basic/Pro plans.

## Prerequisites
Docker, Python 3.11+, Node 20+.

## Local start
1. Database + Redis:
   ```bash
   cd database
   cp .env.example .env
   docker compose up -d
   ```
   (If ports 5432/6379 are taken, change `POSTGRES_PORT`/`REDIS_PORT` in `database/.env` and the URLs in `backend/.env`.)
2. Backend:
   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate          # Windows; use: source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env            # then set JWT_SECRET (see the comment in the file)
   alembic upgrade head
   python -m app.cli seed          # optional: fictional demo shops
   uvicorn app.main:app --reload   # http://localhost:8000/api/v1/health
   ```
3. Celery worker (separate terminal, venv active; `--pool=solo` for Windows). It keeps product and policy embeddings up to date, so keep it running:
   ```bash
   celery -A app.workers.celery_app worker --loglevel=info --pool=solo
   ```
4. Frontend:
   ```bash
   cd frontend
   cp .env.example .env.local
   npm install
   npm run dev                     # http://localhost:3000
   ```

## Tests
```bash
cd backend && pytest
cd ai_engine && pytest
cd frontend && npm run lint && npm run build
```
See `docs/CONVENTIONS.md` for project conventions and `database/README.md` for resetting the demo database.
