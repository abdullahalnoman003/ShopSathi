# ShopSathi conventions

## Folder layout
```
backend/     FastAPI app (application layer + integration endpoints + Celery worker), Alembic migrations
ai_engine/   independent package "shopsathi_ai" (AI engine layer)
frontend/    Next.js (App Router) + TypeScript + Tailwind CSS
database/    local demo DB (docker-compose, init SQL, seed data)
docs/        CONVENTIONS.md, PROGRESS.md
```
Frontend route groups reserved for later prompts: `src/app/(auth)`, `src/app/(dashboard)`, `src/app/admin`. One frontend app holds the seller dashboard, admin panel and test chat window; it must work on phones and laptops (NFR-06).

## Layering
- Five layers (§5.2); each layer only talks to the adjacent one.
- **`ai_engine` never imports `backend`.** It gets shop data only through the `ShopDataGateway` protocol (`shopsathi_ai/interfaces.py`), which the backend implements. It never connects to the database. The backend is the only component that imports `shopsathi_ai`.
- LangChain may be used only inside `ai_engine`.
- `mock` AI providers are test doubles for automated tests, not AI.

## API
- Prefix `/api/v1`, JSON only. Error shape: `{"detail": ...}`.
- Module routers live in `backend/app/api/v1/routes/` and are aggregated in `api/v1/router.py`.

## Database
- SQLAlchemy 2.x, **sync** sessions (`get_db` dependency), migrations with Alembic in `backend/alembic/`.
- Every shop-owned table has a `shop_id` FK (`ON DELETE CASCADE`) plus an index; every query is scoped by `shop_id` (FR-02).
- Timestamps stored in UTC (timezone-aware), displayed in Asia/Dhaka.
- Embeddings (pgvector) are kept separate per shop.

## Environment variables
- Real values only in `.env` files (git-ignored); every variable is documented in the matching `.env.example` (`backend/`, `frontend/`, `database/`, `ai_engine/`). No secrets in code.
- Backend: `DATABASE_URL`, `TEST_DATABASE_URL`, `REDIS_URL`, `FRONTEND_ORIGIN`, `APP_ENV`. AI: `LLM_PROVIDER`, `LLM_MODEL`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `OPENAI_API_KEY`, `GEMINI_API_KEY`. Database: `POSTGRES_*`, `REDIS_PORT`. Frontend: `NEXT_PUBLIC_API_BASE_URL`.

## Frontend
- All backend calls go through `frontend/src/lib/api/client.ts` (`apiFetch`, `ApiError`).

## Tests
- Backend: `backend/tests/` (uses the `shopsathi_test` database). AI engine: `ai_engine/tests/`. Run `pytest` in each.
- Frontend: `npm run lint` and `npm run build`.

## Running everything
See the root `README.md`.
