# Progress

## Prompt 1 — Project foundation & local demo environment
**Built:** separated repo structure; `database/` (Postgres 16 + pgvector, Redis 7 via Docker Compose, init SQL creating `shopsathi_test`); backend skeleton (FastAPI, config, sync SQLAlchemy, Redis factory, Alembic with an empty initial migration, Celery with a `ping` task, `app.cli`); `ai_engine` package (settings, provider interfaces, mock providers, factory, empty `ShopDataGateway` placeholder); Next.js frontend with a typed API client and a placeholder page showing backend health.

**Tables:** none (empty initial migration). **Endpoints:** `GET /api/v1/health`. **Pages:** `/` (placeholder).

**Env vars:** see `docs/CONVENTIONS.md` and each `.env.example`.

**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 2 — Shop accounts, authentication & multi-tenant separation
**Built:** shop sign-up/login/logout/password reset by email (FR-01); JWT + bcrypt; Redis token denylist and rate limits; `EmailService` (SMTP or console log); security dependencies and tenant-scoping helper (FR-02); suspended-shop blocking; platform admin via CLI; fictional demo shops seed; frontend auth pages, auth module and protected dashboard shell.

**Tables (migration 0002):** `shops`, `users`, `password_reset_tokens`.
**Endpoints:** `POST /api/v1/auth/signup`, `/login`, `/logout`, `GET /auth/me`, `POST /auth/password-reset/request`, `/auth/password-reset/confirm`.
**Pages:** `/signup`, `/login`, `/forgot-password`, `/reset-password?token=`, `/dashboard` (placeholder).
**CLI:** `python -m app.cli create-admin --email ...` (password from `ADMIN_PASSWORD` or prompt); `python -m app.cli seed` (idempotent; demo password from `DEMO_PASSWORD` or generated and printed once).
**New env vars (backend/.env.example):** `JWT_SECRET` (required), `ACCESS_TOKEN_EXPIRE_MINUTES`, `PASSWORD_MIN_LENGTH`, `PASSWORD_RESET_EXPIRE_MINUTES`, `LOGIN_RATE_LIMIT`, `LOGIN_RATE_WINDOW_SECONDS`, `RESET_RATE_LIMIT`, `RESET_RATE_WINDOW_SECONDS`, `SMTP_HOST/PORT/USERNAME/PASSWORD/FROM/USE_TLS`, `ADMIN_PASSWORD`, `DEMO_PASSWORD`.
**Upgrade steps:** set `JWT_SECRET` in `backend/.env`, `pip install -r requirements.txt`, `alembic upgrade head`.
**Run tests:** `cd backend && pytest` (DB + Redis running); `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 3 — Subscription plans & message-limit service
**Built:** Free/Basic/Pro plans (placeholder prices/limits in `database/seed/plans.json`), plan choice at sign-up, simulated payment for paid plans, owner-only plan change, per-shop monthly usage and a reusable `UsageLimitService` (not yet wired into any message flow; Prompt 14 does that). Frontend: plan picker + "Simulated payment — no real money is charged" step on sign-up, and a "My plan" dashboard page.

**Tables (migration 0003):** `plans` (three placeholder rows inserted so existing shops default to Free), `simulated_payments`, `shop_message_usage` (unique per shop+period); new column `shops.plan_id` (required FK).
**Endpoints:** `GET /api/v1/plans` (public); `POST /auth/signup` now accepts `plan_code` (default `free`) and `simulated_payment_confirmed`; `GET /api/v1/shop/plan`; `POST /api/v1/shop/plan/change` (owner only).
**Pages:** `/signup` (plan step), `/dashboard/plan`.
**CLI:** `python -m app.cli seed` now also upserts the plans.
**New env vars:** none. New dependency: `tzdata` (Asia/Dhaka on Windows).
**Upgrade steps:** `pip install -r requirements.txt`, `alembic upgrade head`, `python -m app.cli seed`.
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 4 — Staff accounts (Moderator role) & role-based access
**Built:** owner can add and list Moderator accounts; role constants and reusable `require_owner` / `require_shop_user` dependencies; access matrix documented in `docs/CONVENTIONS.md`; plan-change endpoint now uses `require_owner`. Frontend: owner-only **Staff** page, role-aware dashboard nav, and a `RoleGuard`/`OwnerOnly` component that shows "Not allowed" on direct URL access (applied to Staff and My plan).

**Tables:** none (uses `users` with role `moderator`; no migration).
**Endpoints:** `GET /api/v1/shop/staff`, `POST /api/v1/shop/staff` (both owner only).
**Pages:** `/dashboard/staff`; `/dashboard/plan` is now owner-only in the UI.
**New env vars:** none.
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 5 — Product catalogue
**Built:** owner-only, shop-scoped product catalogue (name, description, price, sizes, colours, stock, up to 5 photos); `StorageService` for local photo storage served at `/media`; `ProductService` with a clearly named hook point (`product_hooks`) for Prompt 8 embeddings; demo products for the two demo shops. Frontend: Products list (table on laptops, cards on phones, search, pagination, inline delete confirmation), add/edit form with chip inputs for sizes/colours and photo upload with previews and remove.

**Tables (migration 0004):** `products`.
**Endpoints (`/api/v1/products`, owner only):** `GET` (search `q`, `page`, `page_size`), `POST`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}`, `POST /{id}/photos` (multipart `files`), `DELETE /{id}/photos/{index}`. Static files at `/media/...`.
**Pages:** `/dashboard/products`, `/dashboard/products/new`, `/dashboard/products/[id]`.
**New env vars (backend):** `BACKEND_PUBLIC_URL`, `MEDIA_ROOT`, `MAX_UPLOAD_MB`. New dependency: `python-multipart`.
**Seed:** `database/seed/demo_products.json`, loaded by `python -m app.cli seed` (idempotent by product name per shop).
**Upgrade steps:** `pip install -r requirements.txt`, `alembic upgrade head`, `python -m app.cli seed`.
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 6 — Product import from CSV/Excel
**Built:** owner-only bulk import of products from `.csv`/`.xlsx` (pandas + openpyxl) with a per-row failure report (row number, name, reasons), a downloadable template, and a sample file with valid and invalid rows. Rows reuse the Prompt 5 validation (`ProductImportRow` extends `ProductIn`) and `ProductService.create` (so the product-change hook fires). Frontend: "Import from CSV/Excel" panel on the Products page (file picker, template download, upload progress, result summary and failed-rows table) that refreshes the list.

**Tables:** none (no migration).
**Endpoints (owner only):** `POST /api/v1/products/import` (multipart `file`), `GET /api/v1/products/import/template`.
**Pages:** import panel on `/dashboard/products`.
**New env vars (backend):** `MAX_IMPORT_MB` (2), `MAX_IMPORT_ROWS` (1000).
**Sample file:** `database/seed/sample_products_import.csv` (11 rows: 4 import, 7 fail at rows 4, 5, 6, 7, 8, 9, 12).
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 7 — Shop policy manager
**Built:** owner-only shop policy (delivery charge by area, delivery time, return rules, payment options) with whole-policy replace on save, a tested `PolicyService.get_delivery_charge` lookup for the AI (exact/normalised match, never guesses), and a `policy_changed` hook point for Prompt 8. Demo policies for the two demo shops. Frontend: "Shop policy" page with add/remove area rows, three text fields and save feedback.

**Tables (migration 0005):** `shop_policies`, `delivery_areas` (unique index on `shop_id, lower(area_name)`).
**Endpoints (owner only):** `GET /api/v1/shop/policy` (empty defaults if never saved), `PUT /api/v1/shop/policy`.
**Pages:** `/dashboard/policy`.
**New env vars:** none.
**Seed:** `database/seed/demo_policies.json`, loaded by `python -m app.cli seed` (skips shops that already have a policy).
**Upgrade steps:** `alembic upgrade head`, `python -m app.cli seed`.
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 8 — Embeddings & RAG retrieval (per shop)
**Built:**
- AI engine: embedding providers behind `EmbeddingProvider` returning vectors + token usage (`openai` text-embedding-3-small over HTTPS, `local` sentence-transformers model, `mock`); `chunking.py` (product and policy chunks with `source_type`/`source_id`); `ShopDataGateway` protocol (`vector_search`, `log_ai_usage`); `retrieval.retrieve(shop_id, query_text, top_k, embedder=, gateway=)`.
- Backend: `embedding_chunks` (pgvector, HNSW cosine index) and `ai_usage_logs`; `BackendShopDataGateway` (always filtered by `shop_id`); `EmbeddingService`; Celery tasks `embed_product`, `delete_product_embeddings`, `embed_policy` wired into the product/policy hooks (manual edits, CSV import, policy save); per-shop cost logging; CLI `reembed-shop`, `reembed-all`; `seed` queues embeddings for demo products and policies.

**Tables (migration 0006):** `embedding_chunks`, `ai_usage_logs`.
**Endpoints / pages:** none (no frontend changes).
**Background jobs:** `shopsathi.embed_product`, `shopsathi.delete_product_embeddings`, `shopsathi.embed_policy`. The Celery worker must be running.
**CLI:** `python -m app.cli reembed-shop --shop-id N`, `python -m app.cli reembed-all [--resize-column]`.
**New env vars (backend):** `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL` (now read by the backend and passed to the AI engine), `AI_COST_RATES`, `CELERY_TASK_ALWAYS_EAGER` (tests only). New dependency of `ai_engine`: `httpx`; optional extra `local` (sentence-transformers).
**Scripts:** `backend/scripts/check_embedding_latency.py` (AI-R13 timing), `backend/scripts/check_semantic_search.py` (needs a real provider).
**Upgrade steps:** `pip install -r requirements.txt`, `alembic upgrade head`, `python -m app.cli reembed-all` (builds embeddings for existing products/policies), start the Celery worker.
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 9 — AI chat replies & Test chat window
**Built:**
- AI engine: `LLMProvider` with token usage (`openai` GPT-4o-mini and `gemini` Flash through LangChain in JSON mode, plus a rule-based `mock` test double); `language.py`; `understanding.py` (validated intent/entities, one retry); `tools.py`; `reply.py` (answer only from facts, number-grounding check, one regeneration, then the "I'll check with the shop" fallback); `engine.py` (`ConversationEngine.process_customer_message` -> `EngineResult` with reply, intent, entities, confidence, style, handover, extras, usage); prompt files in `shopsathi_ai/prompts/`.
- Backend: `chats` and `messages` tables; gateway tool methods; Redis `ChatMemoryService`; `ConversationService.handle_customer_message` (the single entry point for Prompt 14); owner-only test-chat API; usage logging (`intent`, `chat_reply`, `embedding`).
- Frontend: "Test chat" page (Messenger-style bubbles, thinking indicator, new conversation, previous conversations, visible "nothing is sent to Facebook" label, responsive).

**Tables (migration 0007):** `chats`, `messages`.
**Endpoints (owner only):** `POST /api/v1/test-chat/sessions`, `GET /api/v1/test-chat/sessions`, `GET /api/v1/test-chat/sessions/{id}/messages`, `POST /api/v1/test-chat/sessions/{id}/messages`.
**Pages:** `/dashboard/test-chat`.
**New env vars (backend):** `CHAT_MEMORY_TURNS`, `CHAT_MEMORY_TTL_SECONDS`, `RAG_MIN_SCORE`, `RAG_MIN_PRODUCT_SCORE` (and `LLM_PROVIDER` / `LLM_MODEL` now select real models; cost rates for gpt-4o-mini and gemini-2.0-flash added to `AI_COST_RATES`). New optional `ai_engine` extras: `openai`, `gemini`, `llm`.
**Scripts:** `backend/scripts/check_chat_examples.py` (proposal example messages + reply time; needs a real LLM key to judge quality).
**Upgrade steps:** `pip install -r requirements.txt` (and `pip install -e "../ai_engine[llm]"` for real models), `alembic upgrade head`.
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

**Prompt 9 — verification with a real model (gpt-4o-mini + text-embedding-3-small):** the proposal's example messages were run against the demo shop: replies used catalogue prices/stock exactly, answered in the customer's style (Banglish, English, Bangla script) and unknown questions got "I'll check with the shop". Reply time 1.9-4.5 s (target 8 s). Findings fixed: product/colour are now normalised to English by the understanding step (`product_name_en`) so Bangla-script questions find products; "eta" is resolved to the most recent product; replies use ASCII digits unless the customer wrote Bangla. `backend/scripts/debug_chat.py` prints what the AI understood and retrieved for any messages.
