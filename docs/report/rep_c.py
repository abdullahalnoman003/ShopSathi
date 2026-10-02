"""Sections 32 to 44: architecture, database, user interface, modules."""
from rep_common import FIG, INV, SHOT

TABLE_INFO = {
    "plans": "The three plans (free, basic, pro) with the monthly AI reply limit and the price.",
    "shops": "One row per shop: name, status (active or suspended) and the plan.",
    "users": "Owners, moderators and platform admins. A platform admin has no shop.",
    "password_reset_tokens": "Hashed one-time reset tokens with an expiry and a used time.",
    "simulated_payments": "Records of the simulated payment made when a paid plan is chosen. No real money is involved.",
    "shop_message_usage": "Counter of AI replies per shop and month (period like 2026-10).",
    "products": "The shop catalogue: price, stock, sizes, colours and up to 5 photo paths.",
    "shop_policies": "One row per shop with delivery time, return rules and payment options.",
    "delivery_areas": "Delivery charge per area for a shop. Area names are unique per shop, ignoring case.",
    "embedding_chunks": "Text chunks of products and policies with their 1536-number embedding (pgvector).",
    "ai_usage_logs": "One row per AI call with operation, provider, model, tokens, estimated cost and time.",
    "chats": "A conversation with one customer (Messenger) or a Test Chat. Holds the pause and flag state and the partly collected order.",
    "messages": "Every message of a chat, from the customer, the AI or the seller, with intent, confidence and delivery details.",
    "orders": "Orders with status draft, confirmed or cancelled. The product name and price are copied so old orders stay readable.",
    "handover_events": "One row each time the AI hands a chat to the seller, with the reason.",
    "notifications": "Notifications for the seller; the only type is chat_flagged.",
    "facebook_pages": "The connected Page of a shop. The Page access token is stored encrypted.",
    "weekly_insights": "The weekly AI summary per shop: top questions and missing products.",
    "admin_actions": "A log of what the platform admin did to shops (suspend, reactivate, plan change).",
}


def architecture(r):
    r.h1("32. System Architecture")
    r.p("ShopSathi is built from a web frontend, a backend API, a background worker, a database, a cache and queue, and a separate AI engine package. "
        "The design keeps the AI engine free of any web or database code, so that it can be tested alone.")
    r.figure(FIG("sysarch"), "System architecture", 14.0,
             "The browser talks to the Next.js frontend and the FastAPI backend. In the production compose a Caddy reverse proxy sits in front and gives HTTPS. "
             "Facebook sends webhooks to the API. Long work (AI replies, embeddings, weekly insights) runs in the Celery worker, which takes jobs from Redis. "
             "PostgreSQL with pgvector stores all data. The worker calls the ai_engine package, which calls OpenAI or Gemini.")
    r.table(["Layer", "Technology (as used in the repository)", "Role"],
            [("Frontend", "Next.js 16, TypeScript, Tailwind CSS", "Seller, moderator and admin pages; calls the API with a bearer token"),
             ("Backend API", "FastAPI, SQLAlchemy 2 (synchronous), Alembic, Pydantic", "Routes, validation, services, permissions"),
             ("Worker", "Celery with Redis broker; Celery beat for the weekly job", "Reply to Messenger messages, embeddings, weekly insights"),
             ("Database", "PostgreSQL 16 with the pgvector extension", "All tables; vector(1536) with an HNSW cosine index"),
             ("Cache and queue", "Redis", "Celery queue, rate limits, token deny list, chat memory, locks, temporary Page list"),
             ("AI engine", "Python package shopsathi_ai (LangChain for OpenAI and Gemini, mock providers, optional local embeddings)", "Understanding, retrieval, suggestions, ordering, hand-over, reply checking"),
             ("Proxy (production compose)", "Caddy", "HTTPS and routing of /api and the pages"),
             ("Packaging", "Docker images for backend and frontend; docker-compose.prod.yml; render.yaml", "Run and deploy")],
            [3.0, 6.6, 6.0], "Technology stack")
    r.h2("32.1 Main design decisions")
    r.bullets(["**The AI engine does not import the backend.** The backend gives it a gateway object for shop data. This is why the evaluation harness can run the real engine against an in-memory shop.",
               "**Slow work leaves the web request.** The webhook only stores the message and queues a task, so Facebook gets a quick answer.",
               "**Facts come from tables, not from the model.** Prices and stock are read live. The language model only writes text around the facts.",
               "**Every query is scoped by shop.** Services receive the shop id from the token, and helper functions add the shop filter.",
               "**Providers are replaceable.** A setting selects the OpenAI, Gemini or mock model, and OpenAI, local or mock embeddings."])


def components(r):
    r.h1("33. Component Diagram")
    r.figure(FIG("component"), "Component diagram", 14.5,
             "The frontend calls the API routes. Routes use dependencies for login, role and shop scope, then call services. Services use the models, the integrations (Facebook client and sender) and the ai_engine package. "
             "The core package holds settings, security, encryption, rate limits and log masking.")
    r.table(["Component", "Main files", "Responsibility"],
            [("Routes", "backend/app/api/v1/routes: auth, shop, plans, products, policy, test_chat, notifications, facebook, chats, orders, reports, admin, webhooks, health", "HTTP interface, input and output schemas"),
             ("Services", "conversation, messenger_ingest, messenger_processor, facebook, usage, plans, insights, products, product_import, embeddings, chat_memory, policy, storage, shop_deletion, email, tenant", "Business logic"),
             ("Models", "backend/app/models (13 files, 19 tables)", "SQLAlchemy tables"),
             ("Integrations", "integrations/facebook: graph_client, messenger_sender, webhook", "Graph API calls, Send API with retries, signature check"),
             ("Workers", "workers: celery_app, tasks, dispatch", "Tasks: embed_product, delete_product_embeddings, embed_policy, process_incoming_message, generate_weekly_insights, ping"),
             ("AI adapters", "ai_adapters: gateway, factory", "Gives the engine shop-scoped data and builds the providers from settings"),
             ("AI engine", "ai_engine/shopsathi_ai (engine, understanding, language, handover, ordering, extraction, suggestions, budget, retrieval, tools, reply, validators, insights, chunking, prompts, providers)", "The conversation pipeline"),
             ("Frontend", "frontend/src: 30 page and layout files, 11 shared components, 14 library files", "User interface")],
            [2.6, 8.0, 5.0], "Components and their files", size=8.5)


def deployment(r):
    r.h1("34. Deployment Diagram")
    r.figure(FIG("deployment"), "Deployment diagram", 14.5,
             "Two setups were used. For development, the API, worker and frontend run directly on a computer, with PostgreSQL and Redis in Docker, and test doubles stand in for Facebook. "
             "The production compose stack (caddy, frontend, api, worker, beat, postgres, redis) was built and run on a developer computer only. A public server deployment was not done.")
    r.p("Section 61 explains the deployment files, and section 62 the Docker images.")


def ai_arch(r):
    r.h1("35. AI Architecture")
    r.figure(FIG("ai_arch"), "AI architecture: the pipeline of the engine", 14.5,
             "The engine detects the language, asks the model to understand the message, and checks the hand-over rules first. Orders, suggestions and fact questions each have their own branch. "
             "The reply is written from verified facts and then checked in code. Every model call writes a usage record.")
    r.p("Section 46 explains each step in detail.")


def messenger_arch(r):
    r.h1("36. Messenger Architecture")
    r.figure(FIG("msgr_arch"), "Messenger architecture", 14.5,
             "A customer message reaches the webhook route, which verifies the signature and calls messenger_ingest. The message is saved and a Celery task is queued. "
             "messenger_processor runs the AI engine and gives the reply to MessengerSender, which calls the Send API inside the 24-hour window. Seller replies from the Inbox use the same sender.")
    r.p("Section 50 describes the Facebook security checks.")


def er(r):
    r.h1("37. ER Diagram")
    r.p("The database has 19 tables. The overview shows which table belongs to which. The detailed diagrams show the columns. In the detailed diagrams, \"1\" marks the parent end and \"N\" the child end of a relation. "
        "The column types come from the SQLAlchemy models (the same ones that the migrations create).")
    r.figure(FIG("er_overview"), "ER overview of all 19 tables", 14.0,
             "Almost every table has a foreign key to shops. Messages, orders, hand-over events and notifications also point to chats. Password reset tokens and admin actions point to users.")
    r.figure(FIG("er_auth"), "ER diagram: plans, shops, users and usage", 14.5, "Plans, shops and users form the base. A shop has one plan; users belong to a shop (platform admins have no shop).")
    r.figure(FIG("er_catalog"), "ER diagram: catalogue, policy, embeddings and AI usage", 14.5, "Products, policy, delivery areas, embedding chunks and AI usage logs all belong to one shop.")
    r.figure(FIG("er_conv"), "ER diagram: chats, messages, orders and Facebook", 14.5, "A chat has many messages. Orders, hand-over events and notifications refer to a chat. The Facebook Page and the weekly insights belong to the shop.")


def schema(r):
    r.h1("38. Database Schema")
    r.p("The tables below are produced from the SQLAlchemy models of the project, which Alembic migrations 0001 to 0013 create. \"Key\" shows PK for primary key, FK for foreign key and the delete rule, and U for unique. "
        "Time columns are `timestamptz`. The `shop_id` column on shop-owned tables is the tenant key (section 48).")
    for i, (t, v) in enumerate(INV["tables"].items(), 1):
        r.h2(f"38.{i} Table {t}")
        r.p(TABLE_INFO[t])
        rows = []
        for c in v["columns"]:
            key = []
            if c["pk"]:
                key.append("PK")
            for fk in c["fk"]:
                key.append("FK " + fk.replace(" (NO ACTION)", "").replace(" (CASCADE)", " cascade").replace(" (SET NULL)", " set null"))
            if c["unique"]:
                key.append("U")
            typ = str(c["type"]).replace("TIMESTAMP WITH TIME ZONE", "timestamptz").replace("DATETIME", "timestamptz").replace("ARRAY", "varchar[]").replace("VARCHAR", "varchar").replace("INTEGER", "integer").replace("BOOLEAN", "boolean")
            default = c["default"] or ""
            rows.append((c["name"], typ, "no" if not c["nullable"] else "yes", ", ".join(key), default[:28]))
        r.table(["Column", "Type", "Null", "Key", "Default"], rows, [3.9, 3.8, 1.1, 4.6, 2.2], f"Columns of {t}", size=8)
        cons = [f"`{c[1] or 'unnamed unique'}`: {c[0]} ({c[2]})" if c[0] == "CHECK" else f"UNIQUE ({c[2]})" for c in v["constraints"]]
        if cons:
            r.p("**Constraints:** " + "; ".join(cons) + ".", size=9.5)


def relationships(r):
    r.h1("39. Database Relationships")
    r.p("All relations are many-to-one from the child to the parent. The delete rule tells what happens to the child when the parent row is deleted.")
    rows = []
    for t, v in INV["tables"].items():
        for c in v["columns"]:
            for fk in c["fk"]:
                parent = fk.split(" ")[0]
                rule = fk.split("(")[1].rstrip(")")
                rows.append((t, c["name"], parent, rule.lower().replace("no action", "restrict (no action)")))
    r.table(["Child table", "Column", "Parent", "On parent delete"], rows, [4.2, 3.8, 4.0, 3.6], "Foreign keys", size=8.5)
    r.h2("39.1 What the delete rules mean")
    r.bullets(["**cascade** on `shop_id`: deleting a shop deletes all its rows. This is how shop deletion (FR-36) removes the data of a shop in one statement.",
               "**set null** on `orders.chat_id`, `orders.product_id` and `orders.confirmed_by_user_id`: an order stays readable even if the chat, product or user is removed.",
               "**set null** on `admin_actions`: the admin log keeps its rows without personal shop data.",
               "**restrict** on `plan_id`: a plan that is used cannot be deleted."])
    r.h2("39.2 Tenant isolation in the database")
    r.p("Every table that holds shop data has a non-null `shop_id`. Additional composite indexes start with `shop_id`. A message has `shop_id` and `chat_id`, and the unique rule `(shop_id, external_message_id)` makes the Facebook message id unique per shop, so a duplicate webhook cannot create a second message.")


def indexing(r):
    r.h1("40. Indexing & Migration")
    r.h2("40.1 Indexes and unique rules")
    rows = []
    for t, v in INV["tables"].items():
        for name, cols, uniq in v["indexes"]:
            rows.append((t, name, ", ".join(cols), "yes" if uniq else "no"))
    r.table(["Table", "Index", "Columns", "Unique"], rows, [3.4, 6.2, 4.4, 1.6], "Indexes", size=8)
    r.p("The index `ix_embedding_chunks_embedding_hnsw` is an HNSW index with cosine distance on the vector(1536) column. A test checks that it is created. "
        "The unique partial index `uq_chats_shop_messenger_psid` allows one Messenger chat per shop and customer; Test Chat chats are not limited by it.")
    r.h2("40.2 Vector storage")
    r.p("Embeddings are stored in `embedding_chunks.embedding` as `vector(1536)`. The dimension equals the OpenAI model `text-embedding-3-small`. A text is cut into chunks of at most 600 characters. "
        "Each chunk keeps the shop id, the source type (product or policy) and the source id. Retrieval filters by shop first and then orders by cosine distance. "
        "A re-embed command can rebuild missing chunks and remove orphans, and it reports a dimension mismatch.")
    r.h2("40.3 Migrations")
    rows = [(m["rev"], m["file"], m["title"]) for m in INV["migrations"]]
    r.table(["Revision", "File", "What it creates"], rows, [1.8, 6.6, 7.2], "Alembic migrations", size=8.5)
    r.p("Migrations run with `alembic upgrade head`. The Docker entrypoint of the backend runs the migrations before the API starts. Migration 0001 is an empty first revision.")


def uiux(r):
    r.h1("41. UI/UX Design")
    r.p("The interface is plain on purpose. The users are shop owners who may not be technical, and many use a phone.")
    r.bullets(["**One top bar with the same menu on every seller page.** On a phone it becomes a Menu button.", "**Plain words.** Labels such as Orders, Inbox, Products, Shop policy and Test chat.",
               "**Clear states.** Orders are shown by tabs: Draft, Confirmed, Cancelled. Flagged chats show a label and a count.",
               "**Safe actions.** Confirm and cancel are separate; deleting the shop needs the password and the exact shop name.",
               "**Honest notes.** Test Chat shows that nothing is sent to Facebook. Reports say that the AI summary is written by AI and that counts are approximate.",
               "**Responsive layout.** Tables become cards on a phone; 70 of 70 page-width checks found no sideways overflow (section 57)."])
    r.p("The real interface uses colour for buttons and labels. The screenshots in this report are converted to grayscale to keep the report black and white.")
    r.h2("41.1 Page map")
    r.table(["Area", "Pages (route)"],
            [("Public", "/ (start), /login, /signup, /forgot-password, /reset-password"),
             ("Seller", "/dashboard, /dashboard/products, /products/new, /products/[id], /policy, /test-chat, /facebook, /plan, /staff, /settings"),
             ("Owner and moderator", "/dashboard/inbox, /inbox/[id], /orders, /orders/[id]; the notification bell on every page"),
             ("Owner", "/dashboard/reports"),
             ("Platform admin", "/admin (shops), /admin/shops/[id], /admin/plans, /admin/ai-usage, /admin/health")],
            [3.6, 12.0], "Page map of the frontend", size=9)


def wireframes(r):
    r.h1("42. Wireframes")
    r.p("The wireframes show the layout of the main pages in black and white. They were drawn from the implemented pages, not before them.")
    r.figure(FIG("wf_login"), "Wireframe: login page", 12.0, "A single centred box with e-mail, password, a Log in button and links to Forgot password and Sign up.")
    r.figure(FIG("wf_shell"), "Wireframe: seller dashboard layout", 12.0, "Every seller page has the same top bar with the menu, the notification bell and Log out, then a page title with its main action, then the content.")
    r.figure(FIG("wf_inbox"), "Wireframe: Inbox", 13.0, "The left column lists chats with filter, flags and Load more. The right side shows the open conversation, the pause or resume button and the reply box.")
    r.figure(FIG("wf_orders"), "Wireframe: Orders list and CSV export", 13.0, "Tabs for the three order states, a table of orders with a Review link, and the export box with an optional date range.")


SHOTS = [
    ("43.1 Public pages", [("login", "Login page"), ("signup", "Sign up page with plan choice"), ("forgot", "Forgot password page")]),
    ("43.2 Seller set-up", [("products", "Products list with search, stock and photos"), ("product_new", "Add product form"), ("policy", "Shop policy and delivery charges"), ("test_chat", "Test Chat before a conversation"), ("test_chat_conv", "Test Chat with an order draft (real OpenAI model)"),
                            ("facebook", "Facebook Page page (not connected)"), ("plan", "My plan with usage"), ("staff", "Staff page with a moderator")]),
    ("43.3 Daily work", [("dashboard", "Dashboard start page"), ("inbox", "Inbox with flagged chats"), ("inbox_chat", "Open conversation in the Inbox"), ("orders", "Orders: draft tab and CSV export"),
                         ("order_detail", "Order detail"), ("reports", "Reports with the weekly AI summary"), ("settings", "Settings with the danger zone")]),
    ("43.4 Moderator and admin", [("mod_dashboard", "Moderator sees the Inbox"), ("admin_shops", "Admin: shops list"), ("admin_shop_detail", "Admin: shop detail"), ("admin_plans", "Admin: plans"),
                                  ("admin_ai", "Admin: AI usage and cost"), ("admin_health", "Admin: system health")]),
]


def screens(r):
    r.h1("43. UI Screens")
    r.p("All screens are real screenshots of the running application on a developer computer, with demo data of two invented shops (names ending with \"(demo)\"). "
        "They were taken in Microsoft Edge at 1366 by 800 pixels and converted to grayscale. Section 76 repeats the full list as the screenshot index and adds the phone screens.")
    for title, items in SHOTS:
        r.h2(title)
        for n, cap in items:
            wid = 14.0
            r.figure(SHOT(n), "Screenshot: " + cap, wid)
    r.h2("43.5 Phone screens")
    r.figure(SHOT("m_all"), "Screenshots at 375 px width: dashboard, menu, products, orders, Inbox and notifications", 15.0,
             "On a phone the menu is behind a Menu button, products and orders are cards, and the notification list opens over the page.")


FEATURES = [
    ("Sign up", "Auth", "routes/auth.py, plans", "/signup", "shops, users", "POST /auth/signup", "bcrypt hash", "test_auth, test_plans", "29.1", "UC-01"),
    ("Login, logout, token", "Auth", "core/security.py", "/login", "users", "POST /auth/login, /logout", "JWT jti deny list, rate limit", "test_auth_security", "29.2, 30.6", "UC-02"),
    ("Password reset", "Auth", "routes/auth.py, services/email.py", "/forgot-password, /reset-password", "password_reset_tokens", "POST /auth/password-reset/*", "hashed single-use token", "test_auth", "29.3", "UC-03"),
    ("Shop isolation", "Tenancy", "services/tenant.py", "-", "all shop tables", "all", "shop_id from token", "test_tenancy, test_privacy", "48", "FR-04"),
    ("Owner / moderator / admin permissions", "RBAC", "core/roles.py", "RoleGuard", "users", "all", "role from database", "test_role_matrix", "20, 49", "FR-05"),
    ("Moderator accounts", "Staff", "routes/shop.py", "/staff", "users", "GET/POST /shop/staff", "owner only", "test_staff", "-", "UC-10"),
    ("Product create, edit, delete, search", "Products", "services/products.py", "/products", "products", "/products", "shop scope", "test_products", "29.4", "UC-04"),
    ("Product photo upload, delete", "Products", "services/storage.py", "ProductForm", "products.photos", "/products/{id}/photos", "magic bytes, 5 MB, 5 photos", "test_products", "29.4", "UC-05"),
    ("CSV / Excel import", "Import", "services/product_import.py", "ProductImport", "products", "POST /products/import", "size and row limits", "test_product_import", "29.5", "UC-06"),
    ("Shop policy and delivery", "Policy", "services/policy.py", "/policy", "shop_policies, delivery_areas", "/shop/policy", "length limits", "test_policy", "-", "UC-07"),
    ("Embeddings", "AI data", "services/embeddings.py, workers/tasks.py", "-", "embedding_chunks", "(background)", "shop filter", "test_embeddings", "30.7", "FR-11"),
    ("Semantic search", "AI", "ai_engine retrieval.py, tools.py", "-", "embedding_chunks", "(AI)", "never other shop's chunks", "test_embeddings_and_retrieval", "30.2", "FR-13"),
    ("Test Chat", "Chat", "routes/test_chat.py", "/test-chat", "chats, messages", "/test-chat/*", "owner only; not counted", "test_test_chat", "30.8", "UC-08"),
    ("Language handling", "AI", "language.py, reply.py", "-", "messages.language_style", "(AI)", "script check of reply", "test_validators", "35", "FR-14"),
    ("AI memory", "AI", "services/chat_memory.py", "-", "Redis, messages", "(AI)", "8 turns, 6 h", "test_test_chat", "35", "FR-15"),
    ("Suggestions, budget", "AI", "suggestions.py, budget.py", "ChatCards", "products", "(AI)", "stock > 0, max 3", "test_suggestions, test_suggestions_api", "29.7", "UC-25"),
    ("Stock checking", "AI", "tools.py, gateway.py", "-", "products", "(AI)", "live data", "test_suggestions_api", "30.2", "UC-23"),
    ("Order draft, phone validation", "AI", "ordering.py, extraction.py, validators.py", "ChatCards", "orders, chats.pending_order", "(AI)", "code-side checks", "test_orders, test_orders_api", "29.8, 30.3", "UC-26"),
    ("Order edit, confirm, cancel", "Orders", "routes/orders.py", "/orders", "orders", "/orders/{id}", "only draft changes", "test_orders_dashboard", "29.9", "UC-17, UC-18"),
    ("CSV export", "Orders", "routes/orders.py", "/orders", "orders", "GET /orders/export", "formula neutralised", "test_orders_dashboard", "29.10", "UC-19"),
    ("Handover detection", "AI", "handover.py", "Inbox flag", "handover_events, chats", "(AI)", "7 reasons, code keywords", "test_handover, test_handover_api", "29.11", "UC-27"),
    ("AI pause / resume", "Inbox", "routes/chats.py", "Inbox", "chats", "/chats/{id}/pause, /resume", "-", "test_inbox", "31.2", "UC-15"),
    ("Notifications", "Notifications", "routes/notifications.py", "NotificationBell", "notifications", "/notifications", "shop scope", "test_handover_api", "29.11", "UC-20"),
    ("Facebook Page connection", "Facebook", "services/facebook.py", "/facebook", "facebook_pages", "/facebook/*", "state, encryption", "test_facebook", "29.12, 30.5", "UC-09"),
    ("OAuth state validation", "Facebook", "services/facebook.py", "-", "Redis", "GET /facebook/callback", "signed, single-use state", "test_facebook", "29.12", "UC-09"),
    ("Token encryption", "Security", "core/crypto.py", "-", "facebook_pages", "-", "Fernet", "test_secrets", "47", "NFR-03"),
    ("Webhook verification, signature", "Messenger", "integrations/facebook/webhook.py", "-", "-", "GET/POST /webhooks/messenger", "HMAC SHA-256", "test_webhook_and_limits", "29.13", "UC-28"),
    ("Duplicate-message protection", "Messenger", "services/messenger_ingest.py", "-", "messages unique", "(webhook)", "unique (shop, mid)", "test_messenger", "29.13", "UC-28"),
    ("24-hour window", "Messenger", "messenger_sender.py", "Inbox", "chats", "(sender)", "checked twice", "test_messenger, test_limits_under_load", "29.13", "UC-28"),
    ("Seller Inbox and reply", "Inbox", "routes/chats.py", "/inbox", "chats, messages", "/chats, /chats/{id}/reply", "window check", "test_inbox", "29.14, 30.4", "UC-13, UC-14"),
    ("AI usage limits, plans, usage tracking", "Plans", "services/usage.py, plans.py", "/plan", "plans, shop_message_usage", "/plans, /shop/plan", "atomic reserve", "test_plans, test_limits_under_load", "29.13", "FR-31"),
    ("Reports", "Reports", "routes/reports.py", "/reports", "messages, orders", "/reports/summary", "owner only", "test_reports", "-", "UC-21"),
    ("Weekly insights", "Insights", "services/insights.py", "/reports", "weekly_insights", "/reports/weekly-insights", "PII removed", "test_insights", "29.16, 30.9", "UC-22"),
    ("Admin: shops, plans, usage, health", "Admin", "routes/admin.py", "/admin", "shops, plans, admin_actions", "/admin/*", "admin only", "test_admin", "24", "UC-31..36"),
    ("Shop deletion", "Privacy", "services/shop_deletion.py", "/settings", "all", "DELETE /shop", "password + name", "test_privacy", "29.15", "UC-12"),
    ("Background processing", "Workers", "workers/*", "-", "Redis", "-", "retry, lock", "test_messenger, test_insights", "30.1", "FR-21"),
    ("Error handling", "All", "routes, processor", "ui.tsx", "messages.extras", "all", "no secrets in errors", "test_messenger", "31.3", "all"),
    ("Docker", "Deploy", "Dockerfile, compose", "-", "-", "-", "-", "manual run", "34", "NFR-11"),
]


def modules(r):
    r.h1("44. Module Implementation")
    r.p("This section describes how each module is built. The table of features at the end links every implemented feature to its code, API, database tables, tests, diagram section and requirement.")
    mods = [
        ("44.1 Authentication and roles", "`routes/auth.py` handles sign-up, login, logout, `me` and password reset. Passwords are hashed with bcrypt. A token (HS256 JWT, 720 minutes by default) carries the user id, the role, the shop id and a unique `jti`. "
         "On logout the `jti` is stored in Redis until the token expires; every protected request checks that list. The role is read from the database. Login and reset are rate limited per IP and per e-mail."),
        ("44.2 Tenancy", "The shop id comes from the token. `services/tenant.py` has `scoped_select`, which adds the shop filter. A request for another shop's object returns 404 (not 403), so that ids of other shops are not revealed."),
        ("44.3 Products, photos and import", "`services/products.py` creates, updates and deletes products and calls a change hook, which queues the embedding task. Photos are saved by `services/storage.py` after a check of the real file signature (PNG, JPEG, WebP), the 5 MB limit and the 5-photo limit; if one file in an upload is not a valid image, the whole upload is rejected. "
         "The import reads CSV or Excel with pandas, checks each row with the same schema as a manual product and reports failed rows."),
        ("44.4 Policy and delivery", "One policy row per shop (delivery time, return rules, payment options) and delivery areas with charges. Saving the policy queues the policy embedding. The AI tool `get_delivery_charge` reads the area charge."),
        ("44.5 Embeddings and retrieval", "`services/embeddings.py` and the worker tasks turn products and policy into chunks (at most 600 characters) and embeddings, replace old chunks, and drop a stale result if the product changed during embedding. Every embedding call writes an `ai_usage_logs` row."),
        ("44.6 Conversation service", "`services/conversation.py` is the one entry point for Test Chat and Messenger. It loads the chat memory, calls the engine through the gateway, saves the AI message, the pending order, the draft order, the hand-over event and the notification, and logs usage. A model outage gives the fallback reply."),
        ("44.7 Messenger ingest and processor", "`messenger_ingest.py` checks events, finds or creates the chat, saves the message and queues the task. `messenger_processor.py` takes a Redis lock per chat, applies the skip rules, reserves one reply from the allowance, runs the engine, sends the reply, sets `sent_at`, and gives the reservation back if nothing was sent. "
         "A retried task does not answer twice."),
        ("44.8 Facebook integration", "`services/facebook.py` creates the OAuth login URL, checks the state, exchanges the code, reads the permissions and Pages, and connects or disconnects a Page. `graph_client.py` follows paging and parses Facebook errors. `messenger_sender.py` sends text and photos with retries for temporary errors."),
        ("44.9 Inbox and orders", "`routes/chats.py` lists chats (flagged first), shows a chat, pauses, resumes, resolves a flag and sends a manual reply. `routes/orders.py` lists orders by status, edits a draft, confirms, cancels and exports. Changing the product of a draft takes the catalogue price and re-checks size and colour."),
        ("44.10 Plans, usage and payment simulation", "`services/plans.py` and `usage.py` handle the plans and the monthly counter. `reserve_ai_reply` and `release_ai_reply` change the counter atomically in SQL, so many chats at the same moment cannot pass the limit. Payment is a stored record `simulated_success`; no payment provider is called."),
        ("44.11 Reports and weekly insights", "`routes/reports.py` counts AI messages sent, chats handed over, orders drafted and confirmed, by Bangladesh day. `services/insights.py` runs the weekly job: it takes the customer messages of one week (Monday to Sunday), removes names and phone numbers, asks the model to summarise in batches and combine, and stores the top questions and the missing products. The catalogue, not the model, decides whether a product exists."),
        ("44.12 Admin", "`routes/admin.py` lists and searches shops, shows details, suspends and reactivates (with a log row), changes plans, edits plan limits, summarises AI usage and cost for a date range, and checks system health (API, database, Redis and a Celery ping)."),
        ("44.13 Shop deletion and privacy", "`services/shop_deletion.py` unsubscribes the Page (best effort), removes photo files and Redis keys, and deletes the shop row; foreign keys remove the rest. `core/log_masking.py` hides tokens, passwords and phone numbers in log records."),
        ("44.14 Frontend", "Next.js app router pages call the API through `lib/client.ts`, which adds the bearer token. `AuthProvider` keeps the user, `RoleGuard` hides pages from roles that may not see them, and small components handle the Inbox, product forms, plan picker, chat cards and the notification bell."),
    ]
    for t, text in mods:
        r.h2(t)
        r.p(text)
    r.h2("44.15 Feature inventory")
    r.p("Table of all implemented features with the files, API, database tables, security rule, tests and the report section that explains them. Section numbers refer to subsections of this report.")
    rows = [(f[0], f[1], f[2] + "\nUI: " + f[3], f[4], f[5], f[6], f[7], f[8]) for f in FEATURES]
    r.table(["Feature", "Module", "Backend / UI", "Database", "API", "Security / AI rule", "Tests", "Sect."], rows, [2.5, 1.3, 3.0, 2.0, 2.1, 1.9, 1.7, 1.1], "Feature inventory", size=6.5)
