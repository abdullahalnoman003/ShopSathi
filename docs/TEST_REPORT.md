# ShopSathi test report: performance, load and security (Milestone M5)

Date of the runs: 2026-10-02. Scope: the Messenger pipeline under load (NFR-01, NFR-07), the security requirements
(NFR-03, NFR-04, NFR-09, FR-15) and the defects the tests found. Everything here can be repeated with the commands in the
last section.

## 1. Summary

| Requirement | Result |
|---|---|
| NFR-01: AI reply within 8 s for 90% of messages | **Met with the real model** (gpt-4o-mini): p90 **5.8 s** with 50 chats at once, from a freshly started worker (p50 5.1 s, p99 6.7 s). With the offline mock model (system overhead only) p90 2.8 s |
| NFR-07: 20 shops and 50 chats at the same time | **Met**: 50 chats on 20 shops, every chat answered, no webhook error, no failed or waiting message. Headroom: 100 chats at once (offered load 25 messages/s) still answered, but its p90 was 8.5 s |
| NFR-03: hashed passwords, encrypted Page tokens, no secrets exposed | **Met** (automated, section 5). HTTPS itself is terminated by the proxy of Prompt 23; the backend now trusts that proxy's forwarded headers |
| NFR-04: customer data only for the shop and the admin | **Met** (cross-tenant sweep over every id endpoint, role matrix over every endpoint) |
| NFR-09: replies only inside the 24-hour window | **Met**, also under concurrency |
| FR-15: replies stop at the monthly limit | **Was not met under concurrency; fixed** (section 6, defect 1) |

Test counts after this work: backend 393 passed (47 are the new security suite, 7 test the load-test tools), AI engine 251,
evaluation harness 82.

## 2. Environment

One developer machine, everything local (this limits the numbers: the load generator, API, worker, database and Redis
compete for the same CPU, and the model is reached over the internet).

| | |
|---|---|
| Machine | Intel Core i7-12700K (20 logical CPUs), 15.8 GB RAM, Windows 11 Pro |
| Software | Python 3.14.3, FastAPI 0.142, SQLAlchemy 2.1, Celery 5.6.3, uvicorn 0.54, PostgreSQL 16.15 + pgvector and Redis 7.4 in Docker |
| API | one uvicorn process |
| Worker | one Celery worker process; pool `solo`, or `threads` with 16 or 50 threads (Celery's `prefork` does not run on Windows) |
| Database pool | 30 connections + 30 overflow per worker process (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`) |
| Chat model | `gpt-4o-mini` (OpenAI) with `text-embedding-3-small`; or the offline mock |
| Facebook | **never contacted**: replies go to the local stub Send API (150 ms per call, about what Facebook takes) |

## 3. Load test

### 3.1 Setup

`backend/scripts/loadtest/` (see its README). 20 load-test shops (Pro plan, three products each, a shop policy with delivery
areas, a connected fake Page with an encrypted fake token) and 50 concurrent chats spread over them. Each chat sends its
messages through the real `POST /api/v1/webhooks/messenger` with a valid `X-Hub-Signature-256`, one every few seconds, and
all chats start within the first half second. The mock runs send 3 messages per chat (150 messages), the real-model runs 2
per chat (100 messages) to keep the cost small. The real-model questions are varied (price, stock, delivery, return policy,
order wish; Banglish, English and Bangla); the mock only answers simple price questions without handing the chat to a
person, so it gets a simple list. Latency is measured from the database: `sent_at - received_at` of every reply, which is
exactly what the product records. The Celery queue length is sampled four times a second.

### 3.2 Results: the real model (the NFR-01 check)

50 chats, 20 shops, 100 messages, worker with 50 threads, final code.

| Run | received to sent p50 / p90 / p99 | queue p50 | AI p50 / p90 | webhook answer p50 / p90 | outcome |
|---|---|---|---|---|---|
| Worker just started (cold) | 5.06 s / **5.77 s** / 6.73 s | 2.0 s | 3.0 s / 3.9 s | 283 / 651 ms | 97 replies, 3 chats paused after a flag, 0 errors |
| Same worker, second run (warm) | 5.24 s / **5.92 s** / 6.97 s | 2.2 s | 2.9 s / 3.6 s | 89 / 344 ms | 72 replies, 28 messages skipped because the real model handed those chats to a person, 0 errors |
| One idle chat (baseline) | 3.3 s / 4.0 s | 0.15 s | 3.0 s / 3.7 s | 275 ms | 2 replies |

NFR-01 passes: p90 is 5.8 to 5.9 s against the 8 s limit. A reply costs about 3 s of AI time (2 to 4 model calls); the rest is
the burst: 50 messages arrive in the same second, one Python process has to store and start all of them (queue p50 2 s), then
the 150 ms send. The queue backlog never exceeded 5 jobs. The 50 chats were all answered (`chats answered 50/50`), the stub
received exactly the number of replies the database records, each to the right customer.
Cost: the setup of the 20 shops (real embeddings) plus these two runs made about 530 model calls, about 5 US cents.

Why 50 threads: with 16 threads the same load queued behind the slow model calls (first run before the fixes: p50 queue 7.6 s,
p90 total **14.7 s**, fail). The calls are waiting for the network, so more threads are free; with 50 the AI time is the
same as for one chat (a separate benchmark of 50 parallel engine calls showed 3.0 s per message at 1, 10, 25 and 50 threads).

### 3.3 Results: the offline mock model (system overhead and capacity)

150 messages, same shape, final code. The mock answers in about 0.1 s, so these numbers are the pipeline itself.

| Worker | p50 / p90 / p99 received to sent | queue backlog max | result |
|---|---|---|---|
| `solo` (the Windows default, one message at a time) | 24.1 s / **42.8 s** / 47.7 s | 127 jobs | **fails NFR-01**; all 150 handled after 58 s |
| `threads`, 16 | 1.2 s / 2.0 s / 2.5 s | 3 | passes |
| `threads`, 50 | 1.9 s / 2.8 s / 3.1 s | 8 | passes |
| `threads`, 50, **100 chats** x 3 messages (offered load 25 msg/s) | 5.6 s / 8.5 s / 8.7 s | 34 | all 300 answered, p90 just over 8 s: the limit of one worker process, about 16 messages/s |

The mock-model runs show that the worker pool setting matters more than anything else: a single message-at-a-time worker is
not enough for 50 chats. One worker process tops out around 16 messages per second (Python's global interpreter lock);
production on Linux can add worker processes (`--pool=prefork`) or several worker containers for more.

### 3.4 What changed because of the load test

* Worker documentation and settings: run the worker with a thread pool; the database pool is now configurable (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_SECONDS`).
* A worker now warms up when it starts (database pool filled, AI client built, no model request made). Without it the first burst after a restart had p90 **10.0 s** (fail); with it **5.8 to 6.1 s**.
* Celery no longer stores a result per task in Redis (only the admin health check's ping needs one): 1,958 result keys had piled up.
* Replies are counted atomically (section 6, defect 1).

## 4. Security checklist

Automated in `backend/tests/security/` (47 tests) plus the cross-tenant sweep of Prompt 20 (`tests/test_privacy.py`). "Pass" means the test passes on the final code.

| Check | Result | Where |
|---|---|---|
| Passwords stored as salted bcrypt hashes (cost >= 10), never returned or logged | Pass | `test_auth_security.py` |
| Login does not reveal whether an account exists | Pass | same |
| JWT signature verified: tampered role, flipped signature, removed signature, `alg: none`, wrong secret, other algorithm, expired, no expiry/subject/id, garbage are all 401 | Pass | same |
| Role is read from the database, not trusted from the token | Pass | same |
| Logout revokes that token on every endpoint and leaves other sessions alone; disabled users and suspended shops lose access with old tokens | Pass | same |
| JWT secret present and not a placeholder | Pass | same |
| Facebook Page token encrypted at rest (Fernet), unreadable without the key, in no table in clear | Pass | `test_secrets.py` |
| No token, secret or hash in any API response or in the OpenAPI schema | Pass | same |
| No secret in the logs (login, wrong login, Facebook connect, webhook, full conversation) and log masking | Pass | `test_secrets.py`, `test_privacy.py` |
| No secrets committed: no `.env` file would be committed, no API/private key patterns in any file that would be committed (including `frontend/`), none of this machine's real secret values from `backend/.env` appear in the repository, example env files have no secret values, no secret defaults in `config.py` | Pass | `test_secrets.py` |
| Webhook: only a correct `X-Hub-Signature-256` is accepted (missing, wrong secret, sha1, truncated, other body, tampered body, empty secret all 403), nothing stored for unsigned requests, huge bodies 413, verification token required | Pass | `test_webhook_and_limits.py` |
| Rate limits: login per account and per address, password reset per address and account, same answer for unknown accounts, reset tokens single-use and stored only as a hash | Pass | same |
| Role check on **every endpoint** (generated from the OpenAPI schema; anonymous, owner, moderator, platform admin; a new unclassified endpoint fails the test) | Pass (all 55+ endpoints) | `test_role_matrix.py` |
| Cross-tenant sweep: shop B's owner and moderator get 403/404 on all id endpoints of shop A, and nothing changes | Pass | `test_privacy.py` |
| 24-hour window and monthly limit under concurrency (24 chats at once with a limit of 5, 25 chats half outside the window, suspended shop) | Pass after the fix in 6.1 | `test_limits_under_load.py` |
| CORS limited to the frontend origin (no `*`; other origins, `null`, other ports and schemes get no permission) | Pass | `test_transport.py` |
| Forwarded headers (`X-Forwarded-For`, `X-Forwarded-Proto`) believed only from `TRUSTED_PROXIES`; spoofing ignored; a forged header does not dodge the login limit | Pass | same |

**HTTPS.** The backend itself speaks plain HTTP and must run behind an HTTPS reverse proxy in production (Prompt 23). It now
honours that proxy: set `TRUSTED_PROXIES` to the proxy's address so URLs it builds stay `https://` and the rate limits see
the real client instead of the proxy. Without it every customer would share one login rate-limit bucket. Not done (not
requested): HSTS and other security headers; they belong to the proxy configuration.

## 5. Not covered / limits of these tests

* The runs are on one machine with a stub in place of Facebook; real Facebook latency and rate limits, a second API process and a multi-process worker were not exercised. Percentiles come from 72 to 150 replies per run; the real-model result was repeated four times with similar numbers (p90 5.8 to 6.1 s once the worker was warmed up).
* The real-model result depends on OpenAI's response time on the day (about 1 to 1.5 s per call here). A slow day would move p90 up; the worker has a 20 s model timeout and falls back to a "check with the shop" reply and a flag.
* The harness measures one burst of 50 messages followed by a calm period, not hours of sustained traffic. A 100-chat burst at 25 messages/s is beyond what one worker process handles within 8 s.
* Penetration testing by a person, dependency vulnerability scanning and a review of the production proxy setup are not part of this report.
* AI answer quality is measured separately with the evaluation tool (Prompt 21): the latest run on the 32 harness sample cases with the real model is in `evaluation/reports/report_20261002_002812_openai.md` (reports are git-ignored; generate a new one with `python evaluation/run_eval.py`). The proposal's 200-message labelled test set does not exist yet, so the AI accuracy targets are not yet measured.

## 6. Issues found and fixes made

1. **Monthly limit passed under concurrency (FR-15), defect in existing behaviour.** The worker checked "below the limit?" and counted the reply only after sending, so chats answered at the same time all passed the check: with a limit of 5 and 24 chats at once, **24 replies were sent and counted**. Fix: `UsageLimitService.reserve_ai_reply` takes one reply from the month's allowance with a single atomic `UPDATE ... WHERE count < limit` before the AI work, and `release_ai_reply` gives it back if nothing was sent (failed send, window closed, chat paused meanwhile). A reply that is not sent is still never counted (the count is briefly one higher while a reply is being made). Test: `test_the_monthly_limit_holds_when_many_chats_are_answered_at_once`.
2. **A worker that handles one message at a time cannot meet NFR-01 under 50 chats** (p90 42.8 s with the mock, 14.7 s with 16 threads and the real model). Fix: documented thread pool, configurable database pool, no change to product behaviour.
3. **Cold-start burst.** The first burst after a worker restart opened all its database connections and imported the AI client at once (p90 10.0 s). Fix: worker warm-up on start (6.1 s afterwards).
4. **Celery result keys piled up in Redis** (1,958 after a day of testing). Fix: results are ignored except for the health-check ping.
5. **Rate limits behind a proxy.** `request.client` would be the proxy for every user. Fix: `TRUSTED_PROXIES` and uvicorn's proxy-headers middleware (default: only `127.0.0.1` is trusted).
6. **A test of mine was vacuous.** The id-endpoint coverage check added in Prompt 20 iterated `app.routes`, which no longer lists the nested routers of this FastAPI version, so it checked nothing. It now reads the OpenAPI schema and asserts that it found at least 15 id routes.
7. **Windows `localhost` delay.** `localhost` tries IPv6 first and adds about 2 s to every new connection; the first load runs showed `send` times of 2.1 s for this reason. Use `127.0.0.1` in `FB_GRAPH_BASE_URL` for local runs. Not a product defect.
8. A deprecated status-code constant in the webhook (`HTTP_413_REQUEST_ENTITY_TOO_LARGE`) was replaced.

No product feature was added.

## 7. Repeat the tests

```bash
# security + everything else
cd backend && pytest                       # all; the security suite alone: pytest tests/security
cd ai_engine && pytest
cd evaluation && pytest

# load test: see backend/scripts/loadtest/README.md
uvicorn scripts.loadtest.stub_send_api:app --port 8098
celery -A app.workers.celery_app worker --pool=threads --concurrency=50      # with FB_GRAPH_BASE_URL=http://127.0.0.1:8098
python -m scripts.loadtest.run_loadtest setup && python -m scripts.loadtest.run_loadtest run --chats 50 --label mock
```

Raw results of every run are written to `backend/scripts/loadtest/results/` (git-ignored).


---

# Part 2 (Prompt 23): deployment packaging, NFR-05 and NFR-06

Date of the runs: 2026-10-02.

## 8. Production stack, tested locally

`deploy/docker-compose.prod.yml` was built and run on the same Windows machine (Docker 29.8, Compose 5.5) with a local
configuration (`deploy/.env.prod`, git-ignored): mock AI, the load test's stub in place of Facebook (reached as
`host.docker.internal:8098`), site names `api.localhost` / `app.localhost` and HTTPS on port 8443. Caddy made its own local
certificate for them (real hosts get Let's Encrypt certificates automatically, which cannot be tried on a laptop).

| Check | Result |
|---|---|
| Images build: `shopsathi-backend` (694 MB, non-root user uid 10001, no secret in its environment or layers) and `shopsathi-frontend` (309 MB, Next.js standalone, user `node`) | Pass |
| `docker compose up -d`: postgres, redis, api, worker, beat, frontend, proxy all reach *healthy* (the worker and beat wait for the api; the proxy waits for api and frontend) | Pass |
| The api ran the Alembic migrations by itself on first start (and again, harmlessly, on every restart) | Pass |
| `GET https://api.localhost:8443/api/v1/health` through the proxy: 200 `{"status":"ok","api":"ok","database":"ok","redis":"ok"}`; `GET https://app.localhost:8443/login`: 200 | Pass |
| HTTP is redirected to HTTPS (308); HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` added by the proxy; `Server` header removed | Pass |
| API docs and `openapi.json` are not published in production (404) | Pass |
| CORS: `https://app.localhost:8443` is allowed, `https://evil.example` gets no permission | Pass |
| First run: `cli create-admin` and `cli seed` ran in a one-off container; admin login works | Pass |
| Meta's webhook handshake through HTTPS (`hub.challenge` echoed for the right verify token, 403 for a wrong one) | Pass |
| Messenger simulation script run inside the compose network (`scripts/simulate_messenger_event.py`): webhook accepted, the **worker container** answered, the reply reached the stub for the right customer | Pass |
| A correctly signed event through the HTTPS proxy: accepted and answered in 0.22 s (mock AI); a bad signature: 403 | Pass |
| Restart policy: the api process was stopped (SIGTERM); Docker started it again and it was healthy after about 35 s (note: `docker kill` is treated as a manual stop and is not restarted; that is Docker's behaviour) | Pass |
| Proxy started before the api was ready answered 503 for up to 30 s | Found and fixed: the proxy now waits for a healthy api (`depends_on: service_healthy`) and retries for 15 s (`lb_try_duration`), health checks every 10 s |
| The beat container was reported *unhealthy* because it inherited the api's health check | Found and fixed: it has its own process check |
| Site address with a port (`api.localhost:8443`) made Caddy listen on 8443 inside the container | Found and fixed: addresses must be host names only; the published port is set with `HTTPS_PORT` |

Not tested here: a real server with public DNS and Let's Encrypt, Render, Railway and Vercel deployments, and Meta's own
webhook verification and a real Facebook message. **They need accounts and credentials that were not available**; the exact
steps are in `docs/DEPLOYMENT.md` (sections 2, 3 and 5) and the first thing to do with credentials is the "Quick checks after a
deploy" in section 8 of that file.

## 9. NFR-05: a new seller signs up, adds 5 products and tests the AI in under 15 minutes

Walkthrough on the running dashboard (production build of the frontend, real model `gpt-4o-mini`, a brand new shop).
The steps were driven in the browser by script, so the times below are the **machine and network time** for every step
without a person's typing and reading; the estimate for a person follows.

| Step (all through the real screens) | Elapsed (script) |
|---|---|
| Sign up (shop name, owner name, e-mail, password, Free plan) | 4.5 s |
| Add product 1: name, price, stock | 14.9 s (includes opening the page) |
| Add products 2 to 5 (same three fields each) | 30.2 s, 34.1 s, 38.0 s, 41.8 s |
| Test chat: start a conversation, ask `Cotton Panjabi er dam koto?` | the reply `Cotton Panjabi er dam 1850 BDT.` appeared after **6.2 s** (58.5 s from the start) |

The script needs **58.5 s** in total. A person has to type about 4 fields for sign-up (about 60 characters), 3 short fields
for each of 5 products (about 120 characters), open the product form five times, and type one question: roughly 220
characters and 25 clicks, which is about 3 to 4 minutes at a slow typing speed of 20 words per minute, plus reading. Adding the
photos, sizes and colours is optional; importing a CSV/Excel file instead of typing the products takes about the same. **Estimated
total: 5 to 8 minutes, well under the 15-minute target.** A stopwatch walkthrough with a real first-time user (not done here) would
turn the estimate into a measurement; the user guide's Part 1 (sections 1 to 4) is written for that walkthrough.

## 10. NFR-06: every page at phone width (375 px) and laptop width (1366 px)

All pages were opened in a browser at both widths (each in an iframe of exactly that width, logged in as the demo owner or as a
platform admin, with the demo data: products, chats, orders, reports). For each page the check is: no horizontal scroll of the
page, and no element sticking out of the screen except inside a deliberately scrollable area. The check itself was verified
first on a page known to be too wide (it correctly reported the overflow).

| Area | Pages | 375 px | 1366 px |
|---|---|---|---|
| Public | `/`, `/login`, `/signup`, `/forgot-password`, `/reset-password` | pass | pass |
| Seller | `/dashboard`, `/dashboard/products`, `/products/new`, `/products/[id]`, `/dashboard/policy`, `/dashboard/test-chat`, `/dashboard/facebook`, `/dashboard/plan`, `/dashboard/staff`, `/dashboard/settings`, `/dashboard/inbox`, `/dashboard/inbox/[id]`, `/dashboard/orders`, `/dashboard/orders/[id]`, `/dashboard/reports` | pass | pass |
| Admin | `/admin`, `/admin/shops/[id]`, `/admin/plans`, `/admin/ai-usage`, `/admin/health` | pass | pass |

**70 of 70 checks passed; no layout bug was found, so no layout was changed.** The pages that had been looked at by eye at phone
width in earlier prompts (orders, reports, inbox, admin) were also checked this way. What this does not prove: touch-target
size, text legibility and a real phone's browser (it uses an emulated width in a desktop browser). The production container
could not be opened in the browser (its local certificate is not trusted); the same code was checked on the development server.

## 11. Final test run

Last run, after all changes of this prompt: backend `pytest` 396 passed; AI engine `pytest` 251 passed; evaluation `pytest` 82 passed;
frontend `npm run lint` clean and `npm run build` succeeded.
