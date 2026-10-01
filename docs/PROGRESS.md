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

## Prompt 10 — AI product suggestions
**Built:**
- AI engine: `suggestions.py` (needs extraction with structured output, candidate search, code-side filtering on live data: in stock, size, colour, budget, max 3), `budget.py` (reads "1500 er moddhe", "under 2000", "১৫০০ টাকার মধ্যে", "1.5k"), prompts `needs_system.md` / `needs_user.md`, fixed phrases `no_suggestion` and `ask_needs`; `ShopDataGateway` gets `get_products` and `browse_products`; `ProductInfo` gets `photos`. The suggestion branch is part of the existing `ConversationEngine` (no parallel pipeline).
- Backend: gateway `get_products` / `browse_products` read the `products` table live (stock is never taken from embeddings) and return photo URLs; `ConversationService` already stores `extras`, so `suggested_products` is saved with the AI message and returned by the test-chat API.
- Frontend: suggestion cards (photo, name, price) under the AI reply in the Test chat window.
- Quality fixes found while testing with the real model: needs come from the latest message only; the reply must be in the customer's script/style (checked in code and shown with a concrete instruction); "I need a laptop under 5000" / "navy panjabi 1400 er moddhe" are now classified as suggestions.

**Tables / endpoints / pages:** none new (the existing test-chat messages now include `extras.suggested_products`).
**New env vars:** none.
**Demo data:** `database/seed/demo_products.json` gains "Eid Special Panjabi" (1450, in stock) and "Premium Silk Panjabi" (1390, sold out) so the proposal example "eid er jonno 1500 er moddhe panjabi" has a real answer; `python -m app.cli seed` adds them.
**Real-model check** (gpt-4o-mini + text-embedding-3-small, demo shop): "eid er jonno 1500 er moddhe panjabi" -> Eid Special Panjabi (1450 BDT) only; never the sold-out Premium Silk Panjabi (1390) nor Cotton Panjabi (1850); "I need a laptop under 5000" and "navy panjabi 1400 er moddhe" -> honest "could not find" with no cards; "kichu suggest korun" -> asks what the customer wants. Test-chat replies took 3-7 s. `backend/scripts/debug_chat.py` prints needs and cards.
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 11 — Automatic order drafting & phone check
**Built:**
- AI engine: `validators.normalize_and_validate_bd_phone` (Bangla digits, spaces/dashes, `+88`/`88`, `^01[3-9]\d{8}$`); `extraction.py` (`extract_order`, structured JSON); `ordering.py` (validation against the shop's data, merge into the pending order, fixed-phrase replies); tool `update_order_draft`; order branch in `ConversationEngine` (collects and asks only for what is missing, re-asks invalid phones, returns `extras["order_ready"]`); prompts `order_system.md` / `order_user.md`; `order_*` phrases in 3 styles.
- Backend: `chats.pending_order`; `orders` table; `ConversationService` persists pending fields, creates one `draft` order per completed collection (never `confirmed`), clears pending state and memory, logs `order_extraction` usage; memory rebuild ignores messages before a draft.
- Frontend: "Order draft created" card in the Test chat window (product, size, colour, quantity, price, name, phone, address, status "draft — awaiting seller confirmation").

**Tables (migration 0008):** `orders`; new column `chats.pending_order`.
**Endpoints / pages:** none new (test-chat messages now carry `extras.order_draft`).
**New env var (backend):** `ORDER_PENDING_TTL_HOURS` (24).
**Real-model check** (gpt-4o-mini, Banglish, demo shop): "Cotton Panjabi nibo" -> asked size/colour/quantity/name/phone/address; "XL size, Navy colour, duita lagbe" and "amar nam Rahim Uddin" were picked up; "phone 0171234567" was refused and asked again; "sorry, number ta 01712345678" accepted; the address completed a draft (Cotton Panjabi, XL, Navy, 2, 1850 BDT each, status `draft`, `is_test`). 3-5 s per reply. The browser card matched the stored row.
**Upgrade steps:** `alembic upgrade head`.
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 12 — Smart handover & seller notification
**Built:**
- AI engine: `handover.py` (`decide_handover(message, understanding, engine_state) -> HandoverDecision(flag, reason)`; the seven flag reasons; keyword safety net in `prompts/handover_terms.json`; configurable confidence threshold); structured handover flags in the understanding step (`refund_request`, `abusive_language`, `human_requested`, `off_topic`); polite fixed holding replies in the three styles; the engine flags before answering and for the "not in shop data" case. Old technical reasons now map onto the seven reasons (cause kept in `Handover.detail`).
- Backend: `handover_events` and `notifications` tables; `ConversationService` flags the chat, pauses the AI, records the event and (Messenger only) a notification; a paused chat stores customer messages but writes no reply; notifications API; test-chat responses carry the chat's flag/pause state; demo flagged Messenger chats in `seed`.
- Frontend: notification bell with unread count (polled every 30 s) and a list with mark-as-read / mark-all in the dashboard header; "flagged, AI paused" banner and notes in the Test chat window.

**Tables (migration 0009):** `handover_events`, `notifications`.
**Endpoints (owner + moderator):** `GET /api/v1/notifications`, `POST /api/v1/notifications/{id}/read`, `POST /api/v1/notifications/read-all`. Test-chat send/list responses gained `chat` / `is_flagged`, `flag_reason`, `ai_paused`; `ai_message` can be null while paused.
**Pages:** none new (bell in the dashboard header; banner in `/dashboard/test-chat`). Links go to the planned `/dashboard/inbox/{chat_id}` (Prompt 15).
**New env var (backend):** `AI_CONFIDENCE_THRESHOLD` (default 0.5).
**Seed:** `database/seed/demo_chats.json` (3 flagged + 1 normal fictional Messenger chats), loaded by `python -m app.cli seed`.
**Real-model check** (gpt-4o-mini): complaint, refund request, off-topic (cricket), "Do you sell laptops?" (not in shop data), "I want to talk to a person" and abuse each flagged with the right reason and the AI stopped replying; "refund policy ki?" is not flagged. Found and fixed: the model wrote `intent: "off_topic"` (outside the seven intents), which made the whole understanding invalid; it is now mapped to the `off_topic` flag.
**Upgrade steps:** `alembic upgrade head`.
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 13 — Facebook Page connection
**Built:** the owner can connect and disconnect one Facebook Page per shop through Facebook Login. `GraphClient` (httpx; reused by Prompt 14), `TokenCipher` (Fernet) for Page tokens at rest, signed expiring one-use OAuth `state`, short-term encrypted Page list in Redis, webhook subscription to the Page's `messages` field on connect and best-effort unsubscribe on disconnect, clear errors (missing app settings, denied or missing permissions, expired state, Page already used by another shop). Frontend: owner-only "Facebook Page" settings page (status card, Connect button, Page selection after returning from Facebook, Disconnect with confirmation). `backend/scripts/fake_facebook.py` is a fake Facebook for local demos.

**Tables (migration 0010):** `facebook_pages` (`shop_id` unique, `page_id` unique, `encrypted_page_token`).
**Endpoints:** `GET /api/v1/facebook/connect-url`, `GET /api/v1/facebook/callback` (public, state-protected), `GET /api/v1/facebook/pages/available`, `POST /api/v1/facebook/pages/connect`, `GET /api/v1/facebook/page`, `POST /api/v1/facebook/page/disconnect` (all but the callback owner only).
**Pages:** `/dashboard/facebook` (nav item "Facebook Page", owner only).
**New env vars (backend):** `FB_APP_ID`, `FB_APP_SECRET`, `FB_GRAPH_API_VERSION`, `FB_OAUTH_REDIRECT_URI`, `FB_TOKEN_ENCRYPTION_KEY`, `FRONTEND_URL`; dev/test only `FB_GRAPH_BASE_URL`, `FB_DIALOG_BASE_URL`. New dependencies: `cryptography`; tests: `respx`.
**Verification:** automated tests mock the Graph API (respx). The browser flow was run end to end against the local fake Facebook (login round-trip, Page selection, connect, subscription, disconnect, cancelled login, missing settings). **Not run against real Facebook: no Meta app / test Page credentials were available (Milestone M2 is pending real credentials).**
**Upgrade steps:** `pip install -r requirements.txt`, `alembic upgrade head`, then the six `FB_*` settings in `backend/.env`.
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 14 — Messenger webhook & reply delivery
**Built:** Facebook messages now reach the AI and the answer goes back to the customer. `GET/POST /api/v1/webhooks/messenger`: verification handshake (`FB_VERIFY_TOKEN`), `X-Hub-Signature-256` check (`FB_APP_SECRET`, constant-time), echoes/receipts/unknown Pages ignored, de-dup by `mid` (`messages.external_message_id`), chat found or created per shop + customer PSID (unique index), message stored with `received_at`, Celery task `process_incoming_message(message_id)` enqueued, 200 returned at once (also if the queue is down; the message stays `pending`). The worker answers a chat's messages in order (per-chat Redis lock), skips the AI (message kept for the seller) when the shop is suspended, the chat is paused, no Page is connected or the plan limit is reached, uses `ConversationService.reply_to_stored_message` (no second copy of the customer message), enforces the 24-hour window and sends with `messaging_type: RESPONSE` through `MessengerSender` (`app/integrations/facebook/messenger_sender.py`; Prompt 15 must reuse it). Product photos (public HTTPS URLs only, max 3) follow suggestion replies. `sent_at` is set and the usage counted only after Facebook accepted the reply; failed sends are logged (code/message only), retried a few times for temporary errors, never crash the worker and are not counted. Non-text messages (photo, voice, sticker, file...) are stored as a placeholder and handed over with reason `low_confidence`.
**Timings (NFR-01):** `extras.delivery.timings_ms` on the AI message = `queue`, `ai`, `send`, `total` (total = `sent_at − customer.received_at`).
**Tables (migration 0011):** partial unique index `uq_chats_shop_messenger_psid` on `chats(shop_id, customer_psid)` for Messenger chats.
**Endpoints:** `GET/POST /api/v1/webhooks/messenger` (public, signature-protected). **Pages:** none.
**New env vars (backend):** `FB_VERIFY_TOKEN`, `FB_SEND_MAX_ATTEMPTS` (3), `FB_SEND_RETRY_DELAY_SECONDS` (0.5).
**Dev tools:** `backend/scripts/simulate_messenger_event.py` (signed events: text, attachment, echo, bad signature, duplicate `--mid`, old timestamp); `fake_facebook.py` now also fakes the Send API and the customer profile (`/_debug/messages`, `/_debug/fail-sends/N`).
**Verification:** 44 new tests in `tests/test_messenger.py` (handshake, bad/missing signature, echo, duplicate mid, unknown Page, message → task → reply to the same PSID via mocked Send API, paused/suspended/limit reached, outside 24 h, usage only after a successful send, retries, non-text, timings, ordering, idempotent retry, photos, shop isolation). Full run: backend 243 passed, ai_engine 221 passed. Simulation against the running stack (uvicorn + Celery worker + fake Facebook + real gpt-4o-mini): bad signature → 403, echo/unknown Page ignored, duplicate mid once, price/stock/delivery questions answered, photo message flagged `low_confidence`, 30-hour-old message skipped. Replies took 6–10 s end to end (queue 0.1–0.3 s, AI 2–8 s over 3 model calls, the first after start-up slowest); the 8 s target for 90 % is **not yet shown** — it needs a sample on the real stack.
**Not verified:** real Facebook (Milestone M4): needs a public HTTPS URL for the backend, `FB_VERIFY_TOKEN` set and the webhook (`messages` field) configured in the Meta app, and the owner connecting the test Page. Pending until then.
**Upgrade steps:** `alembic upgrade head`; set `FB_VERIFY_TOKEN`; run a Celery worker.
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 15 — Chat inbox & human takeover
**Built:** the inbox for owners and moderators (FR-10, FR-11). Backend `chats` routes: list Messenger chats (flagged first, longest-waiting flag first, then latest activity; `flagged|all` filter; pagination; each item has customer label, last-message preview, flag reason, `ai_paused`, last activity, `window_open`), chat detail with customer/AI/seller messages (suggestion and order-draft extras included), pause / resume the AI, manual seller reply, and resolve-flag (clears `is_flagged`, marks that chat's notifications read; resuming the AI stays separate). A manual reply is allowed only while the AI is paused, goes through `MessengerSender` (24-hour window, NFR-09; outside it: 409 with a clear message and nothing sent; Facebook refusal: 502 and nothing stored), is stored as `sender=seller` and is **not** counted as an AI message. Test-channel chats are never listed and return 404, like other shops' chats. Frontend: "Inbox" page (`/dashboard/inbox`, `/dashboard/inbox/{id}`) with Flagged/All filter, flag and "AI paused" badges, conversation view reusing the suggestion and order-draft cards (moved to `components/ChatCards.tsx`, shared with the Test chat), Pause AI / Resume AI, reply box enabled only when paused and the window is open (clear notices otherwise), "Mark flag as handled", polling every 10 s, list and conversation as separate screens on phones. Notification links (Prompt 12) now open the chat.
**Tables:** none (no migration).
**Endpoints (owner + moderator):** `GET /api/v1/chats`, `GET /api/v1/chats/{id}`, `POST /api/v1/chats/{id}/pause`, `/resume`, `/reply`, `/resolve-flag`.
**Pages:** `/dashboard/inbox`, `/dashboard/inbox/[id]` (nav item "Inbox", owner and moderator).
**New env vars:** none.
**Verification:** 19 new backend tests (`tests/test_inbox.py`): ordering, filter and pagination, test chats hidden, pause/resume, resolve-flag, reply rejected when not paused / outside 24 h / no Page, reply sent through the mocked Send API to the right PSID and stored, usage unchanged, moderator allowed, admin and anonymous refused, other shop's chat 404. Full run: backend 262 passed, ai_engine 221 passed, frontend `npm run lint` clean, `npm run build` OK. Browser check against the running stack (API + Celery worker + fake Facebook + real model; chats created with `simulate_messenger_event.py`): owner and moderator logins, flagged chat on top, pause, reply (reached the fake Send API for the right PSID), mark handled, resume (AI answered the next message), closed-window chat shows the notice with reply disabled, phone width (375 px) shows list and conversation separately without horizontal scroll.
**Not verified:** replies to real Facebook (needs the Milestone M4 setup from Prompt 14). Note: the notification bell refreshes on its 30 s poll, not immediately after "Mark flag as handled".
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 16 — Order dashboard & courier CSV export
**Built:** the seller's order dashboard (FR-12, FR-13). Backend `orders` routes (owner + moderator, shop-scoped, `is_test` orders never shown; test and other shops' orders give 404): list by status (`draft` default, newest first, pagination, per-status counts for the tabs), detail (with `chat_id` link and the product's current sizes/colours), edit (draft only: product, size, colour, quantity, name, phone, address; same rules as drafting: product of this shop, size/colour must be listed options, quantity 1..stock, valid BD phone via `normalize_and_validate_bd_phone`; changing the product takes the catalogue price again; the price itself and the status cannot be sent), confirm (`confirmed_at`, `confirmed_by_user_id`), cancel (`cancelled_at`); wrong-state actions return 409 with a clear message. `GET /orders/export?from=&to=` returns a UTF-8 **BOM** CSV of confirmed orders whose confirmation day (Asia/Dhaka, both days included) is in the range; columns `order_id, confirmed_at (Dhaka, YYYY-MM-DD HH:MM), customer_name, customer_phone, customer_address, product_name, size, colour, quantity, unit_price, total_price`; text starting with `= + - @` is prefixed with `'` so customer text cannot become a spreadsheet formula. `GET /orders/product-options` lists the shop's products for the edit form (the products API is owner-only, moderators need this). Frontend: "Orders" page (Draft / Confirmed / Cancelled tabs, table on desktop and cards on phones, pagination, export box with a date range) and an order detail page with the edit form (draft only), Confirm / Cancel with confirmation dialogs and a link to the source chat. No courier booking, tracking, payment, invoice or stock deduction.
**Tables:** none (no migration).
**Endpoints (owner + moderator):** `GET /api/v1/orders`, `GET /api/v1/orders/export`, `GET /api/v1/orders/product-options`, `GET/PATCH /api/v1/orders/{id}`, `POST /api/v1/orders/{id}/confirm`, `POST /api/v1/orders/{id}/cancel`.
**Pages:** `/dashboard/orders`, `/dashboard/orders/[id]` (nav item "Orders", owner and moderator).
**New env vars:** none.
**Verification:** 19 new backend tests (`tests/test_orders_dashboard.py`): listing excludes test and other shops' orders, pagination, edit validation (bad phone, bad/missing size, colour, quantity, stock, foreign product, price/status not editable), product change re-snapshots the price, confirm/cancel transitions and 409s, no stock change, export columns/range/Dhaka days/Bangla text/formula safety/other shops excluded, moderator allowed, admin and anonymous refused. Full run: backend 281 passed, ai_engine 221 passed, frontend lint clean and build OK. Browser check against the running stack: a real AI draft made from a Messenger message (simulation script, real gpt-4o-mini) plus two seeded drafts (one Bangla); edit with an invalid phone shows the error, valid edit saved, confirm dialog, confirm, cancel dialog, cancel; the downloaded CSV (checked through the same endpoint) starts with the BOM, has the exact columns and shows the Bangla name and address correctly; phone width 375 px has no horizontal scroll.
**Not verified:** opening the downloaded file in Excel itself (the BOM and quoting follow what Excel needs, but Excel was not available); moderator login in the browser (covered by API tests).
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.

## Prompt 17 — Reports
**Built:** the owner's report (FR-14). `GET /api/v1/reports/summary?from=&to=` (owner only; days in Asia/Dhaka, both ends included) returns four numbers from the real records, for the caller's shop only and never from the Test chat window: `messages_handled_by_ai` (AI messages with `sent_at` set on Messenger chats), `chats_handed_to_humans` (distinct Messenger chats with a `handover_events` row), `orders_drafted` (non-test orders by `created_at`), `orders_confirmed` (non-test orders by `confirmed_at`). The range is validated (start not after end; at most `REPORT_MAX_RANGE_DAYS`, default 366). Frontend: "Reports" page (owner only, nav item) with a date range (default: last 7 days) and four stat cards, plus a clearly marked "Weekly AI summary" placeholder for Prompt 18. Demo data: `database/seed/demo_history.json` (32 fictional chats over about six weeks with AI replies, handovers and orders in every status) loaded by `python -m app.cli seed`.
**Tables:** none (no migration).
**Endpoints:** `GET /api/v1/reports/summary` (owner only). **Pages:** `/dashboard/reports`.
**New env var (backend):** `REPORT_MAX_RANGE_DAYS` (366).
**Verification:** 10 new backend tests (`tests/test_reports.py`): every metric at the range boundaries (23:59:59 out, 00:00:00 in), Dhaka days vs UTC days, unsent and non-AI messages not counted, a chat handed over several times counted once, drafted/confirmed by their own dates (cancelled drafts still count as drafted), test-chat data excluded, other shops excluded, range validation including the configurable maximum, moderator/admin/anonymous refused, the seed loads and is idempotent. Full run: backend 291 passed (after adjusting one Prompt 12 seed test to ignore the new history chats), ai_engine 221 passed, frontend lint clean and build OK. Browser check with the seeded demo shop: the three ranges tried in the UI/API matched an independent raw-SQL count (last 7 days 11/3/1/0, September 50/5/8/5, since 20 Aug 65/8/11/7); a start date after the end date shows a message and no request; 375 px width has no horizontal scroll.
**Run tests:** `cd backend && pytest`; `cd ai_engine && pytest`; `cd frontend && npm run lint && npm run build`.
