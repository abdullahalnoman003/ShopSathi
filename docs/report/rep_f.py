"""Sections 61 to 68: deployment, Docker, environment, CI/CD, monitoring, results, limits, future work."""
from rep_common import FIG, INV

GROUP = {
    "APP_ENV": "Core", "FRONTEND_ORIGIN": "Core", "FRONTEND_URL": "Core", "BACKEND_PUBLIC_URL": "Core", "TRUSTED_PROXIES": "Core", "MEDIA_ROOT": "Core", "MAX_UPLOAD_MB": "Limits",
    "DATABASE_URL": "Database and Redis", "DB_POOL_SIZE": "Database and Redis", "DB_MAX_OVERFLOW": "Database and Redis", "DB_POOL_TIMEOUT_SECONDS": "Database and Redis",
    "TEST_DATABASE_URL": "Database and Redis", "REDIS_URL": "Database and Redis",
    "LLM_PROVIDER": "AI", "LLM_MODEL": "AI", "EMBEDDING_PROVIDER": "AI", "EMBEDDING_MODEL": "AI", "EMBEDDING_DIM": "AI", "OPENAI_API_KEY": "AI", "GEMINI_API_KEY": "AI", "AI_COST_RATES": "AI",
    "CHAT_MEMORY_TURNS": "AI", "CHAT_MEMORY_TTL_SECONDS": "AI", "RAG_MIN_SCORE": "AI", "RAG_MIN_PRODUCT_SCORE": "AI", "AI_CONFIDENCE_THRESHOLD": "AI", "ORDER_PENDING_TTL_HOURS": "AI",
    "FB_APP_ID": "Facebook", "FB_APP_SECRET": "Facebook", "FB_GRAPH_API_VERSION": "Facebook", "FB_OAUTH_REDIRECT_URI": "Facebook", "FB_TOKEN_ENCRYPTION_KEY": "Facebook", "FB_VERIFY_TOKEN": "Facebook",
    "FB_SEND_MAX_ATTEMPTS": "Facebook", "FB_SEND_RETRY_DELAY_SECONDS": "Facebook", "FB_GRAPH_BASE_URL": "Facebook (test)", "FB_DIALOG_BASE_URL": "Facebook (test)",
    "REPORT_MAX_RANGE_DAYS": "Limits", "MAX_IMPORT_MB": "Limits", "MAX_IMPORT_ROWS": "Limits", "CELERY_TASK_ALWAYS_EAGER": "Workers",
    "JWT_SECRET": "Security", "ACCESS_TOKEN_EXPIRE_MINUTES": "Security", "PASSWORD_MIN_LENGTH": "Security", "PASSWORD_RESET_EXPIRE_MINUTES": "Security", "LOGIN_RATE_LIMIT": "Security",
    "LOGIN_RATE_WINDOW_SECONDS": "Security", "RESET_RATE_LIMIT": "Security", "RESET_RATE_WINDOW_SECONDS": "Security",
    "SMTP_HOST": "E-mail", "SMTP_PORT": "E-mail", "SMTP_USERNAME": "E-mail", "SMTP_PASSWORD": "E-mail", "SMTP_FROM": "E-mail", "SMTP_USE_TLS": "E-mail",
}
SECRET_WORDS = ("SECRET", "KEY", "TOKEN", "PASSWORD", "DATABASE_URL", "REDIS_URL", "SMTP_USERNAME")


def deployment(r):
    r.h1("61. Deployment")
    r.p("**Status in one sentence: the system was run on a developer computer, including the production Docker stack with a local certificate. It was not deployed to a public server.** "
        "The repository holds everything needed for two deployment options. Both are described in `docs/DEPLOYMENT.md`.")
    r.table(["Option", "What it uses", "Status"],
            [("A: Render + Vercel", "`deploy/render.yaml` creates the API (web service), the Celery worker, the Celery beat scheduler, a managed PostgreSQL 16 and a Redis-compatible store. The frontend goes to Vercel.", "Files written. Not deployed, not tested on Render or Vercel (accounts and credentials were not available)."),
             ("B: one server with Docker Compose", "`deploy/docker-compose.prod.yml` with Caddy (HTTPS and Let's Encrypt), frontend, api, worker, beat, postgres and redis.", "Built and run on a developer computer with a local certificate. Not run on a public server.")],
            [3.4, 7.2, 5.0], "Deployment options", size=8.5)
    r.h2("61.1 Production compose: what was checked locally")
    r.bullets(["Images build; the backend image runs as a normal user (uid 10001) and holds no secret.", "All seven containers reach the healthy state; the api runs the migrations by itself.",
               "Through the proxy: health 200, HTTP redirected to HTTPS, security headers added, API docs hidden (404), CORS allows only the frontend address.",
               "The Messenger simulation script ran inside the compose network: the worker container answered and the reply reached the stub.",
               "The api was restarted by Docker after a stop signal and was healthy after about 35 seconds.",
               "Found and fixed during this run: the proxy answered 503 before the api was ready; the beat container reported unhealthy; the site address must not contain a port."])
    r.h2("61.2 Not done")
    r.bullets(["A public domain, a real certificate from Let's Encrypt, and a running public demo.", "Facebook App settings in Meta for Developers with the production webhook URL, and Facebook App Review.",
               "A real SMTP server for password-reset e-mail.", "Backups were described (pg_dump of the database volume) but a restore was not rehearsed."])


def docker(r):
    r.h1("62. Docker")
    r.table(["Image / service", "Base and content", "Notes"],
            [("shopsathi-backend (api, worker, beat, migrate, cli)", "python:3.12-slim; installs requirements and the ai_engine package; no tests; one image for all roles chosen by the first argument", "Built from the repository root. Health check calls /api/v1/health. Photos on a volume at /data/media. Worker uses a thread pool (50 threads by default)."),
             ("shopsathi-frontend", "Next.js standalone build; user `node`", "Image about 309 MB. The backend address is compiled in at build time."),
             ("postgres", "pgvector image for PostgreSQL 16", "Named volume pgdata"), ("redis", "Redis", "Named volume redisdata"),
             ("proxy", "Caddy", "Routes the API and the frontend; HTTPS; volume caddy_data keeps certificates")],
            [3.8, 6.0, 5.8], "Docker images and services", size=8.5)
    r.p("The backend image was about 694 MB. The entrypoint `docker-entrypoint.sh` has the commands `api` (runs `alembic upgrade head`, then uvicorn), `worker`, `beat`, `migrate` and `cli`.")
    r.code("""# build and start the production stack (from the deploy folder)
cp .env.prod.example .env.prod          # then fill in the values
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.prod -f docker-compose.prod.yml ps""")
    r.p("For local development, `database/docker-compose.yml` starts only PostgreSQL with pgvector and Redis, and the API, worker and frontend run directly on the computer.")


def env_setup(r):
    r.h1("63. Environment Setup")
    r.p("All settings are environment variables, read by `backend/app/core/config.py`. No secret has a default value in the code (a test checks this). "
        "The table lists the names, the group and, for non-secret settings, the default. A secret is never printed in this report. Values for a real run go into `backend/.env` (development) or `deploy/.env.prod` (production); both files are git-ignored, and the example files `backend/.env.example` and `deploy/.env.prod.example` contain only names and safe placeholders.")
    rows = []
    for s in INV["settings"]:
        n = s["name"]
        secret = any(w in n for w in SECRET_WORDS) and n not in ("ACCESS_TOKEN_EXPIRE_MINUTES", "PASSWORD_MIN_LENGTH", "PASSWORD_RESET_EXPIRE_MINUTES", "FB_VERIFY_TOKEN_X")
        d = s["default"]
        if n == "AI_COST_RATES":
            shown = "per-model price table"
        elif secret:
            shown = "secret: not shown"
        else:
            shown = d if d != "" else "empty (set per environment)"
        rows.append((n, GROUP.get(n, "Core"), shown))
    r.table(["Variable", "Group", "Default"], rows, [5.8, 3.6, 6.2], "Settings of the backend", size=8)
    r.h2("63.1 Extra variables of the production compose")
    r.p("`deploy/.env.prod.example` adds: `API_SITE`, `FRONTEND_SITE`, `ACME_EMAIL`, `HTTP_PORT`, `HTTPS_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `ADMIN_PASSWORD`, `WORKER_CONCURRENCY` and `SHOPSATHI_VERSION`.")


def cicd(r):
    r.h1("64. CI/CD")
    r.p("Not implemented in the current version. The repository has no continuous integration workflow (no `.github/workflows` file) and no automatic deployment pipeline. "
        "The tests are run by hand with the commands in section 72. The evaluation tool has an option `--fail-on-target` that exits with an error code, so that it could be used in a pipeline later.")
    r.p("Render can build and deploy from the Git repository automatically once the Blueprint is created (`autoDeploy: true` in `render.yaml`). This was not used.")


def monitoring(r):
    r.h1("65. Monitoring")
    r.table(["Item", "What exists", "Status"],
            [("Health endpoint", "GET /api/v1/health returns 200 or 503 with api, database and redis state", "Implemented, tested"),
             ("Admin health page", "Shows API, database, Redis, the Celery worker (a ping task) and the number of jobs waiting in the queue", "Implemented, tested (screenshot in section 43)"),
             ("Docker health checks", "api, worker, beat and others have checks; the proxy waits for a healthy api", "Implemented, run locally"),
             ("AI usage and cost", "Admin page with usage and cost per shop for a date range (from ai_usage_logs)", "Implemented, tested"),
             ("Reply timings", "Each AI reply stores queue, AI and send times in the message", "Implemented, tested"),
             ("Logs", "Python logging with masking of secrets and personal numbers", "Implemented, tested"),
             ("External uptime monitor, alerts, metrics server (for example Prometheus)", "Described in docs/DEPLOYMENT.md as advice", "Not implemented in the current version")],
            [4.0, 7.6, 4.0], "Monitoring", size=8.5)
    r.p("NFR-02 (99% availability) needs a public service running for weeks with a monitor. This was not done, so availability was not measured.")


def results(r):
    r.h1("66. Results")
    r.p("The table compares the objectives of section 13 with the result.")
    r.table(["Objective", "Result", "Evidence"],
            [("1. Account, shop, products, photos, policy", "Done", "FR-01 to FR-10; test_auth, test_products, test_policy"),
             ("2. Answers in three language styles from shop data", "Done; quality measured on 32 samples only", "FR-13, FR-14; section 56"),
             ("3. Suggestions with budget", "Done", "FR-16; test_suggestions*"),
             ("4. Order collection and draft", "Done; AI never confirms", "FR-17, BR-02; test_orders*"),
             ("5. Handover", "Done: 7 reasons", "FR-18, FR-19; test_handover*"),
             ("6. Facebook Page, webhook, 24-hour window", "Done; tested with a simulated Facebook only", "FR-20 to FR-22; test_facebook, test_messenger"),
             ("7. Inbox, orders, CSV, reports, weekly summary", "Done", "FR-23 to FR-30"),
             ("8. Isolation and roles", "Done", "FR-04, FR-05; 47 security tests"),
             ("9. Plans, limits, usage, admin", "Done; payment is a simulation", "FR-31 to FR-35"),
             ("10. Measure and report honestly", "Done with limits (no 200-message test set; no real Facebook)", "Sections 51 to 60")],
            [5.8, 5.0, 4.8], "Objectives and results", size=8.5)
    r.h2("66.1 Size of the project")
    r.table(["Item", "Count"],
            [("API operations", "63 (plus the Facebook callback)"), ("Database tables / migrations", "19 / 13"), ("Backend routes files / services / models", "14 / 18 / 13"),
             ("AI engine modules (excluding prompts and providers)", "17"), ("Frontend page and layout files / shared components", "30 / 11"),
             ("Automated tests (backend / AI engine / evaluation)", "396 / 251 / 82")], [9.0, 6.6], "Size of the project", size=9)
    r.p("The counts of files come from the repository on the date of this report.")
    r.h2("66.2 Demonstration")
    r.p("The screenshots in section 43 and section 76 show the working application with demo data: the Inbox with two flagged chats, orders in three states, the reports page with the weekly AI summary, and a Test Chat in which the real model created an order draft.")


def limitations(r):
    r.h1("67. Limitations")
    r.bullets(["**Real Facebook was never used.** All Messenger work was tested with a fake Graph API, a stub Send API and signed test events. Facebook App Review was not done. Real delivery, rate limits and error codes may behave differently.",
               "**No public deployment.** Availability (NFR-02) is not measured.",
               "**No final AI accuracy.** The 200-message labelled test set does not exist. The real-model numbers come from 32 sample cases; the price and stock result (93.8%) is below the 95% target on that small sample, and the one miss was a Banglish delivery-charge question.",
               "**Speed was measured on one machine** with a stub Facebook; one worker process handles about 16 messages per second.",
               "**Payments are simulated.** No real payment provider exists in the code.",
               "**No e-mail verification of new accounts and no two-factor login.** Password-reset e-mail was not tested with a real SMTP server.",
               "**No Instagram, no voice or image understanding, no courier integration, no stock reduction on order confirmation.**",
               "**Isolation is in the application and the schema,** not in database row-level security.",
               "**Frontend has no automated browser tests;** it was checked by lint, build, page-width checks and manual runs.",
               "**Gemini provider and local embeddings** exist in the code but were not run.",
               "**Notification panel position:** on a wide screen the list opens to the left of the bell and is slightly cut off at the page edge.",
               "**No user study.** The 15-minute sign-up goal (NFR-05) is an estimate from a scripted run."])


def future(r):
    r.h1("68. Future Work")
    r.p("These items are ideas for later versions. None of them is part of the current system.")
    r.bullets(["Connect a real Facebook Page, run the App Review, and test real delivery and rate limits.", "Prepare the 200-message labelled test set from real chats (with permission), tune the prompts on a separate set, and report the accuracy targets.",
               "Deploy to a public server with a real domain, add an uptime monitor and alerts, and measure availability.", "Add real payments (for example bKash or Nagad) through a payment provider.",
               "Add a continuous integration workflow that runs the three test suites and the evaluation with the mock model.", "Add browser tests for the main flows.",
               "Instagram messaging, image understanding, and voice messages.", "Courier integration so that confirmed orders are sent automatically.", "Optional stock reduction when an order is confirmed.",
               "E-mail verification, two-factor login, and PostgreSQL row-level security as a second layer of isolation.", "Fix the notification panel position on wide screens."])
