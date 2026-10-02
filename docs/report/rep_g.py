"""Sections 69 to 76: conclusion, references, appendices, guides, samples, screenshots."""
import json

from rep_common import FIG, HERE, INV, SHOT

SAMPLES = json.load(open(HERE / "data" / "api_samples.json", encoding="utf8"))


def conclusion(r):
    r.h1("69. Conclusion")
    r.p("ShopSathi is a working multi-tenant web application for small Facebook shops. A shop owner can create an account, add products and a policy, test the AI, connect a Facebook Page, "
        "follow customer chats in an Inbox, take over a chat, review draft orders, confirm them and export a CSV list for the courier. "
        "The AI engine answers in Bangla, English and Banglish from the shop's own data, suggests products inside a budget, collects order details with code-side checks, and hands difficult chats to a person. "
        "A platform admin can manage shops, plans, AI cost and system health.")
    r.p("The strongest parts of the project are its safety rules and its tests. Prices and stock are read from live data, the AI cannot confirm an order, every shop is separated from the others, "
        "and 729 automated tests pass. A local load test with the real model met the 8 second target (p90 5.8 s with 50 chats on 20 shops).")
    r.p("The project also has clear gaps, and this report names them. Real Facebook was never connected, so all Messenger behaviour was tested with a simulated Facebook. "
        "The system was not deployed to a public server, so availability was not measured. The 200-message labelled test set does not exist, so the final AI accuracy is not known; "
        "on 32 sample cases the price and stock result (93.8%) was just below the 95% target. Payments are only a simulation.")
    r.p("The next steps are clear: connect a real Page and run Facebook's review, build and use the labelled test set, deploy to a public server with monitoring, and add real payments. "
        "Section 68 lists them. We think the project reached its main goal, a safe and honest first version of an AI sales agent for small Bangladeshi shops, and it leaves a clean base for these steps.")


def references(r):
    r.h1("70. References")
    r.p("These are the documents and technologies that the project used. The online documents were used as technical references while building the system; we did not copy text from them.")
    refs = [
        "ShopSathi: An AI Sales Agent for Facebook Shops. SE-331 Project Proposal Report, Daffodil International University, Department of Software Engineering (project file ShopSathi.docx).",
        "The Business Standard, July 2024: estimate of the number of f-commerce pages by the e-Commerce Association of Bangladesh. We quote it as cited in our proposal; we did not re-read the article for this report.",
        "Meta. Messenger Platform documentation (webhooks, Send API, messaging window), https://developers.facebook.com/docs/messenger-platform",
        "Meta. Facebook Login and Graph API documentation, https://developers.facebook.com/docs/",
        "OpenAI. API documentation (chat completions with JSON output, embeddings), https://platform.openai.com/docs",
        "pgvector: open-source vector similarity search for PostgreSQL, https://github.com/pgvector/pgvector",
        "PostgreSQL Global Development Group. PostgreSQL documentation, https://www.postgresql.org/docs/",
        "FastAPI documentation, https://fastapi.tiangolo.com/",
        "SQLAlchemy documentation, https://docs.sqlalchemy.org/ and Alembic documentation, https://alembic.sqlalchemy.org/",
        "Celery documentation, https://docs.celeryq.dev/ and Redis documentation, https://redis.io/docs/",
        "Next.js documentation, https://nextjs.org/docs and Tailwind CSS documentation, https://tailwindcss.com/docs",
        "LangChain documentation, https://python.langchain.com/",
        "Jones, M., Bradley, J., Sakimura, N. RFC 7519: JSON Web Token (JWT), https://www.rfc-editor.org/rfc/rfc7519",
        "Python Cryptographic Authority. cryptography: Fernet (symmetric encryption), https://cryptography.io/en/latest/fernet/",
        "Caddy web server documentation, https://caddyserver.com/docs/ and Docker documentation, https://docs.docker.com/",
        "Project documents in the repository: docs/PROGRESS.md, docs/TEST_REPORT.md, docs/DEPLOYMENT.md, docs/USER_GUIDE.md, evaluation/README.md and the report in evaluation/reports.",
    ]
    r.numbered(refs)


def appendix(r):
    r.h1("71. Appendix")
    r.h2("A. Repository layout")
    r.table(["Folder", "Content"],
            [("backend/app", "FastAPI application: api/v1/routes, services, models, schemas, core, integrations/facebook, workers, ai_adapters"),
             ("backend/alembic", "Database migrations 0001 to 0013"), ("backend/tests", "396 backend tests, including tests/security (47)"),
             ("backend/scripts", "fake_facebook, simulate_messenger_event, load test tools, AI check scripts"),
             ("ai_engine/shopsathi_ai", "The AI engine package with prompts and providers"), ("ai_engine/tests", "251 tests"),
             ("evaluation", "Evaluation harness, fixtures, sample cases, reports"), ("frontend/src", "Next.js app: app (pages), components, lib"),
             ("database", "Development compose file for PostgreSQL and Redis, init scripts, demo seed data"), ("deploy", "Production compose, Caddyfile, Render blueprint, env example"),
             ("docs", "PROGRESS, TEST_REPORT, DEPLOYMENT, USER_GUIDE, CONVENTIONS and this report's generator (docs/report)")],
            [4.0, 11.6], "Repository layout", size=9)
    r.h2("B. CSV formats")
    r.p("**Product import template** (GET /products/import/template). Sizes and colours are separated by `|`; photos are web addresses.")
    r.code("name,description,price,sizes,colours,stock,photos\nCotton Panjabi,Comfortable everyday panjabi,1850,M|L|XL,White|Navy,24,https://example.com/panjabi.jpg")
    r.p("**Order export** (GET /orders/export). UTF-8 with a byte-order mark so that Excel shows Bangla text. The first rows of the file produced from the demo data:")
    r.code("order_id,confirmed_at,customer_name,customer_phone,customer_address,product_name,size,colour,quantity,unit_price,total_price\n"
           "22,2026-08-21 13:08,Mahmuda Begum,01700001002,\"Flat 4B, Green Road, Dhaka\",Cotton Panjabi,XL,Navy,1,1850.00,1850.00\n"
           "27,2026-09-01 14:07,Zahid Hasan,01700001009,\"House 12, Road 5, Mirpur 10, Dhaka\",Homemade Mango Pickle (Achar) 500g,500g,,3,450.00,1350.00")
    r.p("The names, numbers and addresses above belong to invented demo customers.")
    r.h2("C. Database summary")
    rows = [(t, len(v["columns"]), len(v["indexes"]), len([c for c in v["constraints"] if c[0] == "CHECK"])) for t, v in INV["tables"].items()]
    r.table(["Table", "Columns", "Indexes", "CHECK rules"], rows, [6.0, 2.8, 2.8, 3.0], "Tables and counts", size=8.5, align=["l", "r", "r", "r"])
    r.h2("D. Management commands")
    r.code("python -m app.cli --help\npython -m app.cli create-admin --email <address> --full-name <name>\npython -m app.cli seed\npython -m app.cli reembed-all\npython -m app.cli reembed-shop --shop-id <id>\npython -m app.cli generate-insights --shop-id <id> --week-start <Monday date>")
    r.h2("E. Where the other numbers come from")
    r.bullets(["Test counts: `pytest --collect-only` in backend, ai_engine and evaluation, and the runs of 2 October 2026.", "API and database lists: generated from the application's OpenAPI description and SQLAlchemy metadata by `docs/report/extract_inventory.py`.",
               "Load test numbers: `docs/TEST_REPORT.md` section 3. AI evaluation: `evaluation/reports/report_20261002_002812_openai.md`."])


def install(r):
    r.h1("72. Installation Guide")
    r.p("This guide starts the system on one computer for development and testing. Needed: Docker, Python 3.11 or newer (the Docker image uses 3.12; the team ran 3.14), and Node.js 20 or newer. The commands are from the repository's README.")
    r.h2("72.1 Database and Redis")
    r.code("cd database\ncp .env.example .env\ndocker compose up -d")
    r.p("If ports 5432 or 6379 are already used, change `POSTGRES_PORT` or `REDIS_PORT` in `database/.env` and the URLs in `backend/.env`.")
    r.h2("72.2 Backend")
    r.code("cd backend\npython -m venv .venv\n.venv\\Scripts\\activate          # Windows; on Linux or Mac: source .venv/bin/activate\npip install -r requirements.txt\ncp .env.example .env            # then set JWT_SECRET (see the comment in the file)\nalembic upgrade head\npython -m app.cli seed          # optional: invented demo shops\nuvicorn app.main:app --reload")
    r.p("Open `http://localhost:8000/api/v1/health`. The answer should be `{\"status\":\"ok\",\"api\":\"ok\",\"database\":\"ok\",\"redis\":\"ok\"}`. The AI uses the mock model by default. To use OpenAI, set `LLM_PROVIDER=openai`, `EMBEDDING_PROVIDER=openai` and `OPENAI_API_KEY` in `backend/.env`.")
    r.h2("72.3 Worker and scheduler")
    r.code("celery -A app.workers.celery_app worker --loglevel=info --pool=solo\n# for many chats at once (also on Windows):\n# celery -A app.workers.celery_app worker --pool=threads --concurrency=50\ncelery -A app.workers.celery_app beat --loglevel=info")
    r.p("The worker keeps embeddings up to date and answers Messenger messages. Keep it running. Beat starts the weekly summary; run only one beat.")
    r.h2("72.4 Frontend")
    r.code("cd frontend\ncp .env.example .env.local\nnpm install\nnpm run dev")
    r.p("Open `http://localhost:3000`.")
    r.h2("72.5 Platform admin and demo data")
    r.code("python -m app.cli create-admin --email you@example.com --full-name \"Your Name\"")
    r.p("The command asks for a password. The demo seed creates two invented shops with products, chats and orders.")
    r.h2("72.6 Facebook without a Meta app (for testing)")
    r.code("uvicorn --app-dir scripts fake_facebook:app --port 8099\npython scripts/simulate_messenger_event.py --page-id <connected page id> --text \"Saree er dam koto?\"")
    r.p("The fake Facebook stands in for the Graph API; the settings to use are described at the top of `scripts/fake_facebook.py`. Replies appear at `http://localhost:8099/_debug/messages`. A real Page needs the Facebook settings in section 63 and a public HTTPS address.")
    r.h2("72.7 Tests")
    r.code("cd backend && pytest\ncd ai_engine && pytest\ncd evaluation && pytest\ncd frontend && npm run lint && npm run build")
    r.h2("72.8 Production stack with Docker")
    r.code("cd deploy\ncp .env.prod.example .env.prod\ndocker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build")
    r.p("Fill `.env.prod` first (addresses, secrets, AI key, Facebook values). The api container runs the migrations. Then create the admin with `docker compose ... run --rm api cli create-admin --email ...`. More steps are in `docs/DEPLOYMENT.md`.")


def manual(r):
    r.h1("73. User Manual")
    r.p("This manual is a short version of `docs/USER_GUIDE.md`. Menu names are in bold. The dashboard works on a phone through the **Menu** button.")
    r.h2("73.1 Shop owner")
    r.numbered(["**Sign up.** Open the site, click Sign up, enter shop name, your name, e-mail and a password of at least 8 characters, and choose a plan. Free gives 100 AI replies a month, Basic 1,000, Pro 5,000. For Basic and Pro you confirm a simulated payment; no money is taken.",
                "**Add products.** Products, then Add product. Enter name, price, stock, and optionally description, sizes, colours and up to 5 photos. For many products use Import from CSV/Excel and the template.",
                "**Write the shop policy.** Shop policy: delivery time, return rules, payment options and the delivery charge for each area. The AI quotes charges only for areas you list.",
                "**Try the AI.** Test chat, then Start new test conversation. Write like a customer, for example \"Cotton Panjabi er dam koto?\". Nothing is sent to Facebook and nothing counts against the limit.",
                "**Connect Facebook.** Facebook Page, then Connect Facebook Page. Log in with Facebook, accept the permissions, choose the Page and connect it. This needs the Facebook app settings on the server.",
                "**Work in the Inbox.** Flagged chats are on top. Open a chat to read it. Pause AI to reply yourself. Mark flag as handled when done. Resume AI to give the chat back.",
                "**Handle orders.** Orders, Draft tab. Open an order, edit it if needed, then Confirm order or Cancel order. Export confirmed orders (CSV) with an optional date range for the courier.",
                "**Read reports.** Reports shows four numbers for a date range and the weekly AI summary of top questions and missing products.",
                "**Manage staff and plan.** Staff adds moderators. My plan shows usage and lets you change the plan.",
                "**Delete the shop.** Settings, Danger zone. You need your password and the exact shop name. It cannot be undone."])
    r.h2("73.2 Moderator")
    r.p("A moderator logs in with the e-mail and password that the owner created. The moderator sees Inbox, Orders and the notification bell. In the Inbox the moderator reads chats, pauses and resumes the AI, replies and marks flags as handled. "
        "In Orders the moderator edits, confirms and cancels draft orders and exports the CSV. Products, policy, Facebook, reports, staff and settings are not available.")
    r.h2("73.3 Customer (on Messenger)")
    r.bullets(["Write to the shop's Facebook Page in Bangla, English or Banglish. The first reply says that it is the shop's automatic assistant.", "Ask about price, size, colour, stock, delivery charge or the return rule, or ask for suggestions with a budget.",
               "To order, tell the assistant which product you want. It asks for size, colour, quantity, your name, phone number and address. If the phone number is wrong it asks again.",
               "The shop confirms the order. The assistant never confirms it.", "For a complaint, a refund or a person, write it; the assistant tells you that the shop will reply. The shop answers within Facebook's 24-hour window."])
    r.h2("73.4 Platform admin")
    r.p("The admin logs in on the normal login page and sees the admin pages: **Shops** (search, open, suspend, reactivate, change plan), **Plans** (monthly limit and displayed price), **AI usage & cost** (per shop for a date range) and **System health** (API, database, Redis, worker, queue length). "
        "The admin cannot see a shop's chats, customers or orders.")


def sample_api(r):
    r.h1("74. Sample API")
    r.p("The samples are real answers of the running API on a developer computer with demo data (invented shops and customers). Tokens are replaced by `<token>`; long lists are cut to one item. "
        "Replace `$TOKEN` with the token from the login answer.")

    def js(o, limit=900):
        t = json.dumps(o, indent=2, ensure_ascii=False)
        return t if len(t) <= limit else t[:limit].rsplit("\n", 1)[0] + "\n  ..."

    r.h2("74.1 Login")
    r.code('POST /api/v1/auth/login\nContent-Type: application/json\n\n{"email": "rina.demo@example.com", "password": "<password>"}')
    r.code("200 OK\n" + js(SAMPLES["login"][1]))
    r.h2("74.2 Wrong password")
    r.code("POST /api/v1/auth/login   (wrong password)\n\n" + str(SAMPLES["wrong"][0]) + "\n" + js(SAMPLES["wrong"][1]))
    r.h2("74.3 Plan and usage")
    r.code("GET /api/v1/shop/plan\nAuthorization: Bearer $TOKEN\n\n200 OK\n" + js(SAMPLES["plan"][1]))
    r.h2("74.4 List products")
    p = SAMPLES["products"][1]
    first = dict(p["items"][0])
    r.code("GET /api/v1/products?page=1&page_size=2\nAuthorization: Bearer $TOKEN\n\n200 OK\n" + js({"items": [first], "...": "second item and paging fields follow"}, 1200))
    r.h2("74.5 Orders")
    o = SAMPLES["orders"][1]
    r.code("GET /api/v1/orders?status=confirmed&page=1&page_size=1\nAuthorization: Bearer $TOKEN\n\n200 OK\n" + js(o, 1300))
    r.h2("74.6 Report summary")
    r.code("GET /api/v1/reports/summary?from=2026-09-26&to=2026-10-02\nAuthorization: Bearer $TOKEN\n\n200 OK\n" + js(SAMPLES["report"][1]))
    r.h2("74.7 Flagged chats")
    r.code("GET /api/v1/chats?filter=flagged&page=1&page_size=1\nAuthorization: Bearer $TOKEN\n\n200 OK\n" + js(SAMPLES["chats"][1], 1400))
    r.h2("74.8 Missing query fields")
    r.code("GET /api/v1/reports/summary   (no dates)\n\n422 Unprocessable\n" + '{"detail": [{"type": "missing", "loc": ["query", "from"], "msg": "Field required"},\n            {"type": "missing", "loc": ["query", "to"], "msg": "Field required"}]}')
    r.h2("74.9 Messenger webhook event (shape)")
    r.p("Facebook sends this body to `POST /api/v1/webhooks/messenger` with the header `X-Hub-Signature-256: sha256=<hmac of the raw body>`. The values below are invented. The `scripts/simulate_messenger_event.py` tool builds and signs the same shape.")
    r.code('{"object": "page",\n "entry": [{"id": "<page id>",\n            "messaging": [{"sender": {"id": "<customer PSID>"},\n                           "recipient": {"id": "<page id>"},\n                           "timestamp": 1790000000000,\n                           "message": {"mid": "m_example_0001", "text": "Saree er dam koto?"}}]}]}')
    r.p("A correct signature gives `200`; a wrong or missing one gives `403` and nothing is stored.")
    r.h2("74.10 Health")
    r.code("GET /api/v1/health\n\n200 OK\n" + js(SAMPLES["health"][1]))


def sample_tests(r):
    r.h1("75. Sample Test Cases")
    r.p("Section 58.1 lists 68 automated test cases (TC-01 to TC-68). The table below adds manual and scripted checks that are not in a pytest file. Each was run on the date shown in the source document.")
    r.table(["ID", "Check", "Steps", "Expected", "Result", "Kind"],
            [("MT-01", "Sign-up walk-through (NFR-05)", "Script: sign up, add 5 products, ask one Test Chat question", "All steps work; reply visible", "58.5 s machine time; reply after 6.2 s", "Real model, local"),
             ("MT-02", "Page width", "Open all pages at 375 px and 1366 px", "No sideways overflow", "70 of 70 passed", "Browser check"),
             ("MT-03", "Load test, real model", "50 chats, 20 shops, 100 messages", "p90 <= 8 s", "p90 5.77 s and 5.92 s", "Real model, stub Facebook"),
             ("MT-04", "Load test, mock", "50 and 100 chats, three worker types", "Report p90", "42.8 s, 2.0 s, 2.8 s, 8.5 s", "Mock, stub Facebook"),
             ("MT-05", "Evaluation, real model", "32 sample cases", "Report the metrics", "Intent 100%, price/stock 93.8%, order fields 100%", "Real model, samples only"),
             ("MT-06", "Production compose", "Build, start seven containers, check health, HTTPS, CORS, headers", "All healthy", "Passed on a developer computer", "Local only"),
             ("MT-07", "Messenger simulation in compose", "Signed event to the webhook, worker answers, stub receives", "Reply for the right customer", "Passed; 0.22 s with the mock AI", "Simulated Facebook"),
             ("MT-08", "Screenshots for this report", "Log in as owner, moderator and admin; Test Chat order", "Pages show demo data; order draft created", "Passed; see sections 43 and 76", "Real model, local"),
             ("MT-09", "Real Facebook Page", "Connect a real Page and send a real message", "-", "Not tested", "Not done"),
             ("MT-10", "Public deployment", "Open the deployed site", "-", "Not tested", "Not done")],
            [1.2, 2.8, 4.2, 2.7, 3.2, 1.5], "Manual and scripted checks", size=7.5)


def screenshots(r):
    r.h1("76. Screenshots")
    r.p("The screenshots are real. They were captured from the running application (frontend in production mode on port 3000, API on port 8001, PostgreSQL and Redis in Docker, real OpenAI model for Test Chat) on 2 October 2026. "
        "Every image was converted to grayscale for this black and white report. Section 43 contains the main screens; the table lists all screenshots, and this section shows the extra ones.")
    from rep_c import SHOTS
    rows = []
    n = 0
    for title, items in SHOTS:
        for name, cap in items:
            n += 1
            rows.append((str(n), cap, title.split(" ", 1)[1], "Section 43"))
    extra = [("orders_confirmed", "Orders: Confirmed tab"), ("inbox_flagged", "Inbox filtered to flagged chats"), ("product_edit", "Edit product page"),
             ("notifications", "Notification list on a laptop screen (cropped)")]
    for name, cap in extra:
        n += 1
        rows.append((str(n), cap, "Extra", "Section 76"))
    n += 1
    rows.append((str(n), "Phone screens (6 images in one picture)", "Phone", "Section 43"))
    r.table(["No.", "Screen", "Group", "Shown in"], rows, [1.0, 8.0, 4.0, 2.6], "Screenshot index", size=8.5)
    r.h2("76.1 Extra screens")
    for name, cap in extra:
        r.figure(SHOT(name), "Screenshot: " + cap, 11.0 if name == "notifications" else 14.0)
    r.p("The notification list in the last image opens to the left of the bell and its left edge is slightly outside the page on a laptop screen. This is a known small layout problem (section 67). On a phone the list fits (section 43.5).")
    return n
