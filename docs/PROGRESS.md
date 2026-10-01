# Progress

## Prompt 1 — Project foundation & local demo environment
**Built:** separated repo structure; `database/` (Postgres 16 + pgvector, Redis 7 via Docker Compose, init SQL creating `shopsathi_test`); backend skeleton (FastAPI, config, sync SQLAlchemy, Redis factory, Alembic with an empty initial migration, Celery with a `ping` task, `app.cli`); `ai_engine` package (settings, provider interfaces, mock providers, factory, empty `ShopDataGateway` placeholder); Next.js frontend with a typed API client and a placeholder page showing backend health.

**Tables:** none (empty initial migration). **Endpoints:** `GET /api/v1/health`. **Pages:** `/` (placeholder).

**Env vars:** see `docs/CONVENTIONS.md` and each `.env.example`.

**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.
