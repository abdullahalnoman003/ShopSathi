"""Sections 45 to 50: API documentation, AI implementation, security, tenancy, RBAC, Facebook security."""
from rep_common import FIG, INV, access

P = "/api/v1"
PURPOSE = {
    ("GET", "/health"): "Report API, database and Redis state (200 ok or 503 degraded).",
    ("POST", "/auth/signup"): "Create a shop and its owner; choose a plan; returns a token.",
    ("POST", "/auth/login"): "Log in with e-mail and password; returns a token.",
    ("POST", "/auth/logout"): "Revoke the current token.",
    ("GET", "/auth/me"): "Return the logged-in user and shop.",
    ("POST", "/auth/password-reset/request"): "Ask for a reset link (same answer for any e-mail).",
    ("POST", "/auth/password-reset/confirm"): "Set a new password with the reset token.",
    ("GET", "/plans"): "List the plans with limit and price.",
    ("GET", "/shop/plan"): "Show the shop's plan and this month's usage.",
    ("POST", "/shop/plan/change"): "Change the plan (simulated payment for paid plans).",
    ("GET", "/shop/staff"): "List moderators of the shop.",
    ("POST", "/shop/staff"): "Add a moderator.",
    ("DELETE", "/shop"): "Delete the shop and all its data (password and shop name needed).",
    ("GET", "/products"): "List and search products with paging.",
    ("POST", "/products"): "Create a product.",
    ("GET", "/products/import/template"): "Download the CSV import template.",
    ("POST", "/products/import"): "Import products from a CSV or Excel file.",
    ("GET", "/products/{product_id}"): "Read one product.",
    ("PUT", "/products/{product_id}"): "Update a product.",
    ("DELETE", "/products/{product_id}"): "Delete a product and its photos and embeddings.",
    ("POST", "/products/{product_id}/photos"): "Upload one or more photos (max 5 per product).",
    ("DELETE", "/products/{product_id}/photos/{index}"): "Remove one photo by position.",
    ("GET", "/shop/policy"): "Read the shop policy and delivery areas.",
    ("PUT", "/shop/policy"): "Save the shop policy and delivery areas.",
    ("GET", "/test-chat/sessions"): "List the owner's Test Chat sessions.",
    ("POST", "/test-chat/sessions"): "Start a Test Chat session.",
    ("GET", "/test-chat/sessions/{session_id}/messages"): "List the messages of a session.",
    ("POST", "/test-chat/sessions/{session_id}/messages"): "Send a customer message and get the AI reply.",
    ("GET", "/notifications"): "List notifications, unread first.",
    ("POST", "/notifications/read-all"): "Mark all notifications read.",
    ("POST", "/notifications/{notification_id}/read"): "Mark one notification read.",
    ("GET", "/facebook/connect-url"): "Get the Facebook login URL with a signed state.",
    ("GET", "/facebook/pages/available"): "List the Pages the owner may connect.",
    ("POST", "/facebook/pages/connect"): "Connect one of the listed Pages.",
    ("GET", "/facebook/page"): "Show the connection status.",
    ("POST", "/facebook/page/disconnect"): "Disconnect the Page and delete the stored token.",
    ("GET", "/admin/shops"): "List and search all shops.",
    ("GET", "/admin/shops/{shop_id}"): "Show one shop with counts.",
    ("POST", "/admin/shops/{shop_id}/suspend"): "Suspend a shop.",
    ("POST", "/admin/shops/{shop_id}/reactivate"): "Reactivate a shop.",
    ("POST", "/admin/shops/{shop_id}/plan"): "Change a shop's plan without payment.",
    ("GET", "/admin/plans"): "List plans for editing.",
    ("PUT", "/admin/plans/{code}"): "Edit the limit and price of a plan.",
    ("GET", "/admin/ai-usage"): "AI usage and cost per shop for a date range.",
    ("GET", "/admin/system-health"): "Check API, database, Redis and the worker.",
    ("GET", "/chats"): "List Messenger chats (all or flagged).",
    ("GET", "/chats/{chat_id}"): "Read one chat with all messages.",
    ("POST", "/chats/{chat_id}/pause"): "Pause the AI in this chat.",
    ("POST", "/chats/{chat_id}/resume"): "Resume the AI in this chat.",
    ("POST", "/chats/{chat_id}/resolve-flag"): "Mark the flag handled and its notifications read.",
    ("POST", "/chats/{chat_id}/reply"): "Send a seller reply to the customer.",
    ("GET", "/orders"): "List orders by status with paging.",
    ("GET", "/orders/export"): "Download confirmed orders as CSV.",
    ("GET", "/orders/product-options"): "Products with sizes and colours for the edit form.",
    ("GET", "/orders/{order_id}"): "Read one order.",
    ("PATCH", "/orders/{order_id}"): "Edit a draft order.",
    ("POST", "/orders/{order_id}/confirm"): "Confirm a draft order.",
    ("POST", "/orders/{order_id}/cancel"): "Cancel a draft order.",
    ("GET", "/reports/summary"): "Report numbers for a date range.",
    ("GET", "/reports/weekly-insights"): "List weeks that have a summary.",
    ("GET", "/reports/weekly-insights/{week_start}"): "Read the summary of one week.",
    ("GET", "/webhooks/messenger"): "Facebook verification handshake (verify token).",
    ("POST", "/webhooks/messenger"): "Receive Messenger events (signature checked).",
}
EXTRA_ERR = {
    ("POST", "/auth/signup"): "409 e-mail used",
    ("POST", "/auth/login"): "401 bad login; 403 suspended; 429 rate limit",
    ("POST", "/auth/password-reset/request"): "429 rate limit",
    ("POST", "/auth/password-reset/confirm"): "400 bad or expired token",
    ("POST", "/shop/staff"): "409 e-mail used",
    ("DELETE", "/shop"): "403 wrong password; 422 wrong name; 429",
    ("POST", "/products/import"): "4xx bad file, too large or too many rows",
    ("POST", "/products/{product_id}/photos"): "4xx not an image, too large or over 5 photos",
    ("POST", "/facebook/pages/connect"): "4xx Page not allowed or used by another shop",
    ("POST", "/chats/{chat_id}/reply"): "409 AI not paused, no Page or window closed; 502 Facebook refused",
    ("PATCH", "/orders/{order_id}"): "409 not a draft",
    ("POST", "/orders/{order_id}/confirm"): "409 not a draft",
    ("POST", "/orders/{order_id}/cancel"): "409 not a draft",
    ("POST", "/webhooks/messenger"): "403 bad signature; 413 body too large",
    ("GET", "/webhooks/messenger"): "403 wrong verify token",
    ("GET", "/health"): "503 degraded",
}
GROUPS = [("45.1 Health and authentication", ("/health", "/auth")), ("45.2 Plans, shop and staff", ("/plans", "/shop")), ("45.3 Products", ("/products",)),
          ("45.4 Test Chat and notifications", ("/test-chat", "/notifications")), ("45.5 Facebook", ("/facebook",)), ("45.6 Inbox", ("/chats",)),
          ("45.7 Orders", ("/orders",)), ("45.8 Reports", ("/reports",)), ("45.9 Platform admin", ("/admin",)), ("45.10 Webhook", ("/webhooks",))]


def fields(schema):
    s = INV["schemas"].get(schema)
    if not s:
        return schema
    req = set(s["required"])
    return ", ".join(p + ("" if p in req else "?") for p in s["props"])


def api(r):
    r.h1("45. API Documentation")
    r.p("The API is a FastAPI application under the prefix `/api/v1`. The list below was generated from the OpenAPI description that the application itself produces (63 operations), and the roles from the access rules that the role test checks. "
        "Authentication is a bearer token in the `Authorization` header. A name followed by `?` is an optional field. "
        "Common errors for protected endpoints are 401 (no or invalid token), 403 (role not allowed), 404 (object missing or in another shop) and 422 (invalid input); only the other errors are listed. "
        "One more endpoint is not in the OpenAPI list: `GET /api/v1/facebook/callback`, the address Facebook redirects the browser to after login (hidden from the docs).")
    r.p("The interactive API documentation (`/docs`) is published only in local runs.")
    for title, prefixes in GROUPS:
        eps = [e for e in INV["endpoints"] if e["path"][len(P):].startswith(prefixes)]
        r.h2(title)
        rows = []
        for e in eps:
            path = e["path"][len(P):]
            auth, role = access(e["method"], e["path"])
            req = []
            if e["params"]:
                req.append(", ".join(x.split(" ")[0] for x in e["params"]))
            if e["body"]:
                req.append(("multipart: " if "multipart" in e["body"][0] else "") + (fields(e["body"][1]) if "Body_" not in str(e["body"][1]) else "file(s)"))
            resp = ", ".join(f"{c} {v}".strip() for c, v in e["responses"].items() if c.startswith("2"))
            err = EXTRA_ERR.get((e["method"], path), "")
            rows.append((f"**{e['method']}**\n{path}", PURPOSE[(e["method"], path)], role, "\n".join(req) or "none", resp, err))
        r.table(["Endpoint", "Purpose", "Role", "Request", "Success", "Other errors"], rows, [3.7, 3.4, 1.8, 3.3, 1.8, 1.6], f"API: {title[5:].lower()}", size=6.8)
    r.h2("45.11 Conventions")
    r.bullets(["JSON is used everywhere except file upload (multipart) and the CSV download.", "Dates and times are ISO 8601 in UTC. Report days and the monthly limit use Bangladesh time.",
               "Lists use `page` and `page_size`. An object of another shop gives 404, never its data.", "The CORS setting allows only the configured frontend origin."])


def ai_impl(r):
    r.h1("46. AI Implementation")
    r.p("This section describes the AI engine in the package `ai_engine/shopsathi_ai`. Each part carries a status label: Implemented, Tested, Simulated, Real model, Not tested or Not implemented.")
    r.h2("46.1 Engine overview")
    r.p("The class `ConversationEngine` receives the shop id, a chat context (recent turns, pending order, language, shop name) and the customer message. It returns the reply text, the intent, the confidence, the language style, optional product cards, the pending-order state, a hand-over decision and a list of model calls for the usage log. "
        "The engine never touches the database. It reads shop data through a gateway object, which the backend implements (`ai_adapters/gateway.py`) and the evaluation harness implements in memory.")
    r.h2("46.2 Providers")
    r.table(["Part", "Options", "Default", "Status"],
            [("Chat model", "OpenAI (gpt-4o-mini), Gemini, mock", "mock (LLM_PROVIDER)", "OpenAI: Real model, tested. Gemini: Implemented, Not tested. Mock: tests only."),
             ("Embeddings", "OpenAI text-embedding-3-small (1536), local model, mock", "mock (EMBEDDING_PROVIDER)", "OpenAI: Real model, tested. Local: Implemented, Not tested here. Mock: tests only."),
             ("Output format", "JSON mode for understanding, extraction, needs and insights", "-", "Implemented, Tested"),
             ("Settings", "temperature 0.2, request timeout, one retry", "-", "Implemented")],
            [2.6, 5.2, 3.0, 4.8], "AI providers")
    r.p("The mock provider is a keyword test double. It is not an AI. Automated tests with the mock prove the pipeline and the safety rules; they do not measure answer quality.")
    r.h2("46.3 Pipeline steps")
    r.numbered(["**Language style.** `language.py` looks at the script and a list of common Banglish words. The result is bangla, english or banglish. Bangla digits are turned into ASCII digits.",
                "**Understanding.** One model call returns JSON: intent (price, size_stock, delivery, suggestion, order, complaint, other), entities such as product, size and colour, a confidence, and flags (refund, abusive language, human request, off-topic).",
                "**Hand-over decision.** `handover.py` combines the flags with a keyword check in code and the confidence threshold (0.5 by default). The first matching reason in a fixed order is used: abusive_language, refund, complaint, human_requested, off_topic, low_confidence, not_in_shop_data.",
                "**Order branch.** A second call extracts the order fields. Code then validates them (section 46.7).",
                "**Suggestion branch.** A call extracts the need; the budget is parsed in code; products are filtered from live data (section 46.6).",
                "**Facts.** Tools read the facts: vector search over the shop's chunks, product search, stock check and delivery charge.",
                "**Reply.** The reply model gets only the facts and the recent turns and writes the reply in the customer's style.",
                "**Grounding check.** Code checks that every number in the reply appears in the facts and that the script matches the style. If not, the reply is regenerated once; if it still fails, the engine says that it will check with the shop and flags the chat.",
                "**Result.** The conversation service saves the reply and logs every model call."])
    r.h2("46.4 Semantic retrieval and pgvector")
    r.p("Products and the policy are split into chunks of at most 600 characters and embedded. A product chunk is made from the product data (name, description, price, sizes, colours, stock). At question time the customer text is embedded and the nearest chunks of the same shop are read by cosine distance from `embedding_chunks` (HNSW index). "
        "Chunks below a minimum score (0.2 in general, 0.3 for products) are ignored. This finds a product when the customer uses other words, for example Banglish. "
        "Retrieval is used to find which product or policy text is meant. The price and stock in the reply always come from the `products` table, not from the chunk text. A test checks that retrieval never returns another shop's chunks.")
    r.p("Status: Implemented, Tested (mock embeddings in automated tests; OpenAI embeddings in the evaluation and load runs).")
    r.h2("46.5 Memory")
    r.p("The last 8 turns of each chat are kept in Redis for 6 hours (`CHAT_MEMORY_TURNS`, `CHAT_MEMORY_TTL_SECONDS`). If Redis lost them, the service rebuilds them from the messages table (tested). The engine gets only recent turns and the shop name, not the whole history.")
    r.h2("46.6 Suggestions and budget")
    r.p("The need is read by the model (for example gift, Eid, colour). The budget words (maximum, range, around a price) are read by code in `budget.py`, in English, Banglish and Bangla digits. "
        "Code then selects products of this shop with stock above zero and price in the budget, ranks them, and keeps at most three. The reply model only describes the selected products. "
        "So the zero-stock rule does not depend on the model. The evaluation counted 0 violations in 3 suggestions shown (a small sample).")
    r.h2("46.7 Order collection")
    r.p("`extraction.py` asks the model for product, size, colour, quantity, name, phone and address. `ordering.py` checks them in code: the product must exist in this shop and have stock, the size and colour must be in the product's lists, the quantity must be possible, and the phone must be a Bangladesh mobile number "
        "(`^01[3-9]\\d{8}$` after removing spaces, dashes, Bangla digits and a +88 prefix). If something is missing or wrong the engine asks for that item and keeps the partial data in the chat. "
        "When everything is valid the engine sets `order_ready` and the conversation service creates the draft order in one transaction. If the product sold out in the meantime, nothing is created.")
    r.h2("46.8 Hand-over (confidence and flags)")
    r.p("A reply with low confidence is not sent as a guess. The engine returns a short fixed holding reply in the customer's style that promises nothing, and the chat is flagged. For Messenger chats a notification is created. The seller can resume the AI at any time.")
    r.h2("46.9 Usage tracking and failure handling")
    r.bullets(["Each model call is logged in `ai_usage_logs` with operation (intent, chat_reply, embedding, order_extraction, suggestion_needs, weekly_insights), provider, model, tokens, estimated cost and time. The cost uses configurable rates per model.",
               "A model call has a timeout of 20 seconds and one retry. When the model fails the conversation service returns the fallback reply and flags the chat; the worker does not crash (tested with a dead model).",
               "A monthly reply is reserved before the AI work and given back if no reply was sent."])
    r.h2("46.10 What was tested and with what")
    r.table(["Area", "Automated tests (mock AI)", "Real OpenAI model", "Status"],
            [("Pipeline, safety rules, validators", "ai_engine: 251 tests; backend conversation tests", "-", "Tested"),
             ("Answer quality (intent, price and stock)", "Not meaningful with the mock", "32 sample cases, 2 minutes (section 56)", "Tested on samples only"),
             ("Order fields", "42 order tests", "24 of 24 fields on samples", "Tested on samples only"),
             ("Hand-over", "45 handover tests + 25 API tests", "6 of 6 flagged, 5 of 6 reasons right on samples", "Tested on samples only"),
             ("Speed", "-", "p90 5.8 s (local load test, section 59)", "Tested locally"),
             ("Weekly insights", "28 + 15 tests", "Run on the demo data (the demo shop's summary in section 43)", "Tested on demo data"),
             ("Gemini provider, local embeddings", "factory test only", "Not run", "Not tested")],
            [4.0, 4.0, 4.8, 2.8], "What was tested for the AI", size=8.5)
    r.h2("46.11 Limitations of the AI part")
    r.bullets(["The 200-message labelled test set from the proposal does not exist. The accuracy numbers are from 32 sample cases and are not final.",
               "The language model can still misread a message. The checks (grounding, validators, live data) reduce this but do not remove it.",
               "Bangla script quality was tested with only 6 sample cases.", "The model's speed depends on the provider on the day of the test."])


def security(r):
    r.h1("47. Security")
    r.p("This section lists only the security measures that exist in the code and that a test checks. No claim is made about a penetration test or an external audit; none was done.")
    rows = [
        ("Password storage", "bcrypt hashes, minimum length 8; no password or hash in any response or log", "test_auth_security, test_secrets"),
        ("Tokens", "HS256 JWT with expiry and unique id; tampered, forged, expired, wrong-secret and `alg: none` tokens give 401", "test_auth_security"),
        ("Logout", "The token id goes on a Redis deny list; other sessions continue", "test_auth_security"),
        ("Role checks", "Every endpoint is checked for four callers (anonymous, owner, moderator, admin); a new endpoint without a class fails the test", "test_role_matrix"),
        ("Tenant isolation", "Shop id from the token; cross-tenant sweep over all id endpoints", "test_tenancy, test_privacy"),
        ("Rate limits", "Login (10 per 5 minutes) and password reset (5 per 15 minutes) per IP and per account; shop deletion also limited", "test_webhook_and_limits, test_privacy"),
        ("Password reset", "Token stored only as a hash, valid 60 minutes, single use; same answer for unknown e-mails", "test_webhook_and_limits"),
        ("Facebook secrets", "Page token encrypted with Fernet; App Secret and keys only in environment variables; no secret in any response, in the OpenAPI schema or in the logs", "test_secrets, test_facebook"),
        ("Webhook", "HMAC-SHA256 signature of the raw body; unsigned, wrong-signature or empty-secret requests rejected and nothing stored; body size limit", "test_webhook_and_limits"),
        ("Input handling", "Pydantic validation; image type by file signature; CSV import limits; CSV export neutralises formula cells", "test_products, test_product_import, test_orders_dashboard"),
        ("Logging", "Log masking removes tokens, passwords and phone numbers, including tracebacks", "test_privacy, test_secrets"),
        ("CORS and proxy", "Only the frontend origin is allowed; forwarded headers are believed only from `TRUSTED_PROXIES`", "test_transport"),
        ("Repository", "No `.env` file with real values and no key patterns in the repository; example env files hold no secrets", "test_secrets"),
        ("Docs", "API documentation pages are published only in local runs", "test_health"),
    ]
    r.table(["Area", "Measure", "Checked by"], rows, [3.0, 9.0, 3.6], "Security measures", size=8.5)
    r.h2("47.1 Not implemented or not verified")
    r.bullets(["HTTPS and the security headers (HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy) are added by Caddy in the production compose. This was checked in a local run with a local certificate. A public server with a real certificate was not tested.",
               "Two-factor login, account lock-out after repeated failures (only rate limits exist), and e-mail verification of new accounts: Not implemented in the current version.",
               "Dependency vulnerability scanning and an external penetration test: Not done."])


def tenancy(r):
    r.h1("48. Multi-Tenant Isolation")
    r.figure(FIG("tenant"), "Multi-tenant isolation: how a request is scoped to one shop", 14.0,
             "The token holds the shop id. Services use it in every query. The database keeps the shop id on every shop-owned table with a foreign key.")
    r.bullets(["The shop id is never read from a request body or a URL; it comes from the verified token (`test_shop_id_comes_from_token_only`).",
               "A shop-scoped select helper adds `WHERE shop_id = ...` to queries; services for chats, orders, products, policy, Page and notifications use it.",
               "Asking for an object of another shop returns 404, so that the existence of the id is not shown.",
               "Retrieval filters embedding chunks by shop id before ranking; a test checks that another shop's chunks are never returned.",
               "The Messenger webhook finds the shop by the Page id; a Page only routes to its own shop, and a customer is one chat per shop.",
               "The cross-tenant sweep test logs in as the owner and moderator of shop B and calls every id endpoint of shop A; all return 403 or 404 and nothing changes.",
               "Deleting a shop removes all its rows by cascading foreign keys and leaves other shops untouched (tested)."])
    r.p("Not implemented: PostgreSQL row-level security. Isolation is enforced in the application code and the schema, not by database policies.")


def rbac(r):
    r.h1("49. Authentication/RBAC")
    r.table(["Item", "How it works"],
            [("Sign-up", "Creates an owner and a shop. A platform admin is created only by a command-line tool (`python -m app.cli create-admin`), never by the API."),
             ("Login", "E-mail and password; bcrypt check; rate limit; suspended shop refused. Returns a token valid for 720 minutes by default."),
             ("Token", "HS256 JWT with `sub`, `role`, `shop_id`, `exp` and `jti`. The secret comes from `JWT_SECRET`; a test checks that it is required and not a placeholder."),
             ("Revocation", "Logout, shop deletion and suspension stop tokens at once (deny list, user and shop status read on each request)."),
             ("Role dependencies", "`require_owner`, `require_owner_or_moderator` and `require_platform_admin`. The admin cannot use shop endpoints and a shop user cannot use admin endpoints."),
             ("Frontend", "`RoleGuard` hides pages that a role may not use. This is only for comfort; the API enforces the rules.")],
            [3.0, 12.6], "Authentication and role control", size=9)
    r.p("The access of each role to each area is shown in Table \"Permissions by role\" in section 20, and for each endpoint in section 45.")


def fb_security(r):
    r.h1("50. Facebook Security")
    r.p("No App Secret, access token, encryption key or password is printed in this report. The settings are named only (section 63).")
    r.table(["Check", "What the code does", "Test"],
            [("OAuth state", "A signed token (purpose `fb_connect`, 10 minutes, one-time nonce in Redis). Invalid, expired, reused or foreign states are rejected and nothing is stored.", "test_facebook"),
             ("Permissions", "The granted permissions must include pages_show_list, pages_messaging and pages_manage_metadata, else the owner gets a clear error.", "test_facebook"),
             ("Token handling", "The code is exchanged for a long-lived user token; the user token is not stored. The list of Pages is kept encrypted in Redis for 10 minutes. The Page token is encrypted (Fernet) before it is saved.", "test_facebook, test_secrets"),
             ("One Page rules", "A shop has one Page and a Page belongs to one shop (unique columns).", "test_facebook"),
             ("Webhook verification", "GET returns the challenge only if the verify token matches `FB_VERIFY_TOKEN`.", "test_messenger, test_webhook_and_limits"),
             ("Signature", "POST requires `X-Hub-Signature-256` = HMAC-SHA256 of the raw body with the App Secret. Without a configured secret nothing is accepted.", "test_webhook_and_limits"),
             ("Echoes and unknown Pages", "Messages sent by the Page itself, receipts and events for unknown Pages are ignored.", "test_messenger"),
             ("Duplicates", "A message id (mid) is stored once per shop (unique rule); duplicates are processed once.", "test_messenger"),
             ("24-hour window", "Checked in the processor and again in the sender; Facebook's own 'window closed' answer is not retried.", "test_messenger"),
             ("Disconnect", "Unsubscribes the Page, deletes the stored token; still works if Facebook refuses the unsubscribe.", "test_facebook"),
             ("Logs", "Errors are logged without tokens or customer text.", "test_messenger, test_secrets")],
            [3.0, 9.6, 3.0], "Facebook security checks", size=8.5)
    r.p("**What was not tested:** all these checks were tested against a fake Graph API, a stub Send API and signed test events. A real Page, a real App with live permissions, and Facebook's App Review were not used. "
        "Behaviour with real Facebook (rate limits, error codes, retries) may differ.")
