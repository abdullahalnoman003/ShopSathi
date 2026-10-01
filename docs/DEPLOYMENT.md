# Deploying ShopSathi (live demo with HTTPS)

ShopSathi is deployed as separate pieces. Facebook only sends webhooks to an **HTTPS** address, so every public address
below must be HTTPS.

| Piece | What it is | Where it can run |
|---|---|---|
| **api** | FastAPI backend: login, dashboard API, Messenger webhook. Runs the database migrations when it starts | Render, Railway or a VPS (Docker) |
| **worker** | Celery worker: answers customers' Messenger messages with the AI | same place as the api |
| **beat** | Celery scheduler: makes the weekly AI summary. Exactly **one** | same place |
| **frontend** | Next.js dashboard and admin panel | **Vercel** (recommended) or the VPS |
| **PostgreSQL + pgvector** | the database (the migrations enable the `vector` extension) | managed database, or the VPS stack |
| **Redis** | queue, rate limits, chat memory | managed Redis / Key Value, or the VPS stack |
| **media** | product photos, a folder on a persistent disk or volume | with the api |

Two ways are described: **A. Render (or Railway) + Vercel** and **B. One VPS with Docker Compose** (includes the HTTPS proxy).
Read "Facebook setup", "Production settings" and "Availability" for either.

> **Before you start.** Everything in this repository must be committed and pushed, including `frontend/` (Vercel and Render
> build from the repository). Keep `.env` files out of git (they are ignored); secrets are typed into the hosting dashboard.

---

## 1. Environment variables

The full, commented list is `backend/.env.example` (backend) and `frontend/.env.example`. Generate secrets with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"                       # JWT_SECRET, passwords
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # FB_TOKEN_ENCRYPTION_KEY
```

### api (all variables) and what the others need

| Variable | api | worker | beat | Meaning / production value |
|---|:-:|:-:|:-:|---|
| `APP_ENV` | x | x | x | `production` (hides the API docs, no development logging of e-mails) |
| `DATABASE_URL` | x | x | x | PostgreSQL address. `postgres://` / `postgresql://` addresses from Render or Railway are accepted as they are |
| `REDIS_URL` | x | x | x | Redis address |
| `JWT_SECRET` | x | x | x | long random secret; the same value for all three. **Required** |
| `FRONTEND_ORIGIN` | x | | | the frontend's address, e.g. `https://shopsathi.vercel.app`. **CORS allows only this origin** |
| `FRONTEND_URL` | x | | | where the browser returns after Facebook login (same address) |
| `BACKEND_PUBLIC_URL` | x | x | | this backend's public `https://` address; product photo links are built from it and Facebook downloads photos from it |
| `TRUSTED_PROXIES` | x | | | the proxy in front of the api. `*` is fine when the api is reachable only through the platform's/ Caddy's proxy. Needed so rate limits see the real visitor |
| `MEDIA_ROOT` | x | | | folder for product photos: put it on a persistent disk/volume (`/data/media` in the image) |
| `MAX_UPLOAD_MB`, `MAX_IMPORT_MB`, `MAX_IMPORT_ROWS` | x | | | upload and CSV import limits |
| `ACCESS_TOKEN_EXPIRE_MINUTES`, `PASSWORD_MIN_LENGTH`, `PASSWORD_RESET_EXPIRE_MINUTES`, `LOGIN_RATE_LIMIT`, `LOGIN_RATE_WINDOW_SECONDS`, `RESET_RATE_LIMIT`, `RESET_RATE_WINDOW_SECONDS` | x | | | sign-in settings (defaults are fine) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS` | x | | | e-mail for password reset. **Without `SMTP_HOST` no e-mail is sent** (and in production nothing is logged either), so password reset does not work |
| `ADMIN_PASSWORD`, `DEMO_PASSWORD` | | | | used only by the one-time commands (`create-admin`, `seed`); not needed by the running services |
| `FB_APP_ID`, `FB_APP_SECRET` | x | x | | the Meta app |
| `FB_GRAPH_API_VERSION` | x | x | | `v21.0` |
| `FB_OAUTH_REDIRECT_URI` | x | | | `https://<api>/api/v1/facebook/callback` |
| `FB_VERIFY_TOKEN` | x | | | the secret you also type into Meta's webhook settings |
| `FB_TOKEN_ENCRYPTION_KEY` | x | x | | Fernet key that encrypts Page tokens. **Back it up**: without it the connected Pages must be connected again |
| `FB_SEND_MAX_ATTEMPTS`, `FB_SEND_RETRY_DELAY_SECONDS` | | x | | sending retries (defaults are fine) |
| `LLM_PROVIDER`, `LLM_MODEL`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIM` | x | x | | `openai` / `gpt-4o-mini` / `openai` / `text-embedding-3-small` / `1536`. **Never `mock` in production** (`mock` is a test double, not AI) |
| `OPENAI_API_KEY` (or `GEMINI_API_KEY`) | x | x | | the AI key (the api needs it too: product embeddings, test chat) |
| `AI_COST_RATES`, `CHAT_MEMORY_*`, `RAG_*`, `AI_CONFIDENCE_THRESHOLD`, `ORDER_PENDING_TTL_HOURS`, `REPORT_MAX_RANGE_DAYS` | x | x | | tuning (defaults are fine) |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_SECONDS` | x | x | | connection pool per process. **The worker needs about `WORKER_CONCURRENCY` connections**, and the database must allow the total (see below) |
| `WORKER_CONCURRENCY` | | x | | threads of the worker (default 50; 20 on a small instance) |
| `WEB_CONCURRENCY` | x | | | uvicorn processes of the api (default 1) |
| `PORT` | x | | | set by Render/Railway; default 8000 |
| `RUN_MIGRATIONS` | x | | | `true` (default): the api runs `alembic upgrade head` when it starts |

**frontend** (Vercel or the VPS image): only `NEXT_PUBLIC_API_BASE_URL` = the backend's public `https://` address, no trailing
slash. It is **public by design** (the browser calls the API); never put a secret in a `NEXT_PUBLIC_` variable. It is compiled
into the pages: after changing it, deploy the frontend again.

**Database connections.** One worker with 50 threads holds up to about 60 connections, the api 30, so the database should allow
at least 100 (the VPS stack sets 200). On a small managed database lower `WORKER_CONCURRENCY` and `DB_POOL_SIZE` together.

---

## 2. Option A: Render (backend) + Vercel (frontend)

### 2.1 Backend on Render

1. Push the repository to GitHub/GitLab.
2. Render dashboard: **New > Blueprint**, pick the repository, file `deploy/render.yaml`. It creates the api (web service, Docker),
   the worker, the beat, a PostgreSQL 16 database and a Key Value (Redis) store, and asks for the values marked
   `sync: false` (secrets and your own addresses; the list is in section 1). The api's health check is already set to
   `/api/v1/health`.
3. The first deploy builds `backend/Dockerfile` (about 5 minutes), the api runs the migrations (`CREATE EXTENSION vector` is
   part of them; Render PostgreSQL supports pgvector) and starts. Open `https://<api>.onrender.com/api/v1/health`: it must show `"status":"ok"`.
4. Give the api service a **persistent disk** (the Blueprint asks for one on `/data/media`; disks need a paid instance). Without
   it product photos disappear on every deploy.
5. Use a paid plan for the demo period (NFR-02): free web services sleep when idle and the free database expires.

Railway works the same way without a Blueprint file: create a project with a PostgreSQL (pgvector template) and a Redis
service, then three services from the same repository, each with **Dockerfile path `backend/Dockerfile`**, root directory
the repository root, and the start command `api` (default), `worker` or `beat`. Add the variables of section 1 (Railway's
`DATABASE_URL` and `REDIS_URL` references work as they are). Add a volume at `/data/media` to the api and set the
health check path `/api/v1/health`.

### 2.2 Frontend on Vercel

1. Vercel: **Add New > Project**, import the repository, **Root Directory: `frontend`** (framework: Next.js is detected).
2. Environment variable `NEXT_PUBLIC_API_BASE_URL` = `https://<api>.onrender.com` (production and preview).
3. Deploy. Then put the Vercel address into the backend's `FRONTEND_ORIGIN` and `FRONTEND_URL` and redeploy the api (CORS).
   If you add your own domain in Vercel, use that address everywhere.

---

## 3. Option B: one VPS with Docker Compose (HTTPS included)

Needs a server with Docker (2 CPU / 4 GB is enough for the demo) and two DNS names pointing to its IP address, for example
`api.example.com` and `app.example.com`. Ports 80 and 443 must be open.

```bash
git clone <repository> && cd ShopSathi/deploy
cp .env.prod.example .env.prod          # fill it in: addresses, secrets, AI key, Facebook values
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
```

What it starts (separate containers, only the proxy publishes ports): `proxy` (Caddy: gets and renews the Let's Encrypt
certificates by itself, redirects HTTP to HTTPS, adds HSTS and other security headers), `frontend` (Next.js), `api` (runs the
migrations, then FastAPI), `worker`, `beat`, `postgres` (pgvector) and `redis`. Data lives in the volumes `pgdata`,
`redisdata`, `media` (product photos) and `caddy_data` (certificates: keep it). All containers restart automatically
(`restart: unless-stopped`) and have health checks; the worker and beat wait until the api is healthy.

Update: `git pull && docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build` (the api migrates the
database on start). `BACKEND_PUBLIC_URL` is compiled into the frontend image, so it is rebuilt when you change it.

Back up: the `pgdata` and `media` volumes and your `.env.prod` (especially `FB_TOKEN_ENCRYPTION_KEY`):

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml exec postgres pg_dump -U shopsathi shopsathi | gzip > shopsathi-$(date +%F).sql.gz
```

---

## 4. First run

The api runs the migrations by itself (the three plans are created by them). Then, once:

```bash
# create the platform admin (the password comes from ADMIN_PASSWORD, else you are asked)
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm api cli create-admin --email you@example.com
# optional: two fictional demo shops with products, chats and orders (for a demo only)
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm -e DEMO_PASSWORD=choose-a-password api cli seed
```

On Render/Railway use the service's shell (`/srv/shopsathi/backend/docker-entrypoint.sh cli create-admin --email ...`, with
`ADMIN_PASSWORD` set for that command). Then open the frontend address and log in; the platform admin is sent to `/admin`.
Sellers sign up themselves on `/signup`.

---

## 5. Facebook setup (Meta for Developers)

Do this after the backend is online over HTTPS.

1. https://developers.facebook.com/apps > **Create app** (type: Business). Note the **App ID** and **App secret** (Settings > Basic): they are `FB_APP_ID` and `FB_APP_SECRET`.
2. Add the products **Facebook Login** and **Messenger**.
3. **Facebook Login > Settings > Valid OAuth Redirect URIs**: add exactly `https://<api>/api/v1/facebook/callback` (the same value as `FB_OAUTH_REDIRECT_URI`).
4. **Messenger > Settings > Webhooks > Add Callback URL**:
   * Callback URL: `https://<api>/api/v1/webhooks/messenger`
   * Verify token: the value of `FB_VERIFY_TOKEN`
   * Click **Verify and save**. Meta calls the URL; the backend answers the challenge only for the right token. If it fails: check the address is HTTPS and reachable, the token matches, and the api is running.
   * Subscribe the webhook fields: **`messages`** (the app also subscribes each connected Page to `messages` itself).
5. **Permissions:** `pages_show_list`, `pages_messaging`, `pages_manage_metadata`. While the app is in **Development mode** only people with a role on the app (admin, developer, tester: add them under App roles) can log in and message the Page; for other people the app needs Meta's App Review and Live mode. For the demo, add the seller and the test customers as testers.
6. Create a **test Facebook Page** (or use one you manage). The seller opens the dashboard > **Facebook Page** > **Connect**, logs in with Facebook and picks the Page. The backend stores the Page token encrypted and subscribes the Page to the webhook.
7. From another Facebook account (a tester), message the Page. The reply should arrive within a few seconds, and the chat appears in the dashboard **Inbox**. Meta only lets a Page reply **within 24 hours of the customer's last message**; ShopSathi never sends outside it.

Messages for a Page that is not connected are ignored. A webhook signature check (`X-Hub-Signature-256` with `FB_APP_SECRET`) rejects anything not sent by Meta.

---

## 6. Production settings checklist

* [ ] All public addresses are **https://** (api, frontend). The backend itself speaks HTTP and must sit behind HTTPS (Render/Railway/Vercel do this; on a VPS the Caddy proxy does).
* [ ] `APP_ENV=production` (API docs hidden, no development logging); the services run without `--reload`.
* [ ] **CORS** is limited to `FRONTEND_ORIGIN` (one origin, no `*`).
* [ ] `TRUSTED_PROXIES` is set to the proxy in front of the api, so rate limits and https links use the real visitor.
* [ ] `JWT_SECRET` and `FB_TOKEN_ENCRYPTION_KEY` are long random values, stored only in the hosting dashboard / `.env.prod`; `LLM_PROVIDER` and `EMBEDDING_PROVIDER` are not `mock`.
* [ ] No cookies are used (the dashboard sends its token in the `Authorization` header), so there are no cookie flags to set. The proxy adds `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options` and `Referrer-Policy`; on Vercel add them in the project settings if you want them there too.
* [ ] SMTP is configured (otherwise password reset cannot send e-mail).
* [ ] The database and Redis are not reachable from the internet (private network / no published ports).
* [ ] `.env.prod`, `backend/.env` and keys are not in git (`pytest tests/security` checks the repository).

---

## 7. Availability (NFR-02: 99% during the demo and testing period)

* **Health check:** point the platform at `GET /api/v1/health`. It answers **200** with `{"status":"ok"}` when the API, the database and Redis work, and **503** with `"degraded"` when the database or Redis is down, so the platform restarts or alerts. (Render: set by the Blueprint. Railway: Settings > Healthcheck path. VPS: Docker health checks and Caddy's own check.)
* **Restarts:** Render/Railway restart crashed services; on the VPS every container has `restart: unless-stopped` and a health check (api: the health URL, worker: `celery inspect ping`). Run a **single** beat.
* **Uptime monitoring:** create a free monitor (UptimeRobot, Better Stack or similar) that requests `https://<api>/api/v1/health` every 1 to 5 minutes, expects status 200 and the text `"status":"ok"`, and alerts by e-mail/SMS. A second monitor for the frontend address. 99% over 30 days allows about 7 hours of downtime; the monitor's report is the evidence.
* **Inside the app:** the platform admin's **System health** page shows API, database, Redis, the worker and the number of jobs waiting in the queue. A growing queue means the worker is down or too small.
* **Watch the AI bill:** the admin's **AI usage & cost** page; set a spending limit in the OpenAI dashboard.
* **Logs:** the platform's log view (`docker compose logs -f api worker` on a VPS). Logs contain no passwords, tokens or customer details (masked).
* Keep the demo on paid plans that do not sleep, and avoid deploying during the demo or the tests.

---

## 8. Quick checks after a deploy

```bash
curl -i https://<api>/api/v1/health                      # 200 {"status":"ok",...}
curl -i https://<api>/api/v1/webhooks/messenger?hub.mode=subscribe\&hub.verify_token=<FB_VERIFY_TOKEN>\&hub.challenge=123   # 200, body 123
curl -i -H "Origin: https://evil.example" https://<api>/api/v1/health    # no access-control-allow-origin header
```

Then: sign up on the frontend, add a product, use the **Test chat**, connect the Facebook Page and message it. The step-by-step
guide for sellers and the admin is `docs/USER_GUIDE.md`.

Test a stack on your own computer (without Facebook): see "Production stack, tested locally" (Part 2, section 8) in `docs/TEST_REPORT.md`
(it uses `API_SITE=api.localhost:8443`, a local certificate from Caddy and the stub Send API of the load test).
