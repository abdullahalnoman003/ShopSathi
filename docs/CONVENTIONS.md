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

## Auth & tenancy
- bcrypt password hashes; JWT (HS256) carrying user id, role, `shop_id` and a unique `jti`. Logout stores the `jti` in a Redis denylist (`jwt:deny:<jti>`) until the token expires. Rate limits use Redis fixed windows (`rl:<scope>:<key>`).
- Roles: `owner`, `moderator`, `platform_admin` (no public sign-up; create with `python -m app.cli create-admin`). Suspended shops: users get 403 `Shop suspended`.
- Dependencies in `app/api/deps.py`: `get_current_user`, `require_roles(...)`, `get_current_shop_id`. **Shop-scoped endpoints get the shop id only from `get_current_shop_id`, never from the request.**
- Shop-owned data is read/written through `app/services/tenant.py` (`ShopScopedRepository`, `scoped_select`), which always filters by `shop_id`.
- Emails go through `EmailService` (SMTP from env; with no `SMTP_HOST` it logs the email, including reset links, to the backend console).
- Frontend: token in `localStorage` (`src/lib/auth/storage.ts`), attached by `apiFetch`; a 401 clears it and redirects to `/login`. Auth state via `useAuth()` (`src/lib/auth/AuthProvider.tsx`). Auth pages live in `src/app/(auth)`, protected pages in `src/app/(dashboard)`.
- Demo/test email addresses must use a valid domain such as `example.com` (`.test` is rejected by the email validator).

## Roles & access matrix
Roles live in `app/core/roles.py` (`OWNER`, `MODERATOR`, `PLATFORM_ADMIN`). Reusable dependencies in `app/api/deps.py`: `require_owner`, `require_shop_user` (owner or moderator), built on `require_roles`. **Every later module must enforce this matrix** (backend dependency + frontend nav/`RoleGuard`):

| Area | Owner | Moderator |
|---|---|---|
| Staff accounts, plan, Facebook Page connection, shop deletion | yes | no |
| Products, CSV/Excel import, shop policy | yes | no |
| Test chat window, reports & weekly insights | yes | no |
| Chat inbox, flagged chats, pause/resume AI, manual replies | yes | yes |
| Order drafts: confirm/edit/cancel, export CSV | yes | yes |

- The platform admin uses only the admin panel endpoints (Prompt 19) and is never treated as a shop user: `require_owner` / `require_shop_user` reject it and `get_current_shop_id` gives it no shop.
- Frontend: nav items declare their `roles` in `src/app/(dashboard)/layout.tsx`; pages wrap their content in `RoleGuard` / `OwnerOnly` (`src/components/RoleGuard.tsx`) so a direct URL shows "Not allowed". Hiding in the UI is convenience only; the backend dependency is the real check.

## Products & media
- `products` is shop-owned (`shop_id` FK cascade + index). `sizes`, `colours` and `photos` are PostgreSQL `text[]` arrays (empty by default); price is `NUMERIC(10,2)` BDT, stock is an integer >= 0. The catalogue is the AI's source of truth for price, size, colour and stock.
- All product access goes through `ProductService` (a `ShopScopedRepository`). Products endpoints are owner-only; another shop's product is always a 404.
- Photos: at most 5 per product. The database keeps **storage keys** (`shops/<shop_id>/products/<uuid>.<ext>`); the API returns full URLs built from `BACKEND_PUBLIC_URL` + `/media/<key>`. `StorageService` (`app/services/storage.py`) stores files under `MEDIA_ROOT` (git-ignored), detects JPEG/PNG/WebP from the file bytes, and enforces `MAX_UPLOAD_MB`. Uploads are all-or-nothing. Deleting a product or photo deletes the files.
- **Embedding hook (Prompt 8):** `product_hooks.product_changed(shop_id, product_id)` and `product_hooks.product_deleted(shop_id, product_id)` in `app/services/products.py` are called after every create/update/photo change and after delete. They are no-ops now.

## Product import (CSV / Excel)
- `POST /api/v1/products/import` (owner only) reads `.csv` (UTF-8) or `.xlsx` with pandas/openpyxl. Columns: `name`, `description`, `price`, `sizes`, `colours`, `stock`, `photos`; only `name` and `price` are required, extra columns are ignored. Sizes/colours split on `|` or `,`; photos (http(s) URLs, max 5) split on `|`. `GET /api/v1/products/import/template` returns a template CSV.
- Row validation is the manual-product validation (`ProductImportRow` extends `ProductIn`); rows are created through `ProductService.create`, so the change hook fires for each. Do not add a second validation path.
- Row numbers in failure reports are spreadsheet row numbers (the header is row 1). Fully blank rows are ignored. Failed rows are skipped; the rest are saved (each row is its own transaction).
- Imported `photos` are stored as the given external URLs; `StorageService.url()` returns them unchanged and `delete()` never touches them. Uploaded photos still use storage keys.
- Limits: `MAX_IMPORT_MB` (default 2) and `MAX_IMPORT_ROWS` (default 1000); larger files get 413.

## Plans & message limits
- Plans (`free` / `basic` / `pro`) live in the `plans` table, seeded from `database/seed/plans.json` by `python -m app.cli seed`. **Prices and limits are placeholders (team to decide).** Every shop has a `plan_id`. Payments are simulated only (`simulated_payments`, no gateway, no card/bKash/Nagad data); paid plans need `simulated_payment_confirmed: true`.
- **Counting rule:** one count = one AI reply sent to a customer on Messenger. Test chat window messages (Prompt 9) are not counted. Counts reset per calendar month in Asia/Dhaka (`shop_message_usage`, period `YYYY-MM`).
- Use `UsageLimitService` (`app/services/usage.py`): `can_send_ai_reply` before sending, `record_ai_reply` (atomic upsert, commits) after a reply is sent, `get_usage` for display. Plan assignment goes through `app/services/plans.py` (`resolve_plan_choice`, `assign_plan`) so the admin plan change (Prompt 19) can reuse it. Not yet called from any message flow (Prompt 14 does that).

## Database
- SQLAlchemy 2.x, **sync** sessions (`get_db` dependency), migrations with Alembic in `backend/alembic/`.
- Every shop-owned table has a `shop_id` FK (`ON DELETE CASCADE`) plus an index; every query is scoped by `shop_id` (FR-02).
- Timestamps stored in UTC (timezone-aware), displayed in Asia/Dhaka.
- Embeddings (pgvector) are kept separate per shop.

## Environment variables
- Real values only in `.env` files (git-ignored); every variable is documented in the matching `.env.example` (`backend/`, `frontend/`, `database/`, `ai_engine/`). No secrets in code.
- Backend: `JWT_SECRET` (required), `ACCESS_TOKEN_EXPIRE_MINUTES`, `PASSWORD_MIN_LENGTH`, `PASSWORD_RESET_EXPIRE_MINUTES`, `LOGIN_RATE_LIMIT`/`_WINDOW_SECONDS`, `RESET_RATE_LIMIT`/`_WINDOW_SECONDS`, `SMTP_*`, `ADMIN_PASSWORD`, `DEMO_PASSWORD` (CLI), `DATABASE_URL`, `TEST_DATABASE_URL`, `REDIS_URL`, `FRONTEND_ORIGIN`, `APP_ENV`. AI: `LLM_PROVIDER`, `LLM_MODEL`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `OPENAI_API_KEY`, `GEMINI_API_KEY`. Database: `POSTGRES_*`, `REDIS_PORT`. Frontend: `NEXT_PUBLIC_API_BASE_URL`.

## Frontend
- All backend calls go through `frontend/src/lib/api/client.ts` (`apiFetch`, `ApiError`).

## Tests
- Backend: `backend/tests/` (uses the `shopsathi_test` database and Redis db 15; `conftest.py` creates/drops the schema and cleans between tests; needs the demo DB running). AI engine: `ai_engine/tests/`. Run `pytest` in each.
- Frontend: `npm run lint` and `npm run build`.

## Running everything
See the root `README.md`.
