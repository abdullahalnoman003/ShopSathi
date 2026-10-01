# ShopSathi — Development Prompts

Source of truth: *ShopSathi: An AI Sales Agent for Facebook Shops* (SE-331 Project Proposal). Every requirement below is traced to a proposal ID (FR-xx, AI-Rxx, NFR-xx, AI-1…AI-6, Scope, §5.3, etc.).

**How to use:** run the prompts in order, one per session with your AI coding assistant. Review the changes and commit them yourself after each prompt, then start the next one.

**Decisions this pack makes where the proposal leaves a choice open.** These are implementation choices only, not new features. Prompt 1 writes them into `docs/CONVENTIONS.md`.

| Proposal says | This pack fixes it as | Why |
|---|---|---|
| "Celery or FastAPI background tasks, with Redis" | Celery with a Redis broker | Covers both the queue (incoming messages) and periodic jobs (weekly summary). |
| "LangChain or LlamaIndex" | LangChain, used only inside `ai_engine/` | It's the first option listed, and it supports tool calling and structured output. |
| "GPT-4o-mini or Gemini Flash"; "text-embedding-3-small or bge-m3 / multilingual-e5" | Chosen through environment variables, behind a provider interface | Either provider works; you don't need to change code. |
| Plan prices and message-limit numbers are not given | Editable seed values, marked "placeholder – team to decide" | No numbers get invented as requirements. |
| "Separate AI engine layer" (§5.2) | `ai_engine/` is its own Python package and never imports from `backend/` | Keeps the AI layer independent, as the five-layer architecture requires. |

---

## Part 1 — Project Development Roadmap

| # | Module / task | Purpose | Layers | Depends on | Why at this stage |
|---|---|---|---|---|---|
| 1 | Project foundation & local demo environment | Create the separated folders (`backend/`, `ai_engine/`, `frontend/`, `database/`, `docs/`), the local PostgreSQL+pgvector+Redis setup, app skeletons and the conventions file | Backend + AI-engine skeleton + DB + Frontend skeleton | — | Every later prompt builds on this structure. |
| 2 | Shop sign-up, login/logout, password reset & multi-tenant separation | FR-01, FR-02, NFR-03 (hashing), NFR-04 base; shop owner and platform admin roles; shop status | Backend → Frontend | 1 | Every module needs authenticated, shop-scoped access. |
| 3 | Subscription plans (Free/Basic/Pro), simulated payment & message-limit service | Plan choice at sign-up (workflow step 1), simulated plans/payments (Scope), the monthly-limit counting service used later by FR-15 | Backend → Frontend | 2 | Sign-up includes choosing a plan. The limit service has to exist before AI replies go live. |
| 4 | Staff accounts — "Moderator" role & role-based access | FR-03; owner vs moderator permissions from §1.5 | Backend → Frontend | 2 | Fixes role rules before the feature modules that rely on them. |
| 5 | Product catalogue | FR-04 (add/edit/delete, up to 5 photos) | Backend → Frontend | 2, 4 | The catalogue is the AI's source of facts. |
| 6 | Product import from CSV/Excel | FR-05 (row-level failure report) | Backend → Frontend | 5 | Extends the catalogue module. |
| 7 | Shop policy manager | FR-06 (delivery charge by area, delivery time, return rules, payment options) | Backend → Frontend | 2, 4 | The second AI fact source (delivery, returns). |
| 8 | AI engine: embeddings & RAG retrieval pipeline | Workflow step 2, AI-R13, RAG, semantic search, per-shop vectors in pgvector | AI engine + Backend (no UI) | 5, 6, 7 | Retrieval has to work before any reply generation. |
| 9 | AI chat replies (understanding + grounded replies) & Test chat window | AI-1, AI-2, AI-R01–R04 (reply side), AI-R11, §5.3 disclosure, NFR-08 logging, FR-09 | AI engine + Backend → Frontend | 8 | Milestone M3: prove the AI in the test window before connecting Facebook. |
| 10 | AI product suggestions | AI-3, AI-R05, AI-R06 | AI engine + Backend → Frontend (test chat) | 9 | Extends the reply pipeline. |
| 11 | Automatic order drafting & phone check | AI-4, AI-R07, AI-R08, AI-R09, AI-R11 | AI engine + Backend → Frontend (test chat) | 9, 10 | Builds the orders data the order dashboard needs. |
| 12 | Smart handover & seller notification | AI-5, AI-R04 (flag), AI-R10 | AI engine + Backend → Frontend | 9, 11 | Completes the AI engine before real customers reach it. |
| 13 | Facebook Page connection | FR-07, NFR-03 (encrypted Page tokens) | Backend → Frontend | 2, 4 | Messenger can't work without a connected Page. |
| 14 | Messenger webhook & reply delivery | FR-08, workflow steps 3–8, NFR-01, NFR-09 (24-hour window), FR-15 enforcement, Redis queue | Backend (+ worker) | 3, 9–13 | Wires the finished AI pipeline to real Messenger. |
| 15 | Chat inbox & human takeover | FR-10, FR-11, flagged-first, seller replies | Backend → Frontend | 12, 14 | Needs real and flagged chats to exist. |
| 16 | Order dashboard & courier CSV export | FR-12, FR-13, workflow step 9 | Backend → Frontend | 11 | Needs AI-drafted orders to exist. |
| 17 | Reports | FR-14 (date-range metrics) | Backend → Frontend | 14, 15, 16 | Aggregates data produced by the earlier modules. |
| 18 | Weekly AI chat insights | AI-6, AI-R12 ("common-question insights") | AI engine + Backend → Frontend | 9, 14, 17 | Needs chat history and the reports page. |
| 19 | Platform admin panel | FR-16, NFR-08 (AI cost per shop), admin role (§1.5: shops, plans and limits, system health, AI costs, suspension) | Backend → Frontend | 2, 3, 9 | Manages everything built so far. |
| 20 | Shop deletion & data-privacy enforcement | §5.3 (delete shop removes chats and orders), FR-02, NFR-04 | Backend → Frontend | All data modules | Deletion has to cover every table, so it goes after all of them exist. |
| 21 | AI evaluation harness | §2 test set of 200 labelled messages; AI-R01, AI-R03, AI-R07 targets; per-language accuracy (§5.3) | Independent `evaluation/` component | 9–12 | Milestone M5: measures the finished AI. |
| 22 | Performance, load & security testing | NFR-01, NFR-03, NFR-07, NFR-09 checks; M5 "security and load tests" | Test scripts (backend side) | 1–20 | Verifies non-functional targets on the complete system. |
| 23 | Docker, deployment & user guide | §3 Deployment (Docker; Render/Railway/VPS; Vercel), HTTPS, NFR-02, NFR-05, NFR-06; M6 user guide | All components (packaging only) | 1–22 | Final delivery (M6). |

---

## Part 2 — Complete Development Prompts

Each prompt below can be copied on its own. They all repeat the same **Ground rules** block so each one stands alone.

### Prompt 1 — Project foundation & local demo environment
*Layers: backend skeleton, ai_engine skeleton, database setup, frontend skeleton · Depends on: nothing*

~~~~text
# ShopSathi — Prompt 1: Project foundation & local demo environment

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Create the empty, runnable foundation of ShopSathi: a separated project structure, a reproducible local demo database, a backend skeleton, an independent AI-engine package skeleton and a frontend skeleton. **Do not implement any product feature yet** (no auth, products, chats, AI logic or pages beyond a placeholder).

## Relevant proposal facts (Tools & Technologies, §5.2 architecture)
- Backend: Python, FastAPI (REST API, Facebook webhook, background jobs).
- Background tasks: Celery with Redis (decision for this project: Celery, Redis as broker).
- Database: PostgreSQL; vector database: pgvector extension (embeddings kept separate per shop).
- Cache and queue: Redis (message queue, rate limits, short-term chat memory).
- LLM API: OpenAI GPT-4o-mini or Google Gemini Flash (structured JSON output). Embeddings: OpenAI text-embedding-3-small, or multilingual models such as bge-m3 / multilingual-e5. AI framework: LangChain (decision for this project).
- Auth: JWT with bcrypt-hashed passwords. File handling: pandas, openpyxl. Testing: pytest.
- Frontend: React with Next.js, TypeScript, Tailwind CSS. One frontend app holds the seller dashboard, the admin panel and the test chat window, and it must work on phones and laptops (NFR-06).
- Five-layer architecture (§5.2): Clients → Integration (Messenger webhook/Send API, REST API) → Application layer (FastAPI) → AI engine → Data & external services. Each layer only talks to the layer next to it.

## Step 1 — Understand the existing project
Inspect the current folder. If it is empty, create everything below. If some parts exist, keep them and add only what is missing.

## Step 2 — Project structure (create exactly this top level)
```
shopsathi/ (repository root)
├── backend/        FastAPI application (application layer + integration endpoints + Celery worker)
├── ai_engine/      independent, installable Python package "shopsathi_ai" (AI engine layer)
├── frontend/       Next.js (App Router) + TypeScript + Tailwind CSS
├── database/       local demo database setup, init SQL and seed data
├── docs/           CONVENTIONS.md, PROGRESS.md
├── README.md
└── .gitignore      (Python, Node, .env files, media uploads, caches)
```

## Step 3 — Database (local demo setup) in `database/`
- `database/docker-compose.yml` with:
  - PostgreSQL 16 with pgvector (e.g. the `pgvector/pgvector:pg16` image), a named volume, and port and credentials read from `database/.env` (provide `database/.env.example` with non-secret local defaults).
  - Redis 7.
- `database/init/01-extensions.sql`: `CREATE EXTENSION IF NOT EXISTS vector;`, plus creation of a separate test database (e.g. `shopsathi_test`) with the extension enabled.
- `database/seed/`: empty for now, except a `README.md` explaining that later prompts put demo seed data here (fictional demo shops and products only — no real customer data).
- `database/README.md`: how to start, stop and fully reset the demo database (`docker compose up -d`, `docker compose down -v`).
- Schema migrations: Alembic, living in `backend/alembic/` because they are tied to the ORM models. Document this in `database/README.md` so the database story is clear from one place.

## Step 4 — Backend skeleton in `backend/`
- Python 3.11+, `backend/requirements.txt` (FastAPI, uvicorn, SQLAlchemy 2.x, psycopg 3, alembic, pgvector, pydantic-settings, celery, redis, passlib/bcrypt, python-jose or PyJWT, pandas, openpyxl, httpx, pytest).
- Layout:
  ```
  backend/app/
    main.py                 FastAPI app, CORS (frontend origin from env), /api/v1 router
    core/config.py          settings from environment (pydantic-settings)
    core/database.py        SQLAlchemy engine/session (sync), Base, get_db dependency
    core/redis.py           Redis client factory
    api/v1/router.py        aggregates module routers
    api/v1/routes/health.py GET /api/v1/health → status of API, database and Redis
    models/  schemas/  services/  workers/celery_app.py  cli.py
  backend/alembic/ (+ alembic.ini) — initial empty migration
  backend/tests/  conftest.py using the test database; test_health.py
  backend/.env.example
  ```
- `backend/app/cli.py`: a command entry point (`python -m app.cli <command>`) that later prompts extend (e.g. `seed`).
- Celery app configured with Redis broker; one no-op `ping` task to prove the worker runs. Document how to start the worker; note `--pool=solo` for Windows development.
- `ai_engine` is installed into the backend environment as an editable dependency (`-e ../ai_engine` in requirements), and the backend is the only component that imports it.

## Step 5 — AI engine package skeleton in `ai_engine/`
- `ai_engine/pyproject.toml`, package `shopsathi_ai/` and `tests/`.
- `shopsathi_ai/config.py`: settings from environment: `LLM_PROVIDER` (`openai` | `gemini` | `mock`), `LLM_MODEL`, `EMBEDDING_PROVIDER` (`openai` | `local` | `mock`), `EMBEDDING_MODEL`, `EMBEDDING_DIM`, API keys.
- `shopsathi_ai/providers/`: abstract `LLMProvider` and `EmbeddingProvider` interfaces, plus a factory that picks an implementation from config. Implement the `mock` providers now (deterministic, offline, for automated tests only; clearly documented as test doubles, not AI). Real OpenAI/Gemini/local implementations come in Prompt 8/9. LangChain may be used only inside `ai_engine`.
- `shopsathi_ai/interfaces.py`: an empty placeholder for the `ShopDataGateway` protocol that later prompts define. The AI engine gets shop data only through this protocol, which the backend implements; the AI engine never connects to the database itself.
- The package must not import anything from `backend/`.
- One pytest that checks the provider factory returns the mock providers.

## Step 6 — Verify backend and AI engine
- Start the database (`docker compose up -d` in `database/`), run `alembic upgrade head`, start uvicorn, call `GET /api/v1/health` (expect database and Redis "ok"), start the Celery worker and run the `ping` task, run `pytest` in `backend/` and in `ai_engine/`. Fix any failures before continuing.

## Step 7 — Frontend skeleton in `frontend/`
- Next.js (App Router) + TypeScript + Tailwind CSS + ESLint.
- `src/lib/api/client.ts`: a typed fetch wrapper using `NEXT_PUBLIC_API_BASE_URL` (from `frontend/.env.example`) that parses JSON errors in one consistent way.
- `src/app/page.tsx`: a minimal placeholder page that calls `/api/v1/health` and shows the backend status (only to prove integration; later prompts replace it).
- Plan route groups for later prompts (`(auth)`, `(dashboard)`, `admin`) but do not build those pages now.
- Base responsive layout that works on phone and laptop widths (NFR-06).

## Step 8 — Integration & verification
- Run `npm run build` and `npm run lint` in `frontend/`. Run the dev server and confirm the placeholder page shows the backend health status (CORS works).

## Step 9 — Documentation
- `docs/CONVENTIONS.md` must record: folder layout; the rule that `ai_engine` never imports `backend`; API prefix `/api/v1`, JSON only, error shape `{"detail": ...}`; SQLAlchemy 2.x sync sessions plus Alembic; every shop-owned table has `shop_id` FK (`ON DELETE CASCADE`) plus an index; timestamps stored in UTC, displayed in Asia/Dhaka; env-var naming; the frontend API-client location; test locations; how to run everything.
- `docs/PROGRESS.md`: create it with the Prompt 1 entry.
- Root `README.md`: what ShopSathi is (one paragraph, from the proposal), prerequisites (Docker, Python 3.11+, Node 20+), and step-by-step local start commands.

## Must not do
- No product features, no auth, no real AI calls, no extra services beyond PostgreSQL+pgvector and Redis.

## Expected final state
A clean, separated repository where the demo database starts with one command, the backend health endpoint reports DB/Redis "ok", the Celery worker runs, `ai_engine` installs and passes its test, and the frontend builds and displays backend health.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 2 — Shop sign-up, login/logout, password reset & multi-tenant data separation
*Layers: backend → frontend · Depends on: 1*

~~~~text
# ShopSathi — Prompt 2: Shop accounts, authentication & multi-tenant separation

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Implement shop sign-up, login, logout and password reset by email, multi-tenant data separation, and the platform administrator account type.

## Requirements from the proposal
- FR-01: A shop owner can sign up, log in, log out and reset the password by email.
- FR-02: Each shop's products, chats and orders are kept separate, so no shop can see another shop's data. §5.2: every database query is filtered by shop ID.
- NFR-03: Passwords are hashed (bcrypt). JWT login (§3, Figure 2: "REST API — HTTPS, JWT login").
- NFR-04: Customer personal data is visible only to that shop's users and the platform admin. Build the access foundation for this now.
- Stakeholders: Shop owner (seller), Shop moderator/staff (Prompt 4 adds this), Platform administrator (no public sign-up).
- Redis is used for rate limits (§3).

## Reuse
Use the Prompt 1 structure, settings, DB session, Alembic, Redis client, CLI and frontend API client.

## Step 1 — Understand the existing project
Read `docs/CONVENTIONS.md` and `docs/PROGRESS.md` and inspect the backend/frontend skeletons.

## Step 2 — Backend
1. Models and migration:
   - `shops`: id, name, status (`active` | `suspended`; default active. The admin actions come in Prompt 19), created_at.
   - `users`: id, email (unique), password_hash, full_name, role (`owner` | `moderator` | `platform_admin`), shop_id (FK `shops`, `ON DELETE CASCADE`, nullable only for `platform_admin`), is_active, created_at.
   - `password_reset_tokens`: user_id, hashed token, expires_at, used_at.
2. Endpoints under `/api/v1/auth`:
   - `POST /signup`: creates a shop and its owner user in one transaction (shop name, owner name, email, password). Validate email format, unique email and a minimum password length. (Prompt 3 adds plan choice to this flow; leave a clear extension point and don't build plans now.)
   - `POST /login`: returns a JWT access token (with user id, role, shop_id and a unique token id) and basic user/shop info.
   - `POST /logout`: revokes the current token by storing its id in a Redis denylist until it expires.
   - `GET /me`: current user and shop.
   - `POST /password-reset/request`: always returns the same response, whether or not the email exists. Creates a single-use, expiring token and emails a reset link.
   - `POST /password-reset/confirm`: token + new password.
3. Email sending: a small `EmailService` that uses SMTP settings from env. In development (no SMTP configured), it logs the email, including the reset link, to the console. No third-party email service.
4. Security dependencies (`app/core/security.py`, `app/api/deps.py`):
   - `get_current_user` (validates JWT and denylist, `is_active`).
   - `require_roles(...)`.
   - `get_current_shop_id`, which returns the user's shop_id. This is the **only** way shop-scoped endpoints get the shop id; they never take shop_id from the client.
   - A reusable tenant-scoping helper/base repository so every later shop-owned query filters by `shop_id`.
   - Suspended shops: users of a shop whose status is `suspended` cannot log in or use shop endpoints and get a clear "shop suspended" error.
5. Rate limiting with Redis on `/login` and `/password-reset/request` (simple fixed window per IP/email; limits in config).
6. Platform admin: no public sign-up. Add `python -m app.cli create-admin --email ... ` (password prompted or from env) to create a `platform_admin` user.
7. Demo data: add `database/seed/` data for one or two fictional demo shops with owner accounts. Add `python -m app.cli seed` (idempotent). Demo passwords come from env or are printed once. Never hardcode real credentials.

## Step 3 — Verify backend
pytest covering: sign-up creates shop + owner; duplicate email rejected; login success/failure; password stored hashed; logout revokes token; reset flow (request → token → confirm → login with new password; token single-use and expiry); a suspended shop's user cannot log in; **tenant isolation test**: a user from shop A cannot read shop B's data through the tenant-scoping helper. Run all tests; fix failures.

## Step 4 — Frontend
- Pages in the `(auth)` route group: Sign up (shop name, owner name, email, password), Log in, Forgot password, Reset password (reads token from the link).
- An auth module in `src/lib/auth/` that stores the access token (localStorage), attaches it as `Authorization: Bearer` through the existing API client, and handles logout and 401 (redirect to login).
- A protected `(dashboard)` layout shell: responsive nav (collapses on phones) showing shop name and user, with a Log out button. The dashboard home page is a simple placeholder; later prompts add sections. Only add nav items for modules that exist.
- Show backend validation errors clearly.

## Step 5 — Integrate & verify
Run the frontend against the backend: sign up a new shop → land on the dashboard → log out → log in → forgot password → use the reset link from the backend console → log in with the new password. Check at phone width. Run `npm run build` and `npm run lint` and all backend tests.

## Must not do
No plans, staff accounts, products or admin panel screens yet. No social login.

## Expected final state
A working multi-tenant auth system: shop owners can sign up, log in, log out and reset their password. Every request resolves its shop from the token. A platform admin can be created by CLI. Tenant isolation is enforced and tested.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 3 — Subscription plans (Free, Basic, Pro), simulated payment & monthly message-limit service
*Layers: backend → frontend · Depends on: 2*

~~~~text
# ShopSathi — Prompt 3: Subscription plans & message-limit service

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Add the Free, Basic and Pro subscription plans, plan choice during sign-up, simulated payment for plan selection, a seller "My plan" page, and a reusable monthly message-limit service that the Messenger module (Prompt 14) will call.

## Requirements from the proposal
- Workflow step 1: "The seller signs up, chooses a plan and connects their Facebook Page." (The Facebook part is Prompt 13.)
- Scope: "Subscription plans (Free, Basic, Pro) with monthly message limits." Out of scope: "Real online payment. Plans and payments will be simulated, and there is no real bKash, Nagad or card gateway."
- FR-15: Free, Basic and Pro plans with monthly message limits; stop AI replies when the limit is reached. Build the counting/checking service here. Prompt 14 wires it in before sending AI replies.
- FR-16 (admin changes a shop's plan) is Prompt 19; make the service reusable for that.

## Reuse
Prompt 2 auth, `get_current_shop_id`, tenant helper, sign-up endpoint and page, CLI seed command.

## Step 1 — Understand the existing project.

## Step 2 — Backend
1. Models and migration:
   - `plans`: id, code (`free` | `basic` | `pro`), name, monthly_message_limit, monthly_price (display only).
   - `shops.plan_id` (FK, required; existing shops default to Free in the migration).
   - `simulated_payments`: shop_id, plan_id, amount, status (`simulated_success`), created_at. This only records that a simulated payment happened. No card, bKash or Nagad fields or integrations.
   - `shop_message_usage`: shop_id, period (year-month), ai_messages_count; unique per shop and period.
2. Seed: `database/seed/plans.json` with the three plans. The proposal does not give prices or limit numbers, so use clearly labelled **placeholder values** (comment/README: "team to decide") and load them via `app.cli seed`.
3. Endpoints:
   - `GET /api/v1/plans` (public; used on sign-up).
   - Extend `POST /api/v1/auth/signup` to accept `plan_code`. Free activates directly. Basic/Pro need a simulated payment confirmation flag in the request, and record a `simulated_payments` row.
   - `GET /api/v1/shop/plan`: current plan, this month's usage, limit, remaining.
   - `POST /api/v1/shop/plan/change`: owner only. Same simulated-payment rule for paid plans.
4. `UsageLimitService` (in `app/services/`), reusable later:
   - `can_send_ai_reply(shop_id) -> bool`
   - `record_ai_reply(shop_id)`, atomic increment for the current calendar month.
   - `get_usage(shop_id)`.
   - Counting rule (record it in `docs/CONVENTIONS.md`): one count = one AI reply sent to a customer on Messenger. Test chat window messages (Prompt 9) are not counted. Counts reset per calendar month (Asia/Dhaka).
   - Do not call this service from any message flow yet (Prompt 14 does that).

## Step 3 — Verify backend
pytest: plans listed; sign-up with each plan; paid plan without simulated confirmation is rejected; plan change creates a simulated payment record; usage increments and `can_send_ai_reply` becomes false exactly at the limit; new month starts at zero; only a user with the `owner` role can change the plan.

## Step 4 — Frontend
- Sign-up page: add a plan selection step listing Free/Basic/Pro with message limits and prices from the API. For Basic/Pro, show a clearly labelled **"Simulated payment — no real money is charged"** confirmation step. No payment form fields.
- Dashboard "Plan" page: current plan, messages used this month / limit, and a change-plan action using the same simulated confirmation.

## Step 5 — Integrate & verify
Sign up with Free and with Pro; change plan from the dashboard; confirm usage numbers come from the backend. Check phone width. Run the frontend build/lint and all backend tests.

## Must not do
No real payment gateway, invoices, coupons, trials or billing emails. Do not enforce limits on any message flow yet.

## Expected final state
Shops always have a plan chosen at sign-up, paid plans go through a clearly simulated payment, sellers can see their usage, and a tested `UsageLimitService` is ready for Prompt 14.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 4 — Staff accounts with the "Moderator" role & role-based access
*Layers: backend → frontend · Depends on: 2*

~~~~text
# ShopSathi — Prompt 4: Staff accounts (Moderator role) & role-based access

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Let the shop owner add staff accounts with the "Moderator" role, and define the role-based access rules that all later modules will follow.

## Requirements from the proposal
- FR-03: The owner can add staff accounts with a "Moderator" role.
- §1.5 roles:
  - **Shop owner (seller):** signs up, adds products and policies, connects the Facebook Page, confirms orders, takes over chats.
  - **Shop moderator/staff:** watches chats, handles flagged messages, manages orders for the owner.
  - **Platform administrator:** manages shops, plans and limits (admin panel comes in Prompt 19).
- NFR-04: customer data visible only to that shop's users and the platform admin.

## Access matrix (write it into `docs/CONVENTIONS.md`; later prompts must enforce it)
| Area | Owner | Moderator |
|---|---|---|
| Staff accounts, plan, Facebook Page connection, shop deletion | yes | no |
| Products, CSV/Excel import, shop policy | yes | no |
| Test chat window, reports & weekly insights | yes | no |
| Chat inbox, flagged chats, pause/resume AI, manual replies | yes | yes |
| Order drafts: confirm/edit/cancel, export CSV | yes | yes |
The platform admin uses only the admin panel endpoints (Prompt 19) and is never treated as a shop user.

## Reuse
Prompt 2 `users` table (role `moderator` already exists), `require_roles`, `get_current_shop_id`, password reset flow, dashboard layout.

## Step 1 — Understand the existing project.

## Step 2 — Backend
- `POST /api/v1/shop/staff` (owner only): create a moderator in the owner's shop with email, full name and an initial password. Email must be unique. The moderator can change it later through the existing password-reset flow.
- `GET /api/v1/shop/staff` (owner only): list the shop's moderators.
- Add role constants and reusable dependencies `require_owner` and `require_shop_user` (owner or moderator), built on the existing `require_roles`.
- Apply `require_owner` to the existing plan-change endpoint (Prompt 3).

## Step 3 — Verify backend
pytest: owner can add/list moderators; moderator gets 403 on staff and plan-change endpoints; a moderator can log in and `GET /me` shows their shop; owner of shop A cannot list shop B's staff.

## Step 4 — Frontend
- Dashboard "Staff" page (owner only): list moderators, form to add one.
- Make the dashboard navigation role-aware using the access matrix (hide owner-only sections for moderators; direct URL access shows a "not allowed" message). Only show sections that already exist.

## Step 5 — Integrate & verify
Owner adds a moderator → log in as that moderator → owner-only pages are hidden and blocked. Run build/lint and all tests.

## Must not do
No extra roles or custom permissions. No staff features beyond adding and listing moderator accounts.

## Expected final state
Owners can create Moderator accounts, the access matrix is documented, and reusable role dependencies exist for all later modules.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 5 — Product catalogue
*Layers: backend → frontend · Depends on: 2, 4*

~~~~text
# ShopSathi — Prompt 5: Product catalogue

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Implement the product catalogue where the seller adds, edits and deletes products.

## Requirements from the proposal
- FR-04: add, edit and delete products with name, description, price, sizes, colours, stock count and up to 5 photos.
- The catalogue is the AI's source of truth for price, size, colour and stock (AI-2, AI-R03). Data must be stored cleanly so later prompts can turn it into embeddings (AI-R13, Prompt 8).
- Product photos are shown with product suggestions later (AI-3: "with price and photo") and sent through Messenger, so stored photos must be reachable through a URL.
- Access: owner only (see the access matrix in `docs/CONVENTIONS.md`).

## Reuse
Tenant-scoping helper, `require_owner`, dashboard layout, API client.

## Step 1 — Understand the existing project.

## Step 2 — Backend
1. Model and migration `products`: id, shop_id (FK, cascade, indexed), name, description, price (numeric, BDT), sizes (list of strings, may be empty), colours (list of strings, may be empty), stock_count (integer ≥ 0), photos (ordered list of up to 5 photo URLs/paths), created_at, updated_at.
2. Photo storage: a small `StorageService` that saves uploaded images to a local media folder (path from env, git-ignored), served by the backend at a URL (e.g. `/media/...`). Accept common image types only, with a max file size in config, and at most 5 photos per product.
3. Endpoints `/api/v1/products` (owner only, always scoped to the caller's shop): list (with simple name search and pagination), get, create, update, delete, upload photo(s), remove a photo.
4. Validation: name required; price > 0; stock_count integer ≥ 0; sizes/colours trimmed, no duplicates; ≤ 5 photos. Clear 422 messages.
5. Leave one clearly named service-layer hook point (e.g. `ProductService` emitting "product changed/deleted") that Prompt 8 will connect to embedding updates. Do not implement embeddings now.
6. Demo data: add fictional demo products (clothes, cosmetics, food, gadgets, handicrafts — the shop types named in §1.1, e.g. a "Red Jamdani Saree", panjabi in several sizes, at least one item with stock 0) to `database/seed/` for the demo shops, loaded by `app.cli seed`.

## Step 3 — Verify backend
pytest: CRUD; validation errors; 6th photo rejected; shop A cannot read, update or delete shop B's product (404); moderator gets 403; delete removes the product's stored photos.

## Step 4 — Frontend
- "Products" section: responsive list/table (cards on phones) with name, price, stock, sizes, colours and the first photo; add/edit form (with chip-style inputs for sizes/colours); photo upload with preview and remove (max 5); delete with confirmation.

## Step 5 — Integrate & verify
Create, edit and delete products with photos through the UI against the backend. Check phone width. Run build/lint and all tests.

## Must not do
No categories, discounts, variants with separate prices, stock reservation or warehouse stock management (warehouse stock is out of scope). No CSV import (Prompt 6). No embeddings (Prompt 8).

## Expected final state
Owners manage a shop-scoped product catalogue with up to 5 photos per product, demo products are seeded, and a hook point is ready for embedding updates.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 6 — Product import from CSV or Excel
*Layers: backend → frontend · Depends on: 5*

~~~~text
# ShopSathi — Prompt 6: Product import from CSV/Excel

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Let the seller import products from a CSV or Excel file and show which rows failed and why.

## Requirements from the proposal
- FR-05: import products from a CSV or Excel file and show which rows failed and why.
- Scope: the file contains name, price, sizes, colours, stock and photos. FR-04 adds description.
- Tools: pandas and openpyxl.
- Access: owner only.

## Reuse
The Prompt 5 `products` model, validation rules and `ProductService` (including its change hook). **Do not duplicate product validation.** Call the same service and validators.

## Step 1 — Understand the existing project.

## Step 2 — Backend
1. `POST /api/v1/products/import` (owner only): accepts `.csv`, `.xlsx`. Reads with pandas/openpyxl.
2. Columns (document them in a downloadable template): `name`, `description`, `price`, `sizes` (separated by `|` or `,`), `colours` (same), `stock`, `photos` (up to 5 image URLs separated by `|`).
3. Validate each row with the existing product validation. Valid rows create products through `ProductService`. Invalid rows are skipped and reported. Response: totals (rows read, imported, failed) and a list of failures, each with row number and reason(s) (e.g. "price must be greater than 0", "more than 5 photos", "missing name").
4. Reject wrong file types, empty files and files missing required columns with a clear error. Limit file size in config.
5. `GET /api/v1/products/import/template`: returns a template CSV with the headers and one example row.
6. Put a sample import file (valid and invalid rows, fictional data) in `database/seed/sample_products_import.csv` for testing.

## Step 3 — Verify backend
pytest with CSV and XLSX fixtures: all valid; mixed valid/invalid (correct row numbers and reasons); missing columns; wrong file type; imported products belong only to the importer's shop; moderator gets 403.

## Step 4 — Frontend
On the Products page add "Import from CSV/Excel": file picker, template download link, upload progress, and a result panel showing imported count and a table of failed rows (row number + reason). Refresh the product list after import.

## Step 5 — Integrate & verify
Import the sample file through the UI and confirm the failed-row report matches the file. Run build/lint and all tests.

## Must not do
No product-update-by-matching, scheduled imports or export of products.

## Expected final state
Owners can bulk-import products from CSV/XLSX, see exactly which rows failed and why, and imported products go through the same service as manual ones.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 7 — Shop policy manager
*Layers: backend → frontend · Depends on: 2, 4*

~~~~text
# ShopSathi — Prompt 7: Shop policy manager

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Implement the shop policy page where the seller writes delivery charges by area, delivery time, return rules and payment options.

## Requirements from the proposal
- FR-06: shop policies: delivery charge by area, delivery time, return rules and payment options.
- Scope: "A shop policy page for delivery charges, delivery time, return rules and payment options."
- The AI answers delivery questions only from this data (AI-2, AI objective 2). The AI tool "get delivery charge" (Prompt 9) needs a lookup by area, e.g. "Khagan e delivery charge koto?".
- Access: owner only.

## Reuse
Tenant-scoping helper, `require_owner`, dashboard layout.

## Step 1 — Understand the existing project.

## Step 2 — Backend
1. Models and migration:
   - `shop_policies` (one per shop): shop_id (unique, FK cascade), delivery_time (text), return_rules (text), payment_options (text), updated_at.
   - `delivery_areas`: id, shop_id (FK cascade, indexed), area_name, charge (numeric BDT ≥ 0).
2. Endpoints `/api/v1/shop/policy` (owner only): `GET` (returns policy + areas; empty defaults if not set yet), `PUT` (replace whole policy including the areas list). Validate: area names unique per shop (case-insensitive), charge ≥ 0, text length limits.
3. A `PolicyService` method `get_delivery_charge(shop_id, area_text)`: case-insensitive exact or normalised match on area name, returning the charge or "not found". No guessing. Prompt 9 builds the AI tool on top of this.
4. Same as products: add one service-layer "policy changed" hook point for Prompt 8. No embeddings now.
5. Demo data: fictional policies for the demo shops (e.g. Inside Dhaka / Outside Dhaka / named areas) in `database/seed/`.

## Step 3 — Verify backend
pytest: get default, save, update; duplicate area rejected; `get_delivery_charge` found/not found; tenant isolation; moderator 403.

## Step 4 — Frontend
"Shop Policy" page: editable area/charge rows (add/remove), delivery time, return rules and payment options text fields, save with success/error feedback. Responsive.

## Step 5 — Integrate & verify
Edit and save the policy through the UI, reload, and confirm persistence. Run build/lint and all tests.

## Must not do
No courier integration, delivery tracking or payment processing (all out of scope).

## Expected final state
Each shop has a stored, editable policy with delivery charges by area, plus a tested lookup method ready for the AI.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 8 — AI engine: embeddings & RAG retrieval pipeline
*Layers: ai_engine + backend (no UI) · Depends on: 5, 6, 7*

~~~~text
# ShopSathi — Prompt 8: Embeddings & RAG retrieval (per shop)

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Build the AI engine's "Embedder" and "Retriever" (Figure 2): turn each shop's products and policy into searchable embeddings stored in pgvector, keep them updated, and retrieve the most relevant chunks for a customer message. This prompt has no frontend.

## Requirements from the proposal
- Workflow step 2: "The system turns this data into searchable embeddings for that shop only."
- RAG: "each shop's products and policy are split into small chunks, turned into embeddings and stored in a vector database. For each message, the most relevant chunks are retrieved and given to the LLM."
- Semantic search: multilingual embeddings match "lal saree" with a product listed as "Red Jamdani Saree".
- AI-R13: a product's embeddings update within 1 minute after the seller adds or edits it.
- pgvector embeddings kept separate for each shop; §5.3: one shop's data is never used to answer another shop's customers.
- Embedding model: OpenAI text-embedding-3-small, or a multilingual open-source model (bge-m3 / multilingual-e5). Celery + Redis for background jobs. NFR-08: log AI API usage per shop.

## Reuse
`ai_engine` provider interfaces and mock providers (Prompt 1), product/policy services and their change hooks (Prompts 5–7), Celery app.

## Step 1 — Understand the existing project.

## Step 2 — AI engine (`ai_engine/shopsathi_ai/`)
1. Real embedding providers behind the existing `EmbeddingProvider` interface: `openai` (text-embedding-3-small) and `local` (a multilingual sentence-embedding model such as bge-m3 or multilingual-e5). Selected by config. Each returns vectors plus usage info (tokens) for cost logging.
2. `chunking.py`: pure functions that turn a product into chunk text (name, description, price, sizes, colours, stock status) and a policy into chunks (delivery time, return rules, payment options, each delivery area/charge). Each chunk carries metadata: source_type (`product` | `policy`), source_id.
3. `interfaces.py`: define the `ShopDataGateway` protocol methods needed for retrieval (e.g. `vector_search(shop_id, query_vector, top_k, source_types)`). The AI engine calls the gateway and never touches the database itself.
4. `retrieval.py`: `retrieve(shop_id, query_text, top_k)` → embeds the query and calls the gateway, returning ranked chunks.
5. Unit tests with the mock providers and an in-memory fake gateway.

## Step 3 — Backend
1. Model and migration `embedding_chunks`: id, shop_id (FK cascade, indexed), source_type, source_id, content, embedding `vector(EMBEDDING_DIM)`, updated_at. Add an appropriate pgvector index. Every query filters by shop_id.
2. `app/ai_adapters/gateway.py`: the backend's implementation of `ShopDataGateway` (pgvector cosine search **always filtered by shop_id**).
3. Celery tasks: `embed_product(product_id)`, `delete_product_embeddings(product_id)`, `embed_policy(shop_id)`. Connect them to the existing product/policy hooks (manual add/edit/delete, CSV import, policy save) with minimal changes to those services, so updates are queued immediately and finish well under 1 minute (AI-R13).
4. Model and migration `ai_usage_logs`: shop_id, operation (e.g. `embedding`), provider, model, input_tokens, output_tokens, estimated_cost, created_at. Log every embedding call. Per-model cost rates come from config. Prompt 9 and later prompts reuse this table.
5. CLI: `python -m app.cli reembed-shop --shop-id` and `reembed-all` (needed when the embedding model/dimension changes, and for seeding).
6. Extend `app.cli seed` to queue embeddings for demo data.

## Step 4 — Verify
- pytest (mock provider): creating/editing/deleting a product creates/replaces/removes its chunks; policy save re-embeds policy chunks; retrieval for shop A never returns shop B chunks even when B has a closer match; usage is logged.
- Timing check: with the worker running, edit a product and confirm its chunks are updated within 1 minute (log the measured time).
- With a real provider configured (if keys are available): run a small script showing that "lal saree" retrieves "Red Jamdani Saree" from the demo shop. If no key is available, say so in the report and leave the script ready.

## Must not do
No reply generation, intent detection or chat endpoints (Prompt 9). No frontend changes.

## Expected final state
Products and policies of each shop are chunked, embedded and stored per shop in pgvector, kept fresh by background jobs within 1 minute, retrievable through a shop-isolated retriever, and every embedding call is cost-logged per shop.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 9 — AI chat replies (message understanding + catalogue-grounded replies) & Test chat window
*Layers: ai_engine + backend → frontend · Depends on: 8*

~~~~text
# ShopSathi — Prompt 9: AI chat replies & Test chat window

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Build the core conversation pipeline (Figure 1: "1. Understand → 2. Search (RAG) → 3. Write reply") and the Test chat window where the seller chats with the AI without Facebook. Follow Milestone M3: a working AI chat in the test window before Facebook is connected.

## Requirements from the proposal
- AI-1 / AI-R01: detect the intent of a customer message: **price, size/stock, delivery, suggestion, order, complaint, other**, with key details (product name, size, colour, area), using structured JSON output.
- AI-R02 / AI objective 1: understand Bangla script, English and Banglish, including spelling mistakes and short forms; reply in the same style the customer used.
- AI-2 / AI-R03: short, polite reply using **only** the shop's products and policy. Prices and stock must match the catalogue exactly. Never make up facts.
- AI-R04: when the answer is not in the shop's data, reply "I'll check with the shop" (in the customer's language style) instead of guessing. (Flagging the chat comes in Prompt 12. Here, return a structured "needs handover: not in shop data" signal.)
- AI-R11 / "What the AI will not do": it doesn't confirm orders, change prices, give discounts, promise anything not in the shop's data, take payment, or answer questions unrelated to the shop.
- §5.3: the **first AI reply in a chat** tells the customer they are talking to the shop's automatic assistant and that they can ask for a person.
- §5.3 privacy: send the LLM only what it needs for one reply, not the whole customer history.
- AI agent with tools: search products, check stock, get delivery charge (update order draft comes in Prompt 11).
- Redis: short-term chat memory. NFR-08: log AI API usage per shop. LLM: GPT-4o-mini or Gemini Flash.
- FR-09: test chat window where the seller chats with the AI without using Facebook. Scope: "so sellers can try the AI before going live".
- Example messages from the proposal to test with: "price koto?", "XL ache?", "Khagan e delivery charge koto?", "eta ki XL e pawa jabe?", "XL size ache?".

## Reuse
Prompt 8 retriever, `ShopDataGateway`, `ai_usage_logs`. `PolicyService.get_delivery_charge` (Prompt 7). Product data (Prompt 5). Provider factory and mock providers. Access matrix (test chat is owner only).

## Step 1 — Understand the existing project.

## Step 2 — AI engine (`ai_engine/shopsathi_ai/`)
1. Real LLM providers behind `LLMProvider`: `openai` (GPT-4o-mini) and `gemini` (Gemini Flash), both supporting structured JSON output and tool calling (through LangChain), returning token usage.
2. `language.py`: detect the message style (`bangla` | `english` | `banglish`) and normalise Bangla digits (০-৯ → 0-9) for downstream use.
3. `understanding.py`: `understand(message, recent_turns) -> Understanding` with a Pydantic schema: intent (exactly the 7 values above), entities (product_name, size, colour, area), language_style, confidence (0–1). Validate the LLM JSON against the schema, with a single retry on invalid output.
4. Extend `ShopDataGateway` with the tool data methods: `search_products`, `check_stock(product_id/size/colour)`, `get_delivery_charge(area)`. Implement the tools in `tools.py` on top of the gateway.
5. `reply.py`: `write_reply(...)`. The prompt instructs the LLM to answer only from the supplied chunks and tool results, in the customer's language style, short and polite. Then check in code: every price or stock number in the reply must appear in the supplied facts. If not, regenerate once, then fall back to the "I'll check with the shop" reply with the handover signal.
6. `engine.py`: `ConversationEngine.process_customer_message(shop_id, chat_context, message) -> EngineResult`, orchestrating understand → retrieve/tools → reply. `EngineResult` carries: reply_text, intent, entities, confidence, language_style, `handover` (needed: bool + reason), and an extensible `extras` field for Prompts 10–12. Include the first-reply disclosure when `chat_context.is_first_ai_reply`.
   - Until Prompts 10–12 extend them, `suggestion`, `order` and `complaint` intents get only a safe, grounded reply or the "I'll check with the shop" response. Don't build those features here.
7. Prompt templates live in `shopsathi_ai/prompts/` as files, not inline strings.
8. Unit tests with mock providers: schema validation, language detection, number-grounding check, disclosure on first reply only, handover signal when facts are missing.

## Step 3 — Backend
1. Models and migration:
   - `chats`: id, shop_id (FK cascade), channel (`messenger` | `test`), customer_psid (nullable), customer_name (nullable), created_by_user_id (for test chats), ai_paused (bool, default false), is_flagged (bool, default false), flag_reason (nullable), flagged_at (nullable), ai_disclosure_sent (bool), last_customer_message_at, created_at, updated_at.
   - `messages`: id, shop_id, chat_id (FK cascade), sender (`customer` | `ai` | `seller`), text, intent, confidence, language_style, extras (JSON), external_message_id (nullable, unique per shop), received_at, sent_at, created_at.
2. `app/ai_adapters/gateway.py`: implement the new gateway methods with shop-scoped queries.
3. Short-term chat memory: `ChatMemoryService` in Redis (last N turns per chat with TTL; N in config). Only these recent turns and retrieved facts go to the LLM.
4. `ConversationService.handle_customer_message(chat, text)` in `app/services/`: stores the customer message, builds the chat context, calls `ConversationEngine`, stores the AI message with intent/confidence/style/extras, marks disclosure sent, logs LLM usage to `ai_usage_logs` (operation `chat_reply`, plus `intent` if it is a separate call), and returns the result. **This is the single entry point. Prompt 14 (Messenger) must reuse it.**
5. Test chat endpoints (owner only), channel `test`:
   - `POST /api/v1/test-chat/sessions`: start a new test conversation.
   - `GET /api/v1/test-chat/sessions`, `GET /api/v1/test-chat/sessions/{id}/messages`.
   - `POST /api/v1/test-chat/sessions/{id}/messages`: send a message as the customer, get the AI reply in the response.
   - Test chats are **not** counted by `UsageLimitService` (see `docs/CONVENTIONS.md`), but their AI usage cost is logged. Inbox, reports and exports (later prompts) must exclude channel `test`.

## Step 4 — Verify backend
- pytest (mock providers): send messages through the test-chat API; messages persisted; disclosure only in the first AI reply; usage logged per shop; test chat for shop A cannot be read by shop B; moderator 403.
- With a real LLM key (if available): run the proposal's example messages against a seeded demo shop and confirm the replies use catalogue prices/stock exactly, keep the customer's style, and that an unknown question gets "I'll check with the shop". Measure reply time and note it (NFR-01 target: within 8 seconds). If no key is available, say so in the report.

## Step 5 — Frontend
"Test chat" page (owner only): a Messenger-like chat UI (customer bubbles on one side, AI on the other), message input, a "thinking" indicator while waiting, a "Start new test conversation" button, and a list of previous test sessions. Responsive. Show a visible label that this is a test chat and nothing is sent to Facebook.

## Step 6 — Integrate & verify
Chat with the AI in the UI using the proposal's example messages (Bangla script, English, Banglish). Check phone width. Run build/lint and all tests.

## Must not do
No product suggestion cards (Prompt 10), order drafting (Prompt 11), flagging/notifications (Prompt 12) or Messenger sending (Prompt 14). No answers from general knowledge.

## Expected final state
The seller can chat with the shop's AI in the Test chat window. The AI understands Bangla/English/Banglish, answers only from the shop's catalogue and policy in the customer's style, discloses it is an automatic assistant in the first reply, says "I'll check with the shop" when the data has no answer, and every AI call is logged per shop.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 10 — AI product suggestions
*Layers: ai_engine + backend → frontend (test chat) · Depends on: 9*

~~~~text
# ShopSathi — Prompt 10: AI product suggestions

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Add product suggestions to the existing conversation pipeline.

## Requirements from the proposal
- AI-3: input is the customer's needs, e.g. "eid er jonno 1500 er moddhe panjabi". Output: **1 to 3 matching in-stock products with price and photo.**
- AI-R05: suggest 1 to 3 in-stock products that match the customer's stated needs (type, budget, size, colour). AI objective 3 also mentions occasion.
- AI-R06: **never** suggest a product whose stock is zero.
- §5.3 fairness: suggestions are based on the customer's stated needs and stock, not on guesses about the customer's gender, religion or background.
- Answers only from the shop's data (AI-R03). If nothing matches, say so honestly instead of inventing.

## Reuse
`ConversationEngine` and its `extras`, retriever, gateway tools (`search_products`, `check_stock`), product photos URLs (Prompt 5), Test chat page (Prompt 9). Extend these. Do not create a parallel pipeline.

## Step 1 — Understand the existing project.

## Step 2 — AI engine
1. `suggestions.py`: when intent is `suggestion`, extract the stated needs (product type, budget, size, colour, occasion) with structured output; retrieve candidates via the retriever plus the gateway; then **filter in code**: stock_count > 0 (and the requested size/colour available if stated), price ≤ budget if stated. Rank and return 1–3 products (id, name, price, first photo URL). The LLM writes the short reply text using only these products.
2. If no product passes the filter, return zero suggestions with an honest reply in the customer's style (no invented items). Do not relax the stock rule.
3. Put the suggestions in `EngineResult.extras["suggested_products"]`.
4. Unit tests: zero-stock products never returned even when they are the best semantic match; budget/size/colour respected; at most 3; no-match case.

## Step 3 — Backend
- Make sure `ConversationService` stores `suggested_products` in the AI message `extras`, and the test-chat API returns them.
- Gateway: add any shop-scoped product lookup the suggestion step needs (live stock read from `products`, not only from embeddings, so stock is always current).

## Step 4 — Verify backend
pytest through the test-chat API (mock providers): suggestion response contains 1–3 in-stock products of the same shop; zero-stock seeded product never appears. With a real key (if available), try "eid er jonno 1500 er moddhe panjabi" against the demo shop.

## Step 5 — Frontend
In the Test chat window, render suggested products under the AI reply as small cards (photo, name, price). Reuse existing UI components. Responsive.

## Step 6 — Integrate & verify
Ask for suggestions in Banglish, Bangla and English in the test chat; check cards match backend data and out-of-stock items never appear. Run build/lint and all tests.

## Must not do
No recommendations based on customer profiling, no "related products" widgets, no discounts.

## Expected final state
The AI suggests 1–3 matching in-stock products with price and photo, never a zero-stock product, and the test chat shows them as cards.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 11 — Automatic order drafting from chat & phone check
*Layers: ai_engine + backend → frontend (test chat) · Depends on: 9, 10*

~~~~text
# ShopSathi — Prompt 11: Automatic order drafting & phone check

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
When a customer wants to buy, the AI collects the order details from the conversation, asks for anything missing, validates the phone number, and creates an **order draft** for the seller to confirm.

## Requirements from the proposal
- AI-4: input is the chat history; output is an order draft with **product, size, colour, quantity, name, phone, address, and a list of any missing fields**.
- AI-R07: extract these fields from a chat into an order draft (target: at least 90% of fields correct on the test set, measured in Prompt 21).
- AI-R08: check the phone is a **valid 11-digit Bangladeshi mobile number**, and ask the customer again if it isn't.
- AI-R09: ask the customer for any missing order field **before** creating the order draft.
- AI-R11 / §5.3: the AI never confirms an order, changes a price or gives a discount. The seller always gives final approval.
- Workflow step 7: "If the customer wants to buy, the AI asks for any missing details and fills an order draft." §1.6: "checks nothing is missing before the order reaches the seller."
- AI tool: "update the order draft".

## Reuse
`ConversationEngine`, gateway, `check_stock`/`search_products` tools, `ConversationService`, chat memory, test chat page. Extend these. Do not duplicate them.

## Step 1 — Understand the existing project.

## Step 2 — AI engine
1. `validators.py`: `normalize_and_validate_bd_phone(text)`. Convert Bangla digits, strip spaces, dashes and a leading `+88`/`88` country code. The result must be exactly 11 digits matching `^01[3-9]\d{8}$`. Pure function with thorough unit tests. The backend reuses this same function (Prompt 16).
2. `extraction.py`: `extract_order(conversation_turns, current_pending_fields) -> OrderExtraction` (structured JSON): product (as named), size, colour, quantity, name, phone, address, plus `missing_fields`. Then validate in code:
   - product must resolve (through the gateway) to a product of **this shop**;
   - size/colour must be one of that product's listed options (not required if the product has none);
   - quantity is a positive integer;
   - phone passes the validator. If it fails, add it to the fields to re-ask (AI-R08).
3. Tool `update_order_draft(fields)`: merges newly extracted fields into the chat's pending order state.
4. Engine behaviour for intent `order` (and follow-up turns while an order is being collected): if fields are missing or invalid, reply asking for exactly those fields in the customer's style. When all fields are present and valid, return `extras["order_ready"]` with the complete field set. The reply tells the customer the details were sent to the shop for confirmation. It must **not** say the order is confirmed and must not mention discounts or prices other than the catalogue price. If the product's stock is zero according to the catalogue, say so from the data and don't draft that item.
5. Unit tests: missing-field questions; invalid phone re-ask (e.g. 10 digits, wrong prefix); Bangla-digit phone accepted; size not in options rejected; complete order produces `order_ready`; reply never contains "confirmed".

## Step 3 — Backend
1. `chats.pending_order` (JSON, nullable) column: the in-progress collected fields per chat (migration).
2. Model and migration `orders`: id, shop_id (FK cascade), chat_id (FK), product_id, product_name (snapshot), size, colour, quantity, unit_price (snapshot of catalogue price at draft time), customer_name, customer_phone, customer_address, status (`draft` | `confirmed` | `cancelled`), is_test (bool; true for test-chat orders), created_at, updated_at, confirmed_at, cancelled_at, confirmed_by_user_id.
3. In `ConversationService`: persist pending fields after each turn. When the engine returns `order_ready`, create **one** `orders` row with status `draft` (no duplicate drafts for the same completed collection), clear `pending_order`, and store the order id in the AI message extras. Never set status `confirmed` from the AI path.
4. Log the extraction LLM usage to `ai_usage_logs` (operation `order_extraction`).

## Step 4 — Verify backend
pytest through the test-chat API (mock providers): multi-turn conversation that gives details piece by piece → asks for missing fields → invalid phone re-asked → draft created with status `draft` and `is_test=true`; draft belongs to the right shop; the AI path cannot produce `confirmed`. With a real key (if available), run a Banglish ordering conversation.

## Step 5 — Frontend
In the Test chat window, when an order draft is created, show an "Order draft created" card (product, size, colour, quantity, name, phone, address, status "draft — awaiting seller confirmation"). Responsive.

## Step 6 — Integrate & verify
Place a full order in the test chat in Banglish, including a wrong phone number first; confirm the card matches the stored draft. Run build/lint and all tests.

## Must not do
No order dashboard, confirm/edit/cancel or export (Prompt 16). No payment, courier booking or stock deduction.

## Expected final state
The AI turns a normal conversation into a validated order draft, asks for missing fields and re-asks for invalid phones, never confirms orders itself, and drafts are stored per shop (test-chat drafts marked as test).

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 12 — Smart handover to a human & seller notification
*Layers: ai_engine + backend → frontend · Depends on: 9, 11*

~~~~text
# ShopSathi — Prompt 12: Smart handover & seller notification

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Make the AI flag chats it can't handle, pass them to the seller, and notify the seller.

## Requirements from the proposal
- AI-5: input is the message, detected intent and the AI's confidence. Output: **flag + reason** (complaint, refund, low confidence, off-topic) and a seller notification.
- AI-R10: flag a chat and notify the seller when the customer complains, asks for a refund, uses abusive language, or when the AI's confidence is low.
- AI-R04: when the answer is not in the shop's data, reply "I'll check with the shop" and **flag the chat** instead of guessing.
- Scope "What the AI will do": flag chats it can't handle, such as complaints, refunds, angry customers or questions not covered by the shop's data. §5.3: the customer can ask for a person. AI objective 5: pass the chat to the seller instead of guessing.
- Workflow step 8: "If the AI is unsure, or the customer is upset, the chat is flagged and the seller is notified."
- "It will not answer questions unrelated to the shop" → off-topic is a handover reason.
- Stakeholders: moderators handle flagged messages; the seller can take over any chat.

## Flag reasons (use exactly this set)
`complaint`, `refund`, `abusive_language`, `low_confidence`, `off_topic`, `not_in_shop_data`, `human_requested`.

## Reuse
`EngineResult.handover` signal (Prompt 9), `chats.is_flagged/flag_reason/flagged_at/ai_paused`, `ConversationService`, test chat page, dashboard layout.

## Step 1 — Understand the existing project.

## Step 2 — AI engine
1. `handover.py`: `decide_handover(message, understanding, engine_state) -> HandoverDecision(flag: bool, reason)`. Combine the intent (`complaint`), structured detection of refund requests, abusive language and requests for a person, confidence below a configurable threshold (`AI_CONFIDENCE_THRESHOLD`, document the default), off-topic questions, and the existing not-in-data signal.
2. When flagged, the reply is a short, polite holding message in the customer's style ("I'll check with the shop" / a person from the shop will reply). No promises, refunds or discounts.
3. Unit tests for each reason and for a normal message that must not be flagged.

## Step 3 — Backend
1. Model and migration `handover_events`: id, shop_id, chat_id, reason, created_at. Prompt 17 counts "chats handed to humans" from this table.
2. Model and migration `notifications`: id, shop_id, type (`chat_flagged`), chat_id, reason, created_at, read_at.
3. In `ConversationService`, when the engine flags: set `chats.is_flagged=true`, `flag_reason`, `flagged_at`, set `ai_paused=true` (the chat is handed to a human, so the AI stops replying until a shop user turns it back on in Prompt 15), insert a `handover_events` row, and — for channel `messenger` only — create a `notifications` row. Test-chat flags appear only in the test chat window.
4. While `ai_paused` is true, `ConversationService` stores customer messages but generates no AI reply.
5. Endpoints (shop users, owner and moderator): `GET /api/v1/notifications` (unread first), `POST /api/v1/notifications/{id}/read`, `POST /api/v1/notifications/read-all`.

## Step 4 — Verify backend
pytest (mock providers): each reason flags the chat, pauses AI and records an event; Messenger-channel chats create notifications, test chats don't; a paused chat gets no AI reply; notifications are shop-scoped.

## Step 5 — Frontend
- Dashboard header: a notification indicator (unread count, polled on an interval) with a dropdown/list of flagged-chat notifications (reason + time) and mark-as-read. Links point to the chat; the inbox page arrives in Prompt 15, so link to its planned route.
- Test chat window: when a test chat is flagged, show a banner with the reason and that the AI is paused for this conversation.

## Step 6 — Integrate & verify
In the test chat, trigger a complaint, a refund request, an off-topic question, a question not in the shop data and a "I want to talk to a person" message; confirm the banner/reason and that the AI stops replying. Verify the notification list with seeded Messenger-channel flagged data. Run build/lint and all tests.

## Must not do
No email/SMS/push notifications, and no inbox page yet (Prompt 15).

## Expected final state
Hard chats are flagged with a clear reason, the AI pauses for them and sends a polite holding reply, handover events are recorded for reports, and sellers see in-dashboard notifications.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 13 — Facebook Page connection
*Layers: backend → frontend · Depends on: 2, 4*

~~~~text
# ShopSathi — Prompt 13: Facebook Page connection

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Let the shop owner connect and disconnect the shop's Facebook Page so ShopSathi can read and reply to its Messenger chats.

## Requirements from the proposal
- FR-07: connect and disconnect a Facebook Page.
- Scope: "Connecting the shop's Facebook Page so the AI can read and reply to Messenger chats." Facebook Messenger only (Instagram DM, WhatsApp etc. out of scope).
- NFR-03: Facebook Page tokens are stored **encrypted**.
- Meta is an external platform; its rules must be followed (Meta Messenger Platform API: Graph API, webhooks).
- Access: owner only.

## Reuse
Auth, `require_owner`, tenant helper, settings, dashboard layout and API client.

## Step 1 — Understand the existing project.

## Step 2 — Backend
1. Settings (env only): `FB_APP_ID`, `FB_APP_SECRET`, `FB_GRAPH_API_VERSION`, `FB_OAUTH_REDIRECT_URI`, `FB_TOKEN_ENCRYPTION_KEY` (Fernet key; document how to generate one), `FRONTEND_URL`.
2. `app/integrations/facebook/graph_client.py`: a small Graph API client (httpx) used here and by Prompt 14.
3. Model and migration `facebook_pages`: id, shop_id (unique, FK cascade: one connected Page per shop), page_id (unique: a Page can't be connected to two shops), page_name, encrypted_page_token, connected_at.
4. `TokenCipher` (Fernet) for encrypt/decrypt. The plaintext token is never logged or returned by any API.
5. Connection flow (Facebook Login):
   - `GET /api/v1/facebook/connect-url` → OAuth URL with a signed, expiring `state` bound to the shop. Request the permissions Messenger needs (e.g. `pages_show_list`, `pages_messaging`, `pages_manage_metadata`).
   - `GET /api/v1/facebook/callback` → validate state, exchange code for a user token (and a long-lived token), fetch the Pages the user manages, keep the result short-term (Redis, with TTL) and redirect to the frontend selection page.
   - `GET /api/v1/facebook/pages/available` → list Page names/ids from that short-term result.
   - `POST /api/v1/facebook/pages/connect` (`page_id`) → store the Page with its encrypted Page token and subscribe the app to the Page's `messages` webhook field (`POST /{page-id}/subscribed_apps`).
   - `GET /api/v1/facebook/page` → connection status (name, id, connected_at; never the token).
   - `POST /api/v1/facebook/page/disconnect` → unsubscribe the app from the Page (best effort) and delete the stored token/row.
6. Clear errors for: missing app configuration, denied permissions, expired state, Page already connected to another shop.

## Step 3 — Verify backend
pytest with the Graph API mocked (e.g. respx): full connect flow; token stored encrypted (raw DB value ≠ token, decrypts correctly); token never in responses; disconnect; Page already used by another shop is rejected; moderator 403; invalid state rejected.

## Step 4 — Frontend
"Facebook Page" settings page (owner only): status card (connected Page name or "Not connected"), "Connect Facebook Page" button, a Page selection list after returning from Facebook, and "Disconnect" with confirmation. Show configuration errors clearly. Responsive.

## Step 5 — Integrate & verify
Run the flow with mocked/dev settings. If a real Facebook developer app and test Page are available (Milestone M2), connect the real test Page and report the result; otherwise state that it is pending real credentials. Run build/lint and all tests.

## Must not do
No webhook handling or message sending (Prompt 14). No Instagram or other channels.

## Expected final state
Owners can connect and disconnect one Facebook Page per shop; Page tokens are stored encrypted; the app is subscribed to the Page's messages.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 14 — Messenger webhook, message processing & reply delivery
*Layers: backend + worker (no new UI) · Depends on: 3, 9–13*

~~~~text
# ShopSathi — Prompt 14: Messenger webhook & reply delivery

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Receive customer messages from Facebook through a webhook, process them with the existing AI pipeline in the background, and send replies back to the same customer through Messenger, following Meta's rules and the plan's monthly limit.

## Requirements from the proposal
- FR-08: receive new Messenger messages through a webhook and send replies back to the same customer.
- Workflow steps 3–8: customer message → Facebook webhook → AI understands → searches shop data → writes reply → sent back through Messenger; buying → order draft; unsure/upset → flag + notify.
- System boundary: ShopSathi starts when a customer message reaches the shop's Facebook Page.
- §3: Redis queues incoming messages; Celery processes them "without slowing the API".
- NFR-01: send an AI reply within 8 seconds for 90% of messages. Record timings so this can be measured (Prompt 22).
- NFR-09 / §5.3 Legal: follow Meta's Messenger rules, including **replying only within the 24-hour messaging window**.
- FR-15: stop AI replies when the shop's monthly message limit is reached.
- Suspended shops (Prompt 2 status) must not get AI replies.
- AI-3 output includes the product photo, so suggestion replies send the photo(s) too.
- Out of scope: voice messages and reading customer-sent photos.

## Reuse (do not duplicate)
`ConversationService.handle_customer_message` (Prompts 9–12), `UsageLimitService` (Prompt 3), `facebook_pages`, `TokenCipher`, Graph client (Prompt 13), handover service (Prompt 12), Celery app, Redis.

## Step 1 — Understand the existing project.

## Step 2 — Backend
1. `GET /api/v1/webhooks/messenger`: Meta verification (`hub.mode`, `hub.verify_token` == `FB_VERIFY_TOKEN` env, return `hub.challenge`).
2. `POST /api/v1/webhooks/messenger`:
   - Verify `X-Hub-Signature-256` with `FB_APP_SECRET`; reject invalid signatures.
   - For each messaging event: ignore echoes (`is_echo`) and events for unknown Page ids; de-duplicate by message `mid` (`messages.external_message_id`).
   - Find or create the chat (shop + customer PSID, channel `messenger`); update `last_customer_message_at`. If the Graph API returns the customer's name with the granted permissions, store it; otherwise leave it empty.
   - Store the customer message with `received_at`, enqueue a Celery task (`process_incoming_message(message_id)`) and **return 200 immediately**.
   - Non-text messages (voice, images, stickers, files): don't interpret them (out of scope). Store a placeholder text so the seller sees that something arrived, and hand the chat over through the existing handover service with reason `low_confidence`.
3. Worker task `process_incoming_message`:
   - Process messages of the same chat in order (a per-chat Redis lock).
   - Skip the AI reply (keep the message for the seller) if: shop suspended; chat `ai_paused`; no connected Page; or `UsageLimitService.can_send_ai_reply` is false (FR-15).
   - Otherwise call `ConversationService` with the stored message (no second copy of the customer message), then check the 24-hour window from the customer's last message (NFR-09). Send the reply with the Send API (`messaging_type: RESPONSE`), plus product photos for suggestions as image attachments (public media URLs).
   - Only after a successful send: set `sent_at` and call `UsageLimitService.record_ai_reply`.
   - Graph API errors: log them, limit retries, and never crash the worker. A failed send must not count against the limit.
4. `app/integrations/facebook/messenger_sender.py`: send text/image functions with the window check built in. **Prompt 15 must reuse this for seller manual replies.**
5. Add a simple Messenger simulation script (`backend/scripts/simulate_messenger_event.py`) that posts a correctly signed sample webhook payload to the local API, for development and testing without Facebook.

## Step 3 — Verify
- pytest: verification handshake; bad signature rejected; echo ignored; duplicate `mid` processed once; unknown Page ignored; message → task → AI reply sent through mocked Send API to the same PSID; paused chat, suspended shop and limit-reached shop get no AI reply; outside 24h → not sent; usage counted only after a successful send; non-text message flagged; timing fields recorded; shop isolation (Page of shop A never routes to shop B).
- Run the simulation script against the running stack with the worker and check DB records and logs.
- If a real Facebook test Page is connected and the backend is reachable over public HTTPS (deployed URL or a tunnel), send real messages from a test account and report the results (Milestone M4: "Working demo on a real Facebook test Page"). If not, state what is pending.

## Must not do
No inbox UI (Prompt 15), no proactive/broadcast/follow-up messages outside the 24-hour window, no other channels.

## Expected final state
Real Messenger messages flow end-to-end: webhook → Redis/Celery → the same AI pipeline as the test chat → reply sent back within Meta's 24-hour window, respecting AI pause, shop suspension and the plan's monthly limit, with timings recorded.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 15 — Chat inbox & human takeover
*Layers: backend → frontend · Depends on: 12, 14*

~~~~text
# ShopSathi — Prompt 15: Chat inbox & human takeover

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Build the inbox where shop users see all Messenger chats (flagged first), read conversations, pause the AI for a chat and reply personally, and turn the AI back on.

## Requirements from the proposal
- FR-10: show all chats in an inbox, with flagged chats at the top.
- FR-11: pause the AI for a single chat and reply manually, and turn it back on.
- Scope "Human takeover": the seller can pause the AI for any chat at any time and reply personally. Figure 1: "Seller takes over — replies by hand".
- Moderators watch chats and handle flagged messages; their interest is a "clear list of chats that need a human".
- NFR-09: manual replies sent through Messenger must also respect the 24-hour window.
- NFR-04: customer details visible only to this shop's users.
- Access: owner and moderator.

## Reuse (do not duplicate)
`chats`, `messages`, flag fields and `notifications` (Prompt 12), `messenger_sender` with the window check (Prompt 14), notification indicator (Prompt 12), suggestion and order-draft data in message extras (Prompts 10–11).

## Step 1 — Understand the existing project.

## Step 2 — Backend (all shop-scoped, `require_shop_user`)
- `GET /api/v1/chats`: channel `messenger` only; flagged chats first (by flagged_at), then by latest activity; filter `flagged | all`; pagination. Each item has customer label, last message preview, flag reason, ai_paused, last activity, and whether the 24-hour window is open.
- `GET /api/v1/chats/{id}`: chat details with messages (customer/AI/seller), including suggestion and order-draft extras.
- `POST /api/v1/chats/{id}/pause` and `/resume`: set `ai_paused`.
- `POST /api/v1/chats/{id}/reply`: seller's manual reply. Only allowed while the AI is paused for that chat. Sent through `messenger_sender`. If outside the 24-hour window, return a clear error and don't send. Store as `sender=seller`. Manual replies are not counted as AI messages.
- `POST /api/v1/chats/{id}/resolve-flag`: mark the flagged chat as handled (clear `is_flagged`) and mark its notifications read. Resuming the AI stays a separate action.

## Step 3 — Verify backend
pytest: ordering (flagged first); test-channel chats never listed; pause/resume; reply rejected when AI not paused; reply rejected outside 24h; reply sent via mocked Send API and stored; moderator allowed; other shop's chat returns 404.

## Step 4 — Frontend
"Inbox" page: chat list (flag badge + reason, AI paused badge, last message, time) with flagged chats on top and a Flagged/All filter; conversation view showing customer, AI and seller messages (suggestion cards and order-draft cards reused from the test chat components); "Pause AI / Resume AI" toggle; reply box enabled only when paused, with a clear notice when the 24-hour window has closed; "Mark flag as handled". Poll for new messages. On phones the list and the conversation are separate screens. Connect the notification links (Prompt 12) to the chat view.

## Step 5 — Integrate & verify
Use the Messenger simulation script (Prompt 14) to create chats, including a flagged one; then in the UI pause, reply, resolve and resume; confirm the backend state and mocked/real Send API calls. Check as owner and as moderator, and at phone width. Run build/lint and all tests.

## Must not do
No chat assignment, tags, canned replies or bulk messaging.

## Expected final state
Owners and moderators work from an inbox with flagged chats on top, can take over any chat, reply personally within Meta's window, and hand it back to the AI.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 16 — Order dashboard & courier CSV export
*Layers: backend → frontend · Depends on: 11*

~~~~text
# ShopSathi — Prompt 16: Order dashboard & courier CSV export

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Build the order dashboard where the seller reviews AI-drafted orders and confirms, edits or cancels each one, and exports confirmed orders as a CSV for the courier.

## Requirements from the proposal
- FR-12: list all order drafts and let the seller confirm, edit or cancel each one.
- FR-13: export confirmed orders as a CSV file with the columns courier services usually need.
- Workflow step 9: "The seller reviews the order draft in the dashboard and confirms it. The confirmed order can be exported for the courier." System boundary: ShopSathi ends when the seller confirms an order; payment, packing and delivery stay with the seller.
- AI-R11: only a human confirms. Moderators "manage orders for the owner".
- AI-R08 phone rule also applies to edited phones.
- Access: owner and moderator.

## Reuse (do not duplicate)
`orders` table (Prompt 11), `normalize_and_validate_bd_phone` from `shopsathi_ai.validators` (the backend may import ai_engine), product data for size/colour validation, order-draft card component, chat view route (Prompt 15).

## Step 1 — Understand the existing project.

## Step 2 — Backend (shop-scoped, `require_shop_user`, `is_test=false` only)
- `GET /api/v1/orders`: filter by status (`draft` default, `confirmed`, `cancelled`), newest first, pagination.
- `GET /api/v1/orders/{id}`: order with link to its chat.
- `PATCH /api/v1/orders/{id}`: edit product, size, colour, quantity, customer name, phone, address **while status is `draft`**. Validate with the same rules as drafting (product belongs to the shop, size/colour in options, quantity > 0, valid BD phone). Changing the product re-snapshots `unit_price` from the catalogue; price itself isn't editable.
- `POST /api/v1/orders/{id}/confirm`: draft → confirmed (`confirmed_at`, `confirmed_by_user_id`).
- `POST /api/v1/orders/{id}/cancel`: draft → cancelled (`cancelled_at`).
- `GET /api/v1/orders/export?from=&to=`: CSV (UTF-8 with BOM so Bangla text opens correctly in Excel) of **confirmed** orders in the date range, with courier-friendly columns taken only from order data: order_id, confirmed_at, customer_name, customer_phone, customer_address, product_name, size, colour, quantity, unit_price, total_price (unit_price × quantity).
- Invalid status transitions return 409 with a clear message.

## Step 3 — Verify backend
pytest: listing excludes test orders and other shops' orders; edit validation (bad phone, bad size); confirm/cancel transitions and 409s; export contains only confirmed orders in range with the exact columns; moderator allowed.

## Step 4 — Frontend
"Orders" page: tabs Draft / Confirmed / Cancelled; order cards/table (responsive); detail view with an edit form (draft only) and Confirm / Cancel buttons with confirmation dialogs; link to the source chat; "Export confirmed orders (CSV)" with a date range picker.

## Step 5 — Integrate & verify
Create drafts through the Messenger simulation script or seeded data, then edit, confirm and cancel in the UI and download the CSV; open it and check columns and Bangla text. Phone width check. Run build/lint and all tests.

## Must not do
No courier booking, delivery tracking, payment status, invoices or stock deduction (out of scope).

## Expected final state
Shop users review, edit, confirm or cancel AI-drafted orders, and confirmed orders export as a courier-ready CSV.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 17 — Reports
*Layers: backend → frontend · Depends on: 14, 15, 16*

~~~~text
# ShopSathi — Prompt 17: Reports

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Build the seller's report page with the core numbers for a chosen date range.

## Requirements from the proposal
- FR-14: show a report with **messages handled by AI, chats handed to humans, orders drafted and orders confirmed**, for a chosen date range.
- Scope: "A simple report showing messages handled, orders drafted, orders confirmed and common questions." (Common questions = the weekly AI summary in Prompt 18, shown on this same page.)
- Access: owner only (access matrix).

## Reuse (do not duplicate)
`messages` (sender `ai`, `sent_at`), `handover_events` (Prompt 12), `orders` (`created_at`, `confirmed_at`, `is_test`), `chats.channel`. Exclude test-chat data everywhere.

## Step 1 — Understand the existing project.

## Step 2 — Backend
- `GET /api/v1/reports/summary?from=YYYY-MM-DD&to=YYYY-MM-DD` (owner only; dates interpreted in Asia/Dhaka):
  - `messages_handled_by_ai`: AI messages successfully sent on channel `messenger` in range.
  - `chats_handed_to_humans`: distinct Messenger chats with a `handover_events` row in range.
  - `orders_drafted`: non-test orders created in range.
  - `orders_confirmed`: non-test orders confirmed in range.
- Validate the range (from ≤ to; sensible maximum span in config).
- Demo data: extend `database/seed/` with fictional demo chats, messages, handover events and orders spread over several weeks for the demo shops, so reports (and Prompt 18 insights) can be demonstrated. Clearly fictional names, and phone numbers that look valid but are fake.

## Step 3 — Verify backend
pytest with fixed fixture data: each metric counted correctly at range boundaries; test-chat data excluded; other shops excluded; moderator 403.

## Step 4 — Frontend
"Reports" page: date range picker (default: last 7 days) and four stat cards with the metrics. Leave a clearly marked section placeholder for "Weekly AI summary" (filled in Prompt 18). Responsive.

## Step 5 — Integrate & verify
Run seed data, open Reports, change ranges and cross-check numbers with direct DB queries. Run build/lint and all tests.

## Must not do
No extra metrics, charts beyond the four numbers, revenue analytics or exports of reports.

## Expected final state
Owners see accurate, shop-scoped counts of AI-handled messages, handovers, drafted and confirmed orders for any date range.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 18 — Weekly AI chat insights
*Layers: ai_engine + backend → frontend · Depends on: 9, 14, 17*

~~~~text
# ShopSathi — Prompt 18: Weekly AI chat insights

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Generate a weekly AI summary of each shop's chats and show it on the Reports page.

## Requirements from the proposal
- AI-6: input is all chats for a week. Output: **a short summary of the top questions and products customers asked about but the shop doesn't have.**
- AI-R12: generate a **weekly** summary of the **top 5 customer questions** and the **most-asked products that the shop does not have**.
- Key feature 10: "Reports and common-question insights (AI summary)". Scope: report includes "common questions".
- §5.3 privacy: send the LLM only what it needs. Customer names, phones and addresses aren't needed for this summary.
- NFR-08: log AI usage per shop.

## Reuse (do not duplicate)
LLM provider and prompt-file pattern (`ai_engine`), `ShopDataGateway` product search (to check whether an asked-about product exists in the catalogue), `messages`/`chats` (channel `messenger` only), `ai_usage_logs`, Celery app, Reports page (Prompt 17).

## Step 1 — Understand the existing project.

## Step 2 — AI engine
`insights.py`: `summarize_week(customer_messages, product_lookup) -> WeeklyInsights`:
- Remove personal data (phone numbers, addresses, names) before sending text to the LLM.
- Handle large weeks by batching (map-reduce style) to stay within model limits.
- Structured output: `top_questions` (up to 5, each with a short description and approximate count) and `requested_products` (product names customers asked for).
- For each requested product, check the shop catalogue through the gateway. Keep only those **not found** as `missing_products`, ordered by how often they were asked.
- Unit tests with mock providers (PII removed, ≤5 questions, existing products excluded from missing list).

## Step 3 — Backend
1. Model and migration `weekly_insights`: id, shop_id (FK cascade), week_start (date, Monday, Asia/Dhaka), top_questions (JSON), missing_products (JSON), created_at; unique (shop_id, week_start).
2. `InsightsService.generate_for_shop(shop_id, week_start)`: loads that week's Messenger customer messages, calls the engine, upserts the row, logs usage (operation `weekly_insights`). Shops with no messages that week get an empty summary.
3. Celery beat schedule: once a week, generate the previous week's insights for all active shops. Add the beat start command to the docs.
4. CLI: `python -m app.cli generate-insights --shop-id <id> --week-start <date>` (for testing and demo).
5. `GET /api/v1/reports/weekly-insights` (list available weeks) and `GET /api/v1/reports/weekly-insights/{week_start}` (owner only).

## Step 4 — Verify backend
pytest (mock providers): generation from seeded chats; uniqueness per shop/week; only that shop's messages used; test-chat messages excluded; moderator 403. With a real key (if available), run the CLI on the demo shop and include the output in the report.

## Step 5 — Frontend
Fill the "Weekly AI summary" section on the Reports page: week selector (from available weeks), top 5 questions list, and "Products customers asked for that you don't have" list. Empty state when no summary exists yet. Responsive.

## Step 6 — Integrate & verify
Generate insights via CLI for the demo shop, view them in the UI, and verify against the seeded chats. Run build/lint and all tests.

## Must not do
No sentiment dashboards, trend charts or automated customer follow-ups (future work).

## Expected final state
Every week each shop gets an AI summary of its top 5 customer questions and most-asked missing products, viewable on the Reports page.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 19 — Platform admin panel
*Layers: backend → frontend · Depends on: 2, 3, 9 (and data from later modules)*

~~~~text
# ShopSathi — Prompt 19: Platform admin panel

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Build the platform admin panel (Figure 2 "Admin panel — Next.js"; application-layer "Plans + admin — limits, usage").

## Requirements from the proposal
- FR-16: the platform admin can **view, suspend and reactivate shops and change their plan**.
- §1.5 Platform administrator: manages shops, plans and limits; watches system health and AI costs; handles abuse reports. §5.3: the admin can suspend shops that break the rules (fake reviews, spam, misleading offers).
- NFR-08: AI API usage is logged per shop so the admin can see **the cost of each shop**.
- Scope: "Subscription plans (Free, Basic, Pro) with monthly message limits, and a platform admin panel."

## Reuse (do not duplicate)
`platform_admin` role and `create-admin` CLI (Prompt 2), `shops.status` and the existing suspended-shop enforcement (login blocked; no AI replies, Prompt 14), plan models, `UsageLimitService` (Prompt 3), `ai_usage_logs` (Prompts 8–18), health endpoint (Prompt 1), Celery app.

## Step 1 — Understand the existing project.

## Step 2 — Backend (all under `/api/v1/admin`, `platform_admin` only; shop users get 403)
- `GET /shops`: name, owner email, plan, status, created_at, connected Page name, AI messages this month vs limit; search by name/email; pagination.
- `GET /shops/{id}`: the above plus product/chat/order counts.
- `POST /shops/{id}/suspend` and `/reactivate`.
- `POST /shops/{id}/plan` (`plan_code`): admin plan change through the existing plan service. It is an admin action, so no simulated payment record.
- `GET /plans` and `PUT /plans/{code}`: view plans and edit each plan's monthly message limit and display price ("manages plans and limits").
- `GET /ai-usage?from=&to=`: per-shop totals from `ai_usage_logs` (tokens by operation, estimated cost) and a platform total.
- `GET /system-health`: API, database, Redis, Celery worker (ping task) status and Celery queue length.
- Every admin action that changes a shop (suspend, reactivate, plan change) is logged with the admin user id and time (a simple `admin_actions` table).

## Step 3 — Verify backend
pytest: non-admin 403 on every admin endpoint; suspend → that shop's users can't log in and Messenger messages get no AI reply; reactivate restores; plan change affects `UsageLimitService` limits; plan limit edit applies; AI cost totals match fixture logs; health reports components.

## Step 4 — Frontend
Admin area under `/admin` with its own layout (separate from the seller dashboard). A `platform_admin` logging in through the existing login page goes to `/admin`; shop users can't open admin routes. Pages: Shops list (search, status badges, actions: suspend/reactivate with confirmation, change plan), Shop detail, Plans (edit limits/prices), AI usage & cost (date range, per-shop table, total), System health. Responsive.

## Step 5 — Integrate & verify
Create an admin via CLI, log in, suspend a demo shop and confirm its owner is blocked, reactivate it, change a plan, edit a limit, and view AI cost and health. Run build/lint and all tests.

## Must not do
No admin access to shop chat conversations, no impersonation, no billing/invoicing, and no abuse-report submission form (the proposal only says the admin handles reports and can suspend shops).

## Expected final state
A working admin panel where the platform admin manages shops (view, suspend, reactivate, change plan), plan limits, sees AI cost per shop, and monitors system health.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 20 — Shop deletion & data-privacy enforcement
*Layers: backend → frontend · Depends on: all data modules (2–19)*

~~~~text
# ShopSathi — Prompt 20: Shop deletion & data privacy

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Let sellers delete their shop, removing all of its data, and verify the privacy rules across the whole system.

## Requirements from the proposal
- §5.3: "Sellers can delete their shop, and all its chats and orders are then removed."
- FR-02: no shop can see another shop's data. §5.3: one shop's data is never used to answer another shop's customers.
- NFR-04: customer names, phone numbers and addresses are visible only to that shop's users and the platform admin.
- §5.3: the LLM gets only what it needs for one reply, not the whole customer history.
- Access: owner only for deletion.

## Reuse (do not duplicate)
All existing models (FK `ON DELETE CASCADE` on `shop_id`), `StorageService` (product photos), Facebook disconnect (Prompt 13), `ChatMemoryService` Redis keys (Prompt 9), auth/token revocation (Prompt 2).

## Step 1 — Understand the existing project
List every table that holds shop data and confirm each cascades from `shops`. Fix any that don't, with a migration (only for this purpose).

## Step 2 — Backend
- `DELETE /api/v1/shop` (owner only): requires the owner's current password and the exact shop name as confirmation. In order: disconnect the Facebook Page (best effort), delete product photo files, delete Redis keys for the shop's chats, delete the shop row (cascading users, products, policies, embeddings, chats, messages, orders, notifications, handover events, usage, insights, AI usage logs), and revoke the current token.
- Privacy checks to implement or fix where missing:
  - A **cross-tenant test sweep**: for every shop-scoped endpoint, a user of shop B requesting shop A's resource ids gets 404/403.
  - No customer phone/address/name, password, JWT or Page token appears in application logs (check logging calls; mask where needed).
  - The LLM call payloads in `ConversationEngine` contain only recent turns plus retrieved facts (a test asserting the turn limit).

## Step 3 — Verify backend
pytest: deleting shop A removes all its rows (checked table by table) and files, while shop B's data is untouched; wrong password or name rejected; moderator 403; the cross-tenant sweep passes; the log-masking test passes.

## Step 4 — Frontend
A "Delete shop" danger-zone section in the owner's settings: explains that all products, chats and orders will be removed permanently; asks for the password and the shop name; after success, logs out and goes to the sign-up page.

## Step 5 — Integrate & verify
Create a throwaway shop with products, chats and orders, delete it through the UI, and confirm in the DB that nothing remains. Run build/lint and all tests.

## Must not do
No soft-delete/restore, data export or account recovery features.

## Expected final state
Owners can permanently delete their shop with all its data; tenant isolation and personal-data handling are verified by automated tests across all modules.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 21 — AI evaluation harness (labelled test set & accuracy measurement)
*Layers: independent `evaluation/` component · Depends on: 9–12*

~~~~text
# ShopSathi — Prompt 21: AI evaluation harness

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Create an independent `evaluation/` component that measures the AI against the proposal's accuracy targets using a labelled test set.

## Requirements from the proposal
- §2: AI targets are measured on a test set of **200 real-style customer messages that the team collects and labels**. (M1: collected from public shop pages and by role-play; M5: label the test set, measure intent, answer and order accuracy, improve prompts.)
- AI-R01: intent accuracy **≥ 85%** (price, size/stock, delivery, suggestion, order, complaint, other).
- AI-R03: **≥ 95%** of prices and stock values in AI replies match the catalogue exactly.
- AI-R07: **≥ 90%** of order fields (product, size, colour, quantity, name, phone, address) correct.
- AI-R06: never suggest a zero-stock product. AI-R08: invalid phones are re-asked. AI-R04/AI-R10: flagging cases.
- §5.3 fairness: the test set includes Bangla script, English and Banglish, and accuracy is **reported separately for each one**.
- Tools: pytest and "our own labelled test set".

## Architecture
`evaluation/` is a separate folder at the repository root with its own `requirements.txt`. It imports only `shopsathi_ai` (the AI engine), **not** `backend/`. It uses an in-memory evaluation gateway built from a fixture catalogue and policy, so it runs without the backend or database.

## Step 1 — Understand the existing project
Read the `ConversationEngine`, understanding, suggestion, extraction and handover interfaces.

## Step 2 — Build the harness
1. `evaluation/fixtures/shop_catalogue.json` and `shop_policy.json`: a fictional evaluation shop (include zero-stock items, several sizes/colours, areas with charges).
2. Data format `evaluation/data/README.md` plus a JSONL schema, one record per case with: `id`, `language` (`bangla` | `english` | `banglish`), `type` (`intent` | `answer` | `order` | `suggestion` | `handover`), `messages` (one or more turns), and the labels for that type (expected intent; expected price/stock values; expected order fields; expected flag/reason).
3. `evaluation/data/sample_cases.jsonl`: about 20 **sample** cases covering every type and all three languages, using the proposal's examples. Mark them clearly as samples for testing the harness. **Do not invent the 200-message test set.** The team collects and labels it (`evaluation/data/test_set.jsonl`, git-ignored if it contains real messages).
4. `evaluation/run_eval.py --data <file> --provider <name>`: runs each case through `ConversationEngine` with the fixture gateway and computes intent accuracy, price/stock exact-match rate, order-field accuracy, zero-stock suggestion violations, phone re-ask correctness and flag precision/recall, **overall and per language**. Compare each to its target (pass/fail).
5. Output a Markdown and JSON report to `evaluation/reports/` (timestamped), including the per-case failures for prompt improvement.
6. pytest for the metric functions themselves.

## Step 3 — Verify
Run the harness on the sample file with the mock provider (it must run end-to-end), and with a real provider if a key is available. Include the produced report in your summary. Run the metric tests.

## Must not do
No changes to AI behaviour in this prompt (prompt tuning is the team's M5 work and should be done as separate, deliberate changes). No fabricated "real" test data.

## Expected final state
A self-contained evaluation tool that loads a labelled JSONL test set, runs the AI engine, and reports every proposal accuracy target overall and per language, ready for the team's 200-message set.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 22 — Performance, load & security testing
*Layers: test scripts (backend side) · Depends on: 1–20*

~~~~text
# ShopSathi — Prompt 22: Performance, load & security testing

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Measure and verify the non-functional requirements on the complete system (Milestone M5 "security and load tests"), and fix defects found **in existing behaviour** without adding features.

## Requirements from the proposal
- NFR-01: AI reply within **8 seconds for 90%** of messages.
- NFR-07: support at least **20 shops and 50 chats at the same time** during testing.
- NFR-03: passwords hashed, all traffic HTTPS, Facebook Page tokens stored encrypted.
- NFR-04: customer personal data visible only to that shop's users and the admin.
- NFR-09: replies only within the 24-hour messaging window.
- FR-15: AI replies stop at the monthly limit.
- M5 deliverable: test report.

## Reuse
Messenger simulation script (Prompt 14), timing fields `received_at`/`sent_at`, seed CLI, existing pytest suites, cross-tenant sweep (Prompt 20).

## Step 1 — Understand the existing project.

## Step 2 — Load & performance
1. `backend/scripts/loadtest/`: a Python (asyncio + httpx) load script that creates or uses 20 demo shops with connected fake Pages and sends signed webhook events for **50 concurrent chats**.
2. Make the Graph API base URL configurable (if it isn't already) and add a tiny local **stub Send API server** for load tests only, so no real Facebook calls are made.
3. Run it with the Celery worker(s) and report: p50/p90/p99 time from `received_at` to `sent_at`, errors, and the queue backlog. Run once with the mock LLM (system overhead) and, if a key is available, once with the real LLM (true NFR-01 check, smaller run to control cost).
4. If NFR-01/NFR-07 fail, fix configuration or existing code inefficiencies (e.g. worker concurrency, DB indexes, connection pooling) and re-measure. Don't change product behaviour.

## Step 3 — Security checks (automated where possible, in `backend/tests/security/`)
- Passwords stored as bcrypt hashes; the JWT signature is verified and tampered or expired tokens are rejected; logout revocation works.
- Page tokens encrypted at rest; no token or secret in API responses or logs; no secrets committed (scan the repo for keys and `.env` files).
- Webhook signature enforcement; rate limits on login/password reset.
- Role checks: moderator vs owner vs admin on every endpoint (generate the list from the router).
- Cross-tenant sweep passes (Prompt 20).
- The 24-hour window and monthly limit are enforced under load.
- HTTPS: document that production runs behind HTTPS (Prompt 23) and make sure the backend honours forwarded-proto headers and that the CORS origins are restricted to the frontend URL.

## Step 4 — Report
Write `docs/TEST_REPORT.md` with: environment, load-test setup, latency results vs NFR-01, concurrency results vs NFR-07, security checklist results, issues found and fixes made, and a link to the latest AI evaluation report (Prompt 21) if one exists.

## Must not do
No new product features. No load tests against real Facebook or with unlimited real-LLM spend.

## Expected final state
Repeatable load and security test scripts, measured results for NFR-01/NFR-07, passing security checks, and a test report document.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

### Prompt 23 — Docker, deployment & user guide
*Layers: packaging for all components · Depends on: 1–22*

~~~~text
# ShopSathi — Prompt 23: Docker, deployment & user guide

**Ground rules (read first)**
- Project: **ShopSathi**, an AI sales agent SaaS for small Facebook/Instagram shops in Bangladesh (SE-331 proposal). The proposal is the only source of requirements. Implement exactly what this prompt asks. Do not add features, roles, screens, workflows or business logic that aren't listed here. Use the proposal's terms (shop owner/seller, Moderator, platform admin, order draft, test chat window, flagged chat, human takeover, shop policy, Free/Basic/Pro).
- Before changing anything, inspect the existing repository: `README.md`, `docs/CONVENTIONS.md`, `docs/PROGRESS.md`, and the existing code in `backend/`, `ai_engine/`, `frontend/` and `database/`. Reuse existing models, services, the API client, layouts and components. Do not create duplicate implementations.
- Keep the structure separated: `backend/` (FastAPI, Python), `ai_engine/` (independent Python package; it must never import from `backend/`), `frontend/` (Next.js + TypeScript + Tailwind CSS), `database/` (local demo database setup and seed data), `docs/`. Follow the naming, API, database and auth conventions in `docs/CONVENTIONS.md`.
- Work only on this task. Do not modify unrelated modules, and do not rename, restructure or redesign completed work unless this prompt says to. Preserve existing functionality: all existing tests must still pass.
- Scope every shop-owned table and query by `shop_id` (FR-02). Never hardcode secrets or credentials; read them from environment variables and document them in the matching `.env.example`.
- Order of work: **understand the existing project → implement backend → verify backend → implement frontend → integrate with the backend → verify the complete module → report → STOP.** Do not start the frontend until the backend part is implemented and its tests pass.
- Git: you may run `git status`, `git diff` and `git log` to inspect. **Do not create any Git commit. Do not run `git commit`. Do not commit on my behalf.**

## Task
Package ShopSathi for a live demo deployment with HTTPS, and write the user guide (Milestone M6: "deploy live; user guide").

## Requirements from the proposal
- §3 Deployment: Docker; Render, Railway or a small VPS for the backend; Vercel for the frontend; hosting a live demo **with HTTPS (needed for Facebook webhooks)**.
- NFR-02: available 99% of the time during the demo and testing period.
- NFR-03: all traffic uses HTTPS.
- NFR-05: a new seller can sign up, add 5 products and test the AI in **under 15 minutes**.
- NFR-06: the dashboard works on mobile phone screens and laptops.
- M6 deliverables: live system, user guide.

## Reuse
All existing components, env examples, health endpoint, CLI (migrations, seed, create-admin), Celery app and beat schedule.

## Step 1 — Understand the existing project.

## Step 2 — Containerise (keep components separate)
- `backend/Dockerfile`: one image that installs `ai_engine` and runs as API (uvicorn), worker (Celery) or beat by command. Non-root user, no secrets baked in.
- `frontend/Dockerfile` (for VPS option; Vercel builds from source).
- `deploy/docker-compose.prod.yml` (VPS option): api, worker, beat, frontend, PostgreSQL+pgvector, Redis, and a reverse proxy with automatic HTTPS. The `database/docker-compose.yml` stays the local development setup and is not changed.
- Run Alembic migrations on release/startup of the API service.
- Media storage path for product photos on a persistent volume.

## Step 3 — Hosting configuration & docs (`docs/DEPLOYMENT.md`)
- Backend on Render/Railway (or VPS) and frontend on Vercel. If you add platform config files (e.g. `render.yaml`), put them under `deploy/`. Use a managed PostgreSQL with pgvector and a Redis instance, and list every env variable per component.
- Facebook setup steps: app config, OAuth redirect URI, webhook callback URL (`https://<backend>/api/v1/webhooks/messenger`), verify token, subscribed fields, test Page.
- Production settings: HTTPS only, CORS limited to the frontend domain, secure cookies/headers where used, debug off.
- Availability (NFR-02): configure the platform health check against `/api/v1/health`, restart policies for api/worker/beat, and describe how to monitor uptime during the demo period.
- First-run steps: migrations, `create-admin`, optional demo seed.

## Step 4 — User guide (`docs/USER_GUIDE.md`)
Plain-language, step-by-step guide covering only existing features. For sellers: sign up and choose a plan, staff (Moderator) accounts, products and CSV/Excel import, shop policy, test chat window, connecting the Facebook Page, inbox and human takeover, flagged chats and notifications, orders (confirm/edit/cancel) and CSV export, reports and weekly AI summary, deleting the shop. For the platform admin: shops, plans and limits, AI costs, system health. Include the AI's limits from the proposal (it doesn't confirm orders, change prices, give discounts or take payment).

## Step 5 — Verify
- Build all images and run the production compose stack locally. Check health, log in, and run the Messenger simulation script against it.
- If deployment credentials are available, deploy and confirm HTTPS works, the webhook is verified by Meta, and a real test message gets a reply. Otherwise state exactly what is pending.
- **NFR-05 walkthrough:** time a fresh run of sign up → add 5 products → chat in the test window, and record the time in `docs/TEST_REPORT.md`.
- **NFR-06 check:** open every seller and admin page at phone width (~375px) and laptop width (~1366px); fix layout bugs only.
- Run all backend, ai_engine and evaluation tests plus the frontend build/lint one final time.

## Must not do
No new features, no native mobile app, no changes to business logic beyond deployment configuration and layout fixes.

## Expected final state
ShopSathi runs as separated containers/services with HTTPS, is deployable to Render/Railway (or a VPS) plus Vercel, has deployment and user documentation, and the NFR-05/NFR-06 checks are recorded.

**Finish**
1. Add a short entry for this prompt to `docs/PROGRESS.md`: what was built, new tables/endpoints/pages, new environment variables, and how to run the tests. Update `docs/CONVENTIONS.md` only if this prompt introduced a new shared convention.
2. Report clearly: files created or changed, what was implemented, which commands and tests you ran with their results, and anything you couldn't verify and why.
3. Then STOP. Do not start the next module or any unrelated work.

**Do not create any Git commit. Do not run `git commit`. I will manually review and commit the changes myself.**
~~~~

---

## Final completeness check (proposal → prompt)

### Functional requirements
| ID | Requirement (short) | Prompt |
|---|---|---|
| FR-01 | Sign up, log in, log out, reset password by email | 2 |
| FR-02 | Shop data separation | 2 (foundation), applied in every prompt, verified 20 & 22 |
| FR-03 | Staff accounts with "Moderator" role | 4 |
| FR-04 | Products CRUD with up to 5 photos | 5 |
| FR-05 | CSV/Excel import with failed-row report | 6 |
| FR-06 | Shop policies (delivery charge by area, time, returns, payment options) | 7 |
| FR-07 | Connect/disconnect Facebook Page | 13 |
| FR-08 | Webhook in, reply to the same customer | 14 |
| FR-09 | Test chat window | 9 (extended in 10, 11, 12) |
| FR-10 | Inbox with flagged chats on top | 15 |
| FR-11 | Pause AI per chat, reply manually, turn back on | 15 (auto-pause on handover in 12) |
| FR-12 | Order drafts: confirm, edit, cancel | 16 |
| FR-13 | Export confirmed orders as courier CSV | 16 |
| FR-14 | Date-range report (AI messages, handovers, drafted, confirmed) | 17 |
| FR-15 | Free/Basic/Pro with monthly limits; stop AI at limit | 3 (plans + service), 14 (enforcement), 19 (admin limits) |
| FR-16 | Admin: view, suspend, reactivate shops, change plan | 19 (suspension enforcement set up in 2 and 14) |

### AI requirements and features
| ID | Prompt |
|---|---|
| AI-1 / AI-R01 intent understanding | 9, measured in 21 |
| AI-R02 Bangla/English/Banglish, same style | 9, per-language measurement in 21 |
| AI-2 / AI-R03 catalogue-grounded replies | 8 (RAG), 9, measured in 21 |
| AI-R04 "I'll check with the shop" + flag | 9 (reply), 12 (flag) |
| AI-3 / AI-R05 / AI-R06 suggestions, never zero-stock | 10, measured in 21 |
| AI-4 / AI-R07 / AI-R08 / AI-R09 order extraction, phone check, missing fields | 11, measured in 21 |
| AI-5 / AI-R10 smart handover + notification | 12 |
| AI-R11 no confirming orders, no price changes or discounts | 9, 11, 16 (only humans confirm) |
| AI-6 / AI-R12 weekly top-5 questions + missing products | 18 |
| AI-R13 embeddings updated within 1 minute | 8 |
| AI techniques: LLM + structured JSON, RAG, semantic search, tools (search products, check stock, get delivery charge, update order draft), Bangla AI | 8, 9, 10, 11 |

### Non-functional requirements
| ID | Prompt |
|---|---|
| NFR-01 speed (8 s / 90%) | 14 (timings), 22 (measurement) |
| NFR-02 availability 99% | 23 |
| NFR-03 hashing, HTTPS, encrypted Page tokens | 2, 13, 22, 23 |
| NFR-04 privacy of customer data | 2, 4, 15, 20, 22 |
| NFR-05 onboarding under 15 minutes | 23 (timed walkthrough) |
| NFR-06 responsive dashboard | every frontend step; final check in 23 |
| NFR-07 20 shops / 50 concurrent chats | 22 |
| NFR-08 AI usage logged per shop, admin sees cost | 8, 9, 11, 18 (logging), 19 (admin view) |
| NFR-09 24-hour messaging window | 14, 15, 22 |

### Scope, workflow, ethics and architecture
| Item from proposal | Prompt |
|---|---|
| Workflow steps 1–9 (sign up and plan → products/policy → embeddings → webhook → understand → search → reply → order draft → flag → seller confirms and exports) | 2–3, 5–7, 8, 14, 9, 8–9, 9, 11, 12, 16 |
| Simulated plans/payments, no real gateway | 3 |
| First AI reply discloses automatic assistant and that a person can be requested | 9 (disclosure), 12 (`human_requested` flag) |
| LLM gets only what it needs for one reply | 9, verified 20 |
| Seller can delete shop; chats and orders removed | 20 |
| Fairness: suggestions only from stated needs and stock; per-language accuracy reported | 10, 21 |
| Admin can suspend rule-breaking shops (abuse) | 19 |
| Five-layer architecture; AI engine as an independent layer | 1 (structure), kept in every prompt |
| Tech stack (FastAPI, Celery+Redis, PostgreSQL+pgvector, LangChain, OpenAI/Gemini, multilingual embeddings, JWT+bcrypt, pandas/openpyxl, pytest, Next.js+Tailwind, Docker, Render/Railway/Vercel) | 1, then where each is used |
| Test set of 200 labelled messages (collected by the team) | 21 (harness and format; the team supplies the data) |
| M5 test report, M6 user guide and live deployment | 22, 23 |

### Out of scope (deliberately not in any prompt)
Real bKash/Nagad/card payments · courier booking and delivery tracking · warehouse stock management · WhatsApp, Instagram DM, website chat, phone calls · voice messages and reading customer photos · native mobile app · ads and marketing campaigns · all §5.4 Future Work items.

### Interpretation notes (where the proposal was silent, the minimal reading taken)
1. **Handover pauses the AI for that chat** (Prompt 12). "Pass the chat to the seller" is read as the AI stopping until a shop user resumes it (FR-11).
2. **Message-limit counting:** one count = one AI reply sent on Messenger. Test chat messages aren't counted. Calendar-month reset. This is recorded in `CONVENTIONS.md` so the team can change it.
3. **Test chat data** (chats, order drafts, flags) stays in the test window and is excluded from the inbox, order dashboard, CSV export, reports and insights.
4. **Plan prices and limit numbers** are placeholders. The proposal gives none.
5. **Staff accounts:** only add and list, as FR-03 says. The proposal doesn't mention removing a moderator. If you want that, it's a team decision to add.
6. **"Handles abuse reports"** is covered by the admin's suspend/reactivate (§5.3). No report-submission form is created because the proposal doesn't describe one.
7. **"Manages plans and limits"** (admin role) is read as editing each plan's message limit and display price, in addition to changing a shop's plan (FR-16).
8. **Non-text Messenger messages** (voice/photos are out of scope) are stored as a placeholder and handed to the seller rather than interpreted.
9. **Seller notification** is in-dashboard only. The proposal doesn't name email/SMS/push.
10. **Courier CSV columns** use only order data. Delivery charge isn't included because it isn't one of the order-draft fields in AI-4.
