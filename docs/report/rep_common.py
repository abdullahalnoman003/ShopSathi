"""Shared data for the report: inventory, figure helpers, requirements, use cases, access rules."""
import json
from pathlib import Path

HERE = Path(__file__).parent
INV = json.load(open(HERE / "data" / "inventory.json", encoding="utf8"))
FIG = lambda n: HERE / "figures" / f"{n}.png"
SHOT = lambda n: HERE / "shots" / f"{n}.png"

# ---------------------------------------------------------------------------------------------- access rules
PUBLIC = {("GET", "/api/v1/health"), ("GET", "/api/v1/plans"), ("POST", "/api/v1/auth/signup"), ("POST", "/api/v1/auth/login"),
          ("POST", "/api/v1/auth/password-reset/request"), ("POST", "/api/v1/auth/password-reset/confirm"),
          ("GET", "/api/v1/webhooks/messenger"), ("POST", "/api/v1/webhooks/messenger")}
ANY_USER = {("POST", "/api/v1/auth/logout"), ("GET", "/api/v1/auth/me")}


def access(method, path):
    """Returns (authentication, role) for one endpoint, from the real access table in docs/PROGRESS.md and the role tests."""
    if (method, path) in PUBLIC:
        if "webhooks" in path:
            return "Facebook (verify token / HMAC signature)", "Facebook"
        return "None", "Public"
    if (method, path) in ANY_USER:
        return "Bearer token", "Any logged-in user"
    if path.startswith("/api/v1/admin"):
        return "Bearer token", "Platform admin"
    if path.startswith(("/api/v1/chats", "/api/v1/orders", "/api/v1/notifications")) or (method, path) == ("GET", "/api/v1/shop/plan"):
        return "Bearer token", "Owner, Moderator"
    return "Bearer token", "Owner"


# ---------------------------------------------------------------------------------------------- use cases
UC = [
    ("UC-01", "Sign up and create shop", "Shop owner", "FR-01"),
    ("UC-02", "Log in and log out", "Owner, Moderator, Admin", "FR-02"),
    ("UC-03", "Reset password", "Owner, Moderator", "FR-03"),
    ("UC-04", "Manage products", "Shop owner", "FR-07"),
    ("UC-05", "Upload or delete product photos", "Shop owner", "FR-08"),
    ("UC-06", "Import products from CSV or Excel", "Shop owner", "FR-09"),
    ("UC-07", "Set shop policy and delivery charges", "Shop owner", "FR-10"),
    ("UC-08", "Try the AI in Test Chat", "Shop owner", "FR-12"),
    ("UC-09", "Connect or disconnect a Facebook Page", "Shop owner", "FR-20"),
    ("UC-10", "Add moderators", "Shop owner", "FR-06"),
    ("UC-11", "View or change plan", "Shop owner", "FR-31, FR-32"),
    ("UC-12", "Delete shop", "Shop owner", "FR-36"),
    ("UC-13", "View chat list and read chats", "Owner, Moderator", "FR-23"),
    ("UC-14", "Reply to a customer", "Owner, Moderator", "FR-25"),
    ("UC-15", "Pause or resume AI", "Owner, Moderator", "FR-24"),
    ("UC-16", "Resolve a flagged chat", "Owner, Moderator", "FR-24"),
    ("UC-17", "Review and edit draft orders", "Owner, Moderator", "FR-26"),
    ("UC-18", "Confirm or cancel an order", "Owner, Moderator", "FR-27"),
    ("UC-19", "Export confirmed orders (CSV)", "Owner, Moderator", "FR-28"),
    ("UC-20", "See notifications", "Owner, Moderator", "FR-19"),
    ("UC-21", "View reports", "Shop owner", "FR-29"),
    ("UC-22", "Read weekly AI summary", "Shop owner", "FR-30"),
    ("UC-23", "Ask about product, price or stock", "Customer", "FR-13"),
    ("UC-24", "Ask about delivery and policy", "Customer", "FR-13"),
    ("UC-25", "Ask for suggestions with a budget", "Customer", "FR-16"),
    ("UC-26", "Give order details in chat", "Customer", "FR-17"),
    ("UC-27", "Ask for a human", "Customer", "FR-18"),
    ("UC-28", "Receive AI reply (24-hour window)", "Customer", "FR-21, FR-22"),
    ("UC-29", "Detect complaint, refund or abuse", "AI engine", "FR-18"),
    ("UC-30", "Create draft order", "AI engine", "FR-17"),
    ("UC-31", "Search and view shops", "Platform admin", "FR-33"),
    ("UC-32", "Suspend or reactivate a shop", "Platform admin", "FR-33"),
    ("UC-33", "Change a shop's plan", "Platform admin", "FR-33"),
    ("UC-34", "Edit plan limits and prices", "Platform admin", "FR-34"),
    ("UC-35", "View AI usage and cost", "Platform admin", "FR-34, FR-35"),
    ("UC-36", "View system health", "Platform admin", "FR-34, FR-37"),
    ("UC-37", "Create weekly insights (scheduled)", "Scheduler", "FR-30"),
    ("UC-38", "Log in as platform admin", "Platform admin", "FR-02"),
]

# ---------------------------------------------------------------------------------------------- functional requirements
# (id, requirement, proposal ref, use case, module, api, tables, tests, status)
FR = [
    ("FR-01", "An owner can sign up with shop name, e-mail and password, choose a plan, and gets a shop and an owner account.", "FR-01", "UC-01", "Auth, Plans", "POST /auth/signup", "shops, users, plans, simulated_payments", "test_auth, test_plans", "Implemented, tested"),
    ("FR-02", "Users log in and out with a signed token; logout stops the token at once; suspended shops cannot log in.", "FR-01", "UC-02, UC-38", "Auth", "POST /auth/login, /auth/logout, GET /auth/me", "users", "test_auth, test_auth_security", "Implemented, tested"),
    ("FR-03", "A user can reset a forgotten password with a one-time link that expires.", "FR-01", "UC-03", "Auth", "POST /auth/password-reset/request, /confirm", "password_reset_tokens", "test_auth, test_webhook_and_limits", "Implemented, tested (mail is logged locally; SMTP not tested)"),
    ("FR-04", "Every shop sees only its own data; the shop is taken from the token, never from the request.", "FR-02", "All", "Tenancy", "All shop endpoints", "all shop-owned tables", "test_tenancy, test_privacy", "Implemented, tested"),
    ("FR-05", "Three roles exist: owner, moderator and platform admin, each with fixed permissions.", "FR-03", "All", "Security", "All endpoints", "users", "test_role_matrix", "Implemented, tested"),
    ("FR-06", "The owner can add moderators to the shop and list them.", "FR-03", "UC-10", "Staff", "GET/POST /shop/staff", "users", "test_staff", "Implemented, tested"),
    ("FR-07", "The owner can create, edit, delete, list and search products (name, description, price, stock, sizes, colours).", "FR-04", "UC-04", "Products", "/products", "products", "test_products", "Implemented, tested"),
    ("FR-08", "The owner can upload up to 5 photos per product (PNG, JPEG, WebP, up to 5 MB) and delete them.", "FR-04", "UC-05", "Products, Storage", "POST/DELETE /products/{id}/photos", "products", "test_products", "Implemented, tested"),
    ("FR-09", "The owner can import products from a CSV or Excel file (2 MB, 1000 rows); invalid rows are reported.", "FR-05", "UC-06", "Product import", "POST /products/import, GET /products/import/template", "products", "test_product_import", "Implemented, tested"),
    ("FR-10", "The owner stores delivery time, return rules, payment options and delivery charges per area.", "FR-06", "UC-07", "Policy", "GET/PUT /shop/policy", "shop_policies, delivery_areas", "test_policy", "Implemented, tested"),
    ("FR-11", "Products and policy are turned into embeddings and stored for semantic search; changes update them.", "AI-R13", "UC-04, UC-07", "Embeddings, Celery", "none (background)", "embedding_chunks", "test_embeddings", "Implemented, tested"),
    ("FR-12", "The owner can chat with the shop's AI in a Test Chat that sends nothing to Facebook.", "FR-09", "UC-08", "Test chat", "/test-chat/sessions", "chats, messages", "test_test_chat", "Implemented, tested"),
    ("FR-13", "The AI answers questions about price, stock, sizes, colours, delivery charge and policy using only shop data.", "AI-R03", "UC-23, UC-24", "AI engine", "(via chat)", "products, shop_policies, delivery_areas", "test_conversation, evaluation", "Implemented, tested with real model on samples"),
    ("FR-14", "The AI replies in the customer's style: Bangla script, English or Banglish.", "AI-R02", "UC-23", "AI engine", "(via chat)", "messages.language_style", "test_validators, test_test_chat", "Implemented, tested"),
    ("FR-15", "The AI remembers the last 8 turns of a chat (Redis, 6 hours) and rebuilds them from the database if Redis lost them.", "—", "UC-23", "Chat memory", "(via chat)", "messages", "test_test_chat", "Implemented, tested"),
    ("FR-16", "The AI suggests up to 3 in-stock products that fit the customer's need and budget, with photos.", "AI-R05, AI-R06", "UC-25", "Suggestions", "(via chat)", "products", "test_suggestions, test_suggestions_api", "Implemented, tested"),
    ("FR-17", "The AI collects order details, checks the phone number, product, size, colour and stock, and creates a draft order.", "AI-R07 to AI-R09", "UC-26, UC-30", "Ordering", "(via chat)", "orders, chats.pending_order", "test_orders, test_orders_api", "Implemented, tested"),
    ("FR-18", "The AI detects 7 handover reasons, stops answering, flags the chat and sends a safe reply.", "AI-R04, AI-R10", "UC-27, UC-29", "Handover", "(via chat)", "handover_events, chats", "test_handover, test_handover_api", "Implemented, tested"),
    ("FR-19", "A notification is created for each flagged Messenger chat and the seller can read it in a bell menu.", "AI-R10", "UC-20", "Notifications", "/notifications", "notifications", "test_handover_api", "Implemented, tested"),
    ("FR-20", "The owner connects one Facebook Page through Facebook login; the Page token is stored encrypted.", "FR-07", "UC-09", "Facebook", "/facebook/*", "facebook_pages", "test_facebook", "Implemented, tested with a fake Facebook only"),
    ("FR-21", "The system receives Messenger events, checks the signature, ignores duplicates and stores the message.", "FR-08", "UC-28", "Messenger webhook", "GET/POST /webhooks/messenger", "chats, messages", "test_messenger, test_webhook_and_limits", "Implemented, tested with simulated events only"),
    ("FR-22", "AI replies are sent through the Send API only inside the 24-hour window, with retries; failed sends are not counted.", "FR-08, NFR-09", "UC-28", "Messenger sender", "(worker)", "messages", "test_messenger", "Implemented, tested with a stub Send API only"),
    ("FR-23", "The seller can list chats (flagged first), filter them and read a whole conversation.", "FR-10", "UC-13", "Inbox", "GET /chats, /chats/{id}", "chats, messages", "test_inbox", "Implemented, tested"),
    ("FR-24", "The seller can pause and resume the AI for a chat and mark a flag as handled.", "FR-11", "UC-15, UC-16", "Inbox", "POST /chats/{id}/pause, /resume, /resolve-flag", "chats", "test_inbox", "Implemented, tested"),
    ("FR-25", "The seller can send a manual reply to a customer from the Inbox.", "FR-11", "UC-14", "Inbox", "POST /chats/{id}/reply", "messages", "test_inbox", "Implemented, tested with a stub Send API only"),
    ("FR-26", "The seller can list orders by status and view and edit a draft order.", "FR-12", "UC-17", "Orders", "GET /orders, /orders/{id}, PATCH /orders/{id}", "orders", "test_orders_dashboard", "Implemented, tested"),
    ("FR-27", "The seller confirms or cancels a draft order; the AI never confirms.", "FR-12, AI-R11", "UC-18", "Orders", "POST /orders/{id}/confirm, /cancel", "orders", "test_orders_dashboard, test_orders_api", "Implemented, tested"),
    ("FR-28", "The seller exports confirmed orders as a CSV file for the courier, with an optional date range.", "FR-13", "UC-19", "Orders", "GET /orders/export", "orders", "test_orders_dashboard", "Implemented, tested"),
    ("FR-29", "The owner sees a report: AI messages handled, chats handed to humans, orders drafted and confirmed.", "FR-14", "UC-21", "Reports", "GET /reports/summary", "messages, handover_events, orders", "test_reports", "Implemented, tested"),
    ("FR-30", "A weekly AI summary of customer questions and missing products is created every week (Sunday 20:00 UTC, which is Monday 02:00 in Bangladesh) and shown to the owner.", "AI-R12", "UC-22, UC-37", "Insights", "GET /reports/weekly-insights", "weekly_insights", "test_insights", "Implemented, tested with real model on demo data"),
    ("FR-31", "Each plan has a monthly limit of AI replies; replies stop at the limit; usage is counted per shop and month (Dhaka time).", "FR-15", "UC-11", "Plans, Usage", "GET /plans, GET /shop/plan", "plans, shop_message_usage", "test_plans, test_limits_under_load", "Implemented, tested"),
    ("FR-32", "Paid plans use a simulated payment confirmation; no real payment is made.", "FR-15", "UC-01, UC-11", "Plans", "POST /shop/plan/change", "simulated_payments", "test_plans", "Implemented (simulation only)"),
    ("FR-33", "The platform admin lists and searches shops, sees details, suspends or reactivates a shop and changes its plan.", "FR-16", "UC-31 to UC-33", "Admin", "/admin/shops...", "shops, admin_actions", "test_admin", "Implemented, tested"),
    ("FR-34", "The platform admin edits plans, views AI usage and cost, and checks system health.", "FR-16, NFR-08", "UC-34 to UC-36", "Admin", "/admin/plans, /admin/ai-usage, /admin/system-health", "plans, ai_usage_logs", "test_admin", "Implemented, tested"),
    ("FR-35", "Every AI call (chat, embedding, extraction, insights) is logged with tokens, cost and time per shop.", "NFR-08", "UC-35", "Usage", "(internal)", "ai_usage_logs", "test_embeddings, test_test_chat", "Implemented, tested"),
    ("FR-36", "The owner can delete the shop and all its data after entering the password and the exact shop name.", "Section 5.3", "UC-12", "Shop deletion", "DELETE /shop", "all shop-owned tables", "test_privacy", "Implemented, tested"),
    ("FR-37", "A health endpoint reports the API, database and Redis state (503 when a part is down).", "—", "UC-36", "Health", "GET /health", "none", "test_health", "Implemented, tested"),
]

NFR = [
    ("NFR-01", "AI reply within 8 seconds for 90% of messages.", "p90 5.8 s with the real model (gpt-4o-mini), 50 chats, one machine, stub Facebook. 8.5 s at 100 chats with the mock model.", "Tested locally; not tested with real Facebook"),
    ("NFR-02", "99% availability.", "Not measured. The system was never run as a public service.", "Not verified"),
    ("NFR-03", "Passwords hashed, HTTPS, tokens encrypted.", "bcrypt hashes, Fernet-encrypted Page tokens: tested. HTTPS is done by Caddy in the production compose; tested with a local certificate only.", "Partly verified"),
    ("NFR-04", "Customer data private to the shop.", "Cross-tenant sweep and 47 security tests pass.", "Tested"),
    ("NFR-05", "A new owner can sign up, add 5 products and test the AI in under 15 minutes.", "A scripted walk-through took 58.5 s of machine time; a person's time was estimated at 5 to 8 minutes, not measured with users.", "Estimated, not user-tested"),
    ("NFR-06", "Dashboard works on a phone and a laptop.", "70 of 70 page-width checks (375 px and 1366 px) showed no sideways overflow (docs/TEST_REPORT.md section 10).", "Tested"),
    ("NFR-07", "At least 20 shops and 50 simultaneous chats.", "50 chats on 20 shops: all answered, no failed message (local load test).", "Tested locally"),
    ("NFR-08", "AI usage is logged per shop.", "ai_usage_logs, one row per AI call.", "Implemented, tested"),
    ("NFR-09", "Reply only inside Facebook's 24-hour window.", "Checked in the processor and again in the sender.", "Implemented, tested"),
    ("NFR-10", "Logs must not contain secrets or customer data (added during implementation).", "Log masking tests and a conversation test that scans the logs.", "Tested"),
    ("NFR-11", "The system can be started with Docker (added during implementation).", "Production compose stack built and run locally; not deployed to a public server.", "Tested locally"),
]

BR = [
    ("BR-01", "A shop has one owner. A moderator belongs to one shop. The platform admin has no shop (database CHECK on users)."),
    ("BR-02", "The AI never confirms an order. Only the seller confirms or cancels a draft order."),
    ("BR-03", "Only a draft order can be edited, confirmed or cancelled; other states return HTTP 409."),
    ("BR-04", "The AI replies only within 24 hours of the customer's last message."),
    ("BR-05", "Each plan has a monthly AI reply limit. A reply counts only after Facebook accepted it. Test Chat is not counted."),
    ("BR-06", "A product with zero stock is never suggested. At most 3 products are suggested."),
    ("BR-07", "A Bangladesh mobile number must match 01[3-9] followed by 8 digits; otherwise the AI asks again."),
    ("BR-08", "Prices and stock come from the live product table, not from embeddings."),
    ("BR-09", "On any of 7 handover reasons the AI stops for that chat until the seller resumes it."),
    ("BR-10", "A Facebook Page can belong to one shop only, and a shop has one Page."),
    ("BR-11", "A suspended shop cannot log in, and its customers get no AI replies."),
    ("BR-12", "A paid plan needs a simulated payment confirmation. No real payment exists."),
    ("BR-13", "The first AI reply in a chat tells the customer that it is an automatic assistant."),
    ("BR-14", "A product has at most 5 photos; each is PNG, JPEG or WebP and up to 5 MB."),
    ("BR-15", "Deleting a shop needs the owner's password and the exact shop name and cannot be undone."),
    ("BR-16", "Test Chat chats and test orders are never shown in the Inbox, reports or exports."),
    ("BR-17", "Monthly usage and report days use Bangladesh time (Asia/Dhaka)."),
    ("BR-18", "A product import accepts at most 2 MB and 1000 rows; invalid rows are skipped and reported."),
]
