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
- **Embedding hook (Prompt 8):** `product_hooks.product_changed(shop_id, product_id)` and `product_hooks.product_deleted(shop_id, product_id)` in `app/services/products.py` are called after every create/update/photo change and after delete. They queue the Celery embedding jobs (see "Embeddings & retrieval").

## Product import (CSV / Excel)
- `POST /api/v1/products/import` (owner only) reads `.csv` (UTF-8) or `.xlsx` with pandas/openpyxl. Columns: `name`, `description`, `price`, `sizes`, `colours`, `stock`, `photos`; only `name` and `price` are required, extra columns are ignored. Sizes/colours split on `|` or `,`; photos (http(s) URLs, max 5) split on `|`. `GET /api/v1/products/import/template` returns a template CSV.
- Row validation is the manual-product validation (`ProductImportRow` extends `ProductIn`); rows are created through `ProductService.create`, so the change hook fires for each. Do not add a second validation path.
- Row numbers in failure reports are spreadsheet row numbers (the header is row 1). Fully blank rows are ignored. Failed rows are skipped; the rest are saved (each row is its own transaction).
- Imported `photos` are stored as the given external URLs; `StorageService.url()` returns them unchanged and `delete()` never touches them. Uploaded photos still use storage keys.
- Limits: `MAX_IMPORT_MB` (default 2) and `MAX_IMPORT_ROWS` (default 1000); larger files get 413.

## Shop policy
- `shop_policies` (one row per shop, `shop_id` unique) holds delivery time, return rules and payment options; `delivery_areas` (shop-owned, `shop_id` FK cascade + index) holds area name and charge (BDT, >= 0). Area names are unique per shop, ignoring case (DB index on `lower(area_name)`) and also ignoring punctuation/spacing (validated with `normalise_area`). Endpoints `GET`/`PUT /api/v1/shop/policy` are owner-only; `PUT` replaces the whole policy including the areas list.
- **Delivery charge lookup for the AI (Prompt 9):** `PolicyService.get_delivery_charge(area_text)` returns `DeliveryCharge(found, area_name, charge)`. It matches only an exact area name after normalisation (case, punctuation and extra spaces ignored). No partial or fuzzy matching: the AI tool must extract the area name itself and treat `found=False` as "ask the seller / don't guess".
- **Embedding hook (Prompt 8):** `policy_hooks.policy_changed(shop_id)` in `app/services/policy.py` is called after every save. It queues the `embed_policy` job (see "Embeddings & retrieval").

## Embeddings & retrieval (RAG)
- **Layering:** `ai_engine` holds the pure logic (`chunking.py`, `retrieval.py`, embedding providers, the `ShopDataGateway` protocol). The backend implements the gateway (`app/ai_adapters/gateway.py`) and does all database work (`app/services/embeddings.py`). The backend builds the AI engine's settings from its own `.env` (`app/ai_adapters/factory.py`).
- **Tables:** `embedding_chunks` (`shop_id` FK cascade, `source_type` product|policy, `source_id`, `content`, `embedding vector(EMBEDDING_DIM)`, HNSW cosine index, composite index starting with `shop_id`) and `ai_usage_logs` (per shop: operation, provider, model, input/output tokens, `estimated_cost` in USD). `source_id` is the product id for products and the shop id for the shop policy.
- **Always filter by shop:** `vector_search` and every chunk query include `shop_id`; one shop's chunks are never used for another shop. The gateway enables pgvector's iterative index scan so a shop filter never returns fewer than `top_k` rows.
- **Keeping chunks fresh (AI-R13):** the product/policy hooks queue Celery tasks `embed_product(product_id)`, `delete_product_embeddings(product_id, shop_id)`, `embed_policy(shop_id)` via `app/workers/dispatch.enqueue`, which never fails the request (if the queue is down it logs an error; fix with `python -m app.cli reembed-shop --shop-id N`). Tasks replace a source's chunks in one transaction; if the source changed while embedding, the stale result is dropped (a newer task is queued). **A Celery worker must be running** for embeddings to update. Measured edit-to-updated time with the mock provider: ~0.2 s (`backend/scripts/check_embedding_latency.py`).
- **Usage logging (NFR-08):** every embedding call, including the query embedding done by `retrieve`, is written to `ai_usage_logs` through `app/services/ai_usage.py` (`log_ai_usage`). Later AI features must log their calls the same way. Cost = tokens x the per-model rate in `AI_COST_RATES` (JSON, USD per 1M tokens); unknown models cost 0 but are still logged.
- **Providers:** `EMBEDDING_PROVIDER` = `openai` (text-embedding-3-small, key in `OPENAI_API_KEY`), `local` (multilingual model such as BAAI/bge-m3, `pip install "shopsathi-ai[local]"`), or `mock` (offline test double with NO semantics - tests only; it cannot match "lal saree" to "Red Jamdani Saree").
- **Changing model or dimension:** set `EMBEDDING_MODEL`/`EMBEDDING_DIM` (bge-m3 = 1024), then `python -m app.cli reembed-all`. If the dimension changed, add `--resize-column` (empties and resizes the derived `embedding_chunks` table, then rebuilds). Without it the command stops with a clear message. The migration creates the column with the `EMBEDDING_DIM` in force at that time.
- **Tests** set `CELERY_TASK_ALWAYS_EAGER=true` (jobs run inline) and `EMBEDDING_PROVIDER=mock`.

## Conversation pipeline (AI chat)
- **Layering:** `ai_engine` has the pipeline (`engine.py`: 1. understand -> 2. search (RAG + tools) -> 3. write reply), language detection (`language.py`), the checked reply writer (`reply.py`), tools (`tools.py`) and the prompt files (`shopsathi_ai/prompts/*.md|json`, never inline strings). It reaches shop data only through `ShopDataGateway` (`vector_search`, `search_products`, `check_stock`, `get_delivery_charge`, `log_ai_usage`), implemented by the backend gateway. The backend builds the models (`get_llm()`, `get_embedder()`).
- **Single entry point:** `ConversationService.handle_customer_message(chat, text)` (`app/services/conversation.py`). It stores the customer message, loads short-term memory, calls `ConversationEngine`, stores the AI message (intent, confidence, language style, `extras`), sets `chats.ai_disclosure_sent`, and logs LLM usage. **Prompt 14 (Messenger) must reuse it** for every channel. One message per chat is processed at a time (Redis lock), so only one reply is "the first".
- **Intents** (exactly): `price`, `size_stock`, `delivery`, `suggestion`, `order`, `complaint`, `other`. Entities: `product_name`, `size`, `colour`, `area`. Language style: `bangla` | `english` | `banglish`, decided in code (`detect_style`) and used for every reply and fixed phrase. Bangla digits are normalised to 0-9 before understanding.
- **Grounding rules:** replies use only supplied facts (product/stock tool results, delivery-charge lookup, retrieved policy/product chunks above `RAG_MIN_SCORE`). In code, **every number in a reply must appear in the facts**; otherwise the reply is regenerated once, then replaced by the fixed "I'll check with the shop" phrase. No facts at all means the model is not asked to write anything. Stock is for the product overall (the catalogue has no per-size stock). Tools are run by the engine from the understood intent and entities (not by LLM function calling), so the model never chooses what data to fetch.
- **Handover signal:** `EngineResult.handover = {needed, reason}` and the same under `messages.extras.handover`. Reasons: `not_in_shop_data`, `reply_not_grounded`, `understanding_failed`, `ai_unavailable`, and (until Prompts 11-12 build them) `complaint` and `order_request`, which get only the safe "I'll check with the shop" reply. Prompt 12 turns the signal into flagged chats.
- **First reply disclosure:** the first AI reply of a chat starts with the "automatic assistant, ask for a person" text (in the customer's style); `ai_disclosure_sent` makes it appear once per chat.
- **Privacy:** the LLM gets the current message, at most the last 6 turns (300 characters each), and the retrieved facts. No customer name, PSID or older history.
- **Memory:** Redis list `chatmem:<shop_id>:<chat_id>` with the last `CHAT_MEMORY_TURNS` turns and a TTL (`CHAT_MEMORY_TTL_SECONDS`); rebuilt from the `messages` table if it expired. AI turns remember the product entity so "eta ki XL e pawa jabe?" knows what "eta" is.
- **Usage logging (NFR-08):** `ai_usage_logs` operations `intent` (understanding call), `suggestion_needs` (needs extraction), `chat_reply` (reply calls, including the regeneration) and `embedding` (query embedding). Rates in `AI_COST_RATES`.
- **Test chat (FR-09):** `chats.channel = 'test'`, owner only, `/api/v1/test-chat/...`. Test chats are **not** counted by `UsageLimitService` (their AI cost is logged), and inbox, reports and exports (later prompts) **must exclude channel `test`**. Nothing is sent to Facebook.
- **Where the keys go:** API keys and provider choices live in **`backend/.env`** only (`LLM_PROVIDER`, `EMBEDDING_PROVIDER`, `OPENAI_API_KEY`, ...). The backend passes them to `ai_engine`, which does not read any `.env` of its own. Automated tests force the mock providers, so they never call a paid API.
- **English search form:** the understanding step also returns `entities.product_name_en` (the product in English letters, e.g. "লাল শাড়ি" -> "red saree") and normalises `colour` to English. The engine searches the catalogue with it, because embedding similarity across Bangla script and an English catalogue is weak with text-embedding-3-small. Semantic (embedding) product matches are used only when no product name matches.
- **Product suggestions (AI-3, AI-R05, AI-R06):** for intent `suggestion` the engine (`shopsathi_ai/suggestions.py`) 1) extracts the needs stated in **this message only** (product type, budget, size, colour, occasion; one LLM call, operation `suggestion_needs`; falls back to the understood entities), 2) gets candidates (name match, then similarity; with no product type: similarity to the occasion, then in-stock browsing), 3) **filters in code on live `products` data**: `stock_count > 0`, requested size/colour offered, price <= budget, then reads the chosen products once more just before replying, and 4) lets the model write the reply from those products only. At most 3 (`MAX_SUGGESTIONS`). A zero-stock product is never suggested and the stock rule is never relaxed. No match -> an honest fixed phrase (`no_suggestion`) and no cards; no stated need at all -> `ask_needs`. The budget is read by code (`budget.py`); a number the model returns is accepted only if the customer wrote it. Nothing is inferred about the customer (gender, religion, background); the prompts forbid it.
- **`extras["suggested_products"]`** on the AI message: `[{id, name, price, photo}]` (`photo` = first photo URL or null; absent key = not a suggestion reply). `extras["needs"]` holds the extracted needs. The Test chat renders the cards; Prompt 14 should send the same list as Messenger cards.
- **Reply style is checked in code too:** a Bangla message needs a reply in Bangla script; Banglish and English replies must contain no Bangla letters (`script_matches_style`). A wrong-script reply is regenerated once, then replaced by the safe fallback (`reply_wrong_script`). The prompt shows the model a concrete `write_in` instruction and example.
- **Order drafting (AI-4, AI-R07 to AI-R09, AI-R11):** on intent `order`, and on follow-up messages while an order is being collected, `extract_order` (structured JSON, operation `order_extraction`) reads the chat and `process_order` (`ordering.py`) **validates in code** against the shop's data: the product must resolve to a product of this shop (ambiguous -> ask which one; unknown -> "I'll check with the shop"; stock 0 -> say so and draft nothing), size/colour must be one of the product's listed options (not asked when it has none), quantity a positive integer within the catalogue stock, the phone a valid Bangladeshi mobile number (`validators.normalize_and_validate_bd_phone`, **reused by Prompt 16**), and name/phone/address must appear in the customer's own messages (the model cannot invent them). Missing or invalid fields are asked for again, in the customer's style, from fixed phrases (`order_*` in `prompts/phrases.json`): the AI cannot say an order is confirmed, mention a discount, or quote anything but the catalogue price.
- **Pending order:** `chats.pending_order` (JSON) holds the validated fields collected so far; the engine returns the new state in `EngineResult.pending_order`; `ConversationService` stores it and forgets it after `ORDER_PENDING_TTL_HOURS` (24). A question asked in the middle of collecting (price, delivery ...) is answered normally and the pending order is kept. While collecting, data-only messages (a phone number or address) keep the conversation's language style.
- **Order draft:** when everything is valid the engine returns `extras["order_ready"]`; `ConversationService` creates exactly **one** `orders` row with status `draft` (unit price = the live catalogue price, product name snapshot, `is_test = true` for channel `test`), stores `order_id` / `order_draft` in the AI message extras and clears the pending order and the short-term memory (so the same details can never be drafted twice; the memory rebuild ignores messages before the draft). **Nothing in the AI path sets `confirmed` or `cancelled`**: confirming, editing and cancelling belong to the seller (Prompt 16). Reports, exports and the seller's order list must exclude `is_test` orders.
- **Handover / flagging (AI-5, AI-R10, AI-R04):** `shopsathi_ai/handover.py` decides. A chat is flagged for exactly one reason from this set: `complaint`, `refund`, `abusive_language`, `low_confidence`, `off_topic`, `not_in_shop_data`, `human_requested` (priority in that order of urgency: abusive_language, refund, complaint, human_requested, off_topic, low_confidence, not_in_shop_data). Inputs: the understanding step's intent, confidence and structured flags (`refund_request`, `abusive_language`, `human_requested`, `off_topic`), a precise keyword check in code (`prompts/handover_terms.json`; a question about the refund/return *policy* is not a refund request), and the "not in shop data" signal. Technical failures (LLM down, unverifiable reply, unusable JSON) are recorded as `low_confidence` with the cause in `handover.detail`. Confidence below `AI_CONFIDENCE_THRESHOLD` (default **0.5**) flags; it is ignored while an order is being collected and for greetings. A handover word written as the intent ("off_topic") is mapped to its flag, never lost.
- **Holding replies:** a flagged chat gets one short fixed phrase in the customer's style (`holding_*`, `check_with_shop` in `prompts/phrases.json`): no promise of a refund, discount or answer.
- **What flagging does (`ConversationService._flag_chat`):** `chats.is_flagged / flag_reason / flagged_at` are set, `chats.ai_paused = true` (the AI writes no reply to later messages until a shop user turns it back on, Prompt 15; the customer's messages are still stored), a `handover_events` row is added (Prompt 17 counts "chats handed to humans" from this table), and, for channel `messenger` only, a `notifications` row (`type = chat_flagged`). Flags in the Test chat window create events but no notifications and are shown in that window only. The pause check happens before the engine runs, so a paused chat costs no AI calls.
- **Notifications API (owner + moderator, shop-scoped):** `GET /api/v1/notifications` (`unread_count` + items, unread first), `POST /api/v1/notifications/{id}/read`, `POST /api/v1/notifications/read-all`. The dashboard header bell polls it every 30 s; items link to the planned inbox route `/dashboard/inbox/{chat_id}` (page arrives in Prompt 15). Demo flagged Messenger chats come from `python -m app.cli seed` (`database/seed/demo_chats.json`).
- **Mock LLM:** `LLM_PROVIDER=mock` is a keyword/regex test double that fills the same JSON shapes (no real language understanding; it cannot read "লাল শাড়ি"). Use `openai` or `gemini` (`pip install "shopsathi-ai[llm]"`) for real quality.

## Facebook Page connection (FR-07)
- **Settings (environment only):** `FB_APP_ID`, `FB_APP_SECRET`, `FB_GRAPH_API_VERSION` (default `v21.0`; Meta retires old versions, so review it from time to time), `FB_OAUTH_REDIRECT_URI` (this backend's `/api/v1/facebook/callback`, also registered in the Meta app under Facebook Login), `FB_TOKEN_ENCRYPTION_KEY` (a Fernet key), `FRONTEND_URL` (empty = `FRONTEND_ORIGIN`). Dev/test only: `FB_GRAPH_BASE_URL`, `FB_DIALOG_BASE_URL` (point at `backend/scripts/fake_facebook.py`).
- **Encryption (NFR-03):** Page tokens are encrypted with `TokenCipher` (`app/core/crypto.py`, Fernet) before they are stored in `facebook_pages.encrypted_page_token`. Generate a key with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. **Back the key up and keep it secret**: without it the stored tokens cannot be read and every shop must reconnect its Page. Plaintext tokens are never logged, never returned by an API, and never put in a URL (the Graph client sends them in the `Authorization` header or a POST body).
- **Flow:** `GET /facebook/connect-url` (signed `state` bound to the shop, 10 minutes, works once; signed with a key derived from `JWT_SECRET`, so a login token is not a valid state) -> Facebook -> `GET /facebook/callback` (public: the state identifies the shop; exchanges the code for a long-lived user token, checks that all of `pages_show_list`, `pages_messaging`, `pages_manage_metadata` were granted, lists the managed Pages, keeps them 10 minutes in Redis **encrypted**, and always redirects to `FRONTEND_URL/dashboard/facebook?status=select` or `?error=<code>`) -> `GET /facebook/pages/available` -> `POST /facebook/pages/connect {page_id}` (subscribes the app to the Page's `messages` field, then stores the encrypted Page token) -> `GET /facebook/page` (status, never the token) -> `POST /facebook/page/disconnect` (unsubscribes best-effort, deletes the row). Owner only (the callback excepted).
- **Rules:** one Page per shop (`shop_id` unique) and a Page belongs to one shop (`page_id` unique); a shop must disconnect before connecting another Page. Error codes the frontend maps: `denied`, `permissions_missing`, `no_pages`, `state_expired`, `state_invalid`, `not_configured` (503, names the missing settings), `facebook_error`; API errors use `{"detail": ...}`.
- **Meta rules:** while the Meta app is in Development mode only people with a role on the app (admin, developer, tester) can log in, and `pages_messaging` / `pages_manage_metadata` for other users need Meta's App Review (Advanced Access). Webhook handling and sending messages are Prompt 14.

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

## Messenger webhook & delivery (Prompt 14)
- The webhook must verify `X-Hub-Signature-256` on the raw body before reading it, answer 200 quickly and do the AI work in the Celery task `process_incoming_message`.
- Sending to a customer always goes through `MessengerSender` (24-hour window check built in, `messaging_type: RESPONSE`, retry only temporary errors, never log tokens or message text). Prompt 15 (seller replies) reuses it; no message outside the window is ever sent.
- A Messenger AI reply is stored with `sent_at = NULL` and gets `sent_at` + usage count only after Facebook accepted it.
- Per-message state lives in `messages.extras`: `ai_status` (pending/replied/skipped/failed), `ai_skip_reason`, `in_reply_to` (on the AI message), `delivery` (`status`, `facebook_message_id`, `timings_ms`).
- Non-text customer messages are stored as a bracketed placeholder and handed over with `low_confidence`.

## Inbox (Prompt 15)
- `/api/v1/chats...` is owner + moderator, Messenger chats only (`channel='test'` is never listed and gives 404). Listing order: flagged first (oldest flag first), then latest activity.
- The seller's manual reply (`sender='seller'`) is allowed only while `ai_paused`, always goes through `MessengerSender` (24-hour window) and is never passed to `UsageLimitService`. Pause, resume and resolve-flag are independent actions.
- Shared message cards live in `frontend/src/components/ChatCards.tsx`.

## Orders dashboard & CSV export (Prompt 16)
- `/api/v1/orders...` is owner + moderator, `is_test = false` only. Only drafts can be edited, confirmed or cancelled (else 409); only a person confirms. The unit price is never edited: it comes from the catalogue when the product changes.
- The courier CSV is UTF-8 with BOM, CRLF lines, columns `order_id, confirmed_at, customer_name, customer_phone, customer_address, product_name, size, colour, quantity, unit_price, total_price`; date filters are Asia/Dhaka days, both included. Any future export of customer-written text must neutralise leading `= + - @` the same way (`_safe_cell`).

## Reports (Prompt 17)
- Report counts (owner only) always exclude `chats.channel = 'test'` and `orders.is_test`, use Asia/Dhaka calendar days with both ends included, count "messages handled by AI" as AI messages with `sent_at` set (a reply that was never delivered is not handled), and "chats handed to humans" as distinct chats with a `handover_events` row. Later reports (Prompt 18 insights) must follow the same rules.

## Weekly insights (Prompt 18)
- A week is Monday 00:00 to next Monday 00:00 in Asia/Dhaka; `weekly_insights.week_start` is the Monday. The summary uses only the shop's Messenger **customer** messages (never test chats), after personal details are removed (`shopsathi_ai.insights.redact`); any future AI feature that sends chat text to a model must do the same. Usage is logged under operation `weekly_insights` (one row per model call).
- Scheduled work runs through Celery beat (`beat_schedule` in `app/workers/celery_app.py`, UTC times); start it with `celery -A app.workers.celery_app beat`.
