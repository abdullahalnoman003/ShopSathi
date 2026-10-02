"""Batch C: activity and sequence diagrams for the real workflows."""
from dgflow import activity
from dgkit import sequence

S = ("start",)
E = ("end",)


def A(t):
    return ("act", t)


def D(q, branch, side="no", rejoin=False, main_label=None, side_label=None):
    o = {"branch": branch, "side": side, "rejoin": rejoin}
    if main_label:
        o["main_label"] = main_label
    if side_label:
        o["side_label"] = side_label
    return ("dec", q, o)


ACT = {}

ACT["act_signup"] = [S, A("Visitor opens the Sign up page"), A("Enters shop name, owner name, e-mail, password and chooses a plan"),
                     D("Data valid and plan choice allowed?", [A("Show the error (422)"), E]),
                     D("E-mail already registered?", [A("Show 'Email is already registered' (409)"), E], side="yes", main_label="no"),
                     A("Create the shop (status active) and the owner user (bcrypt password hash)"),
                     A("Save a simulated payment record if a paid plan was chosen"),
                     A("Create the access token (JWT) and return it with the user"), A("Dashboard opens"), E]

ACT["act_login"] = [S, A("User enters e-mail and password"),
                    D("Too many attempts from this IP or e-mail?", [A("Reject with 429"), E], side="yes", main_label="no"),
                    D("E-mail and password correct and user active?", [A("Reject with 401 'Invalid email or password'"), E]),
                    D("Shop suspended?", [A("Reject with 403 'Shop suspended'"), E], side="yes", main_label="no"),
                    A("Create JWT with user id, role, shop id and a unique jti"), A("Browser keeps the token; dashboard or admin page opens"),
                    A("On log out: store the jti in the Redis deny list until the token would expire"), E]

ACT["act_reset"] = [S, A("User enters the e-mail on 'Forgot password'"), A("Rate limit check by IP and by e-mail"),
                    D("Active user with this e-mail?", [A("Do nothing, show the same message"), E]),
                    A("Store a hashed one-time token (valid 60 minutes)"), A("Send the link by e-mail in the background\n(written to the log only in local mode)"),
                    A("Show 'If that email is registered, a reset link has been sent'"), A("User opens the link and enters a new password"),
                    D("Token exists, unused and not expired?", [A("Reject with 400 'Invalid or expired reset link'"), E]),
                    A("Save the new password hash and mark the token used"), E]

ACT["act_product"] = [S, A("Owner fills the product form (name, price, sizes, colours, stock, description)"),
                      D("Data valid?", [A("Show the validation errors"), E]),
                      A("Save the product for the owner's shop"), A("Queue an embedding task in Celery"),
                      A("Worker builds the product text and its embedding and stores it in embedding_chunks"),
                      A("Owner uploads photos (PNG, JPEG or WebP, up to 5 MB each)"),
                      D("Real image type and size allowed?", [A("Reject with 400"), E]),
                      A("Save the photo and keep its path in the product; a photo can be deleted by its number"), E]

ACT["act_import"] = [S, A("Owner downloads the CSV template (optional)"), A("Owner uploads a CSV or Excel file"),
                     D("File type, size (2 MB) and row count (1000) allowed?", [A("Reject the file with an error message"), E]),
                     A("Read every row and validate it with the same rules as a manual product"),
                     A("Create each valid row as a product (embedding task queued)"), A("Skip invalid rows and note the row number and reason"),
                     A("Show how many rows were created and which rows failed"), E]

ACT["act_ai"] = [S, A("Customer message arrives (Messenger or Test Chat)"), A("Load the last 8 turns of this chat from Redis"),
                 A("Detect the language style (Bangla, English or Banglish)"), A("Understanding step (LLM): intent, entities, confidence"),
                 D("Handover reason found?", [A("Save handover event, flag the chat, pause the AI, create a notification"), A("Send a fixed safe reply"), E], side="yes", main_label="no"),
                 D("Intent is an order?", [A("Extract order fields, check them in code,\nask again or create the draft order"), A("Reply from the order result"), E], side="yes", main_label="no"),
                 D("Intent is a suggestion?", [A("Find needs and budget, filter live products in code (max 3, in stock)"), A("Reply LLM writes the text; product cards are attached"), E], side="yes", main_label="no"),
                 A("Collect facts with tools: vector search, product search, stock, delivery charge"),
                 A("Reply LLM writes the answer from the facts only"),
                 D("Numbers and script pass the grounding check?", [A("Regenerate once; if it still fails use the fallback text 'I will check with the shop'")], rejoin=True),
                 A("Save the reply, update chat memory, log the AI usage"), E]

ACT["act_suggest"] = [S, A("Customer asks for a recommendation (for example a gift under 3000 taka)"),
                      A("LLM extracts needs: category, occasion, colour, size, budget words"),
                      A("Code parses the budget (maximum, range, around) from the text"),
                      A("Query this shop's products: stock above zero and price within the budget"),
                      D("Any product matches?", [A("Reply from facts: no matching product is in stock")], rejoin=True),
                      A("Rank the matches and keep at most 3"), A("Reply LLM writes a short text about them"),
                      A("Attach the product cards with photos"), E]

ACT["act_order"] = [S, A("Customer says which product they want"), A("Extraction step (LLM) returns product, size, colour, quantity, name, phone, address"),
                    A("Code matches the product in this shop and checks size, colour and stock"),
                    D("Phone matches 01[3-9] and 8 more digits?", [A("Ask the customer for a valid phone number"), E]),
                    D("All fields present?", [A("Keep the partial order in the chat and ask for the missing field"), E]),
                    A("Create the order with status draft; clear the pending order"), A("Reply with the order summary: the seller must confirm"), E]

ACT["act_manage_order"] = [S, A("Seller opens Orders and chooses the Draft tab"), A("Opens an order to review it"),
                           D("Needs a change?", [A("Edit product, size, colour, quantity or customer fields\n(checked against the shop's products)")], side="yes", main_label="no", rejoin=True),
                           D("Order is still a draft?", [A("Reject with 409: only drafts can be confirmed or cancelled"), E]),
                           D("Seller confirms?", [A("Set status cancelled and cancelled_at"), E], main_label="yes", side_label="no"),
                           A("Set status confirmed, confirmed_at and confirmed_by"),
                           A("Later: export confirmed orders to CSV for the courier"), E]

ACT["act_export"] = [S, A("Seller opens Orders and chooses an optional date range"), A("Request GET /orders/export"),
                     A("Select confirmed orders of this shop (Bangladesh day of confirmation)"),
                     A("Neutralise cells that start with =, +, - or @ (CSV formula protection)"), A("Return the CSV file as a download"), E]

ACT["act_handover"] = [S, A("A customer message is processed"), A("Understanding step and code rules look for a handover reason"),
                       D("One of the 7 reasons found?", [A("Continue with the normal AI reply"), E], side="no", main_label="yes", side_label="no"),
                       A("Save a handover event with the reason"), A("Flag the chat and pause the AI for this chat"),
                       A("Create a 'chat flagged' notification (Messenger chats only)"), A("Send a fixed safe reply to the customer"),
                       A("Seller sees the flag in the Inbox and the bell"), A("Seller replies, resolves the flag and may resume the AI"), E]

ACT["act_fb_connect"] = [S, A("Owner clicks Connect Facebook Page"), A("Backend creates a signed state (10 minutes, one use) and the Facebook login URL"),
                         A("Owner logs in at Facebook and accepts the permissions"), A("Facebook calls /facebook/callback with code and state"),
                         D("State valid and not used before?", [A("Reject: invalid or expired state"), E]),
                         A("Exchange the code for a long-lived user token; check the granted permissions"),
                         D("Required permissions granted?", [A("Show 'missing permission' error"), E]),
                         A("Read the owner's Pages; keep them encrypted in Redis for 10 minutes"), A("Owner picks one Page"),
                         D("Page already used by another shop?", [A("Reject the connection"), E], side="yes", main_label="no"),
                         A("Encrypt the Page token (Fernet), save it, subscribe the Page to 'messages'"), E]

ACT["act_webhook"] = [S, A("Facebook sends POST /webhooks/messenger"),
                      D("X-Hub-Signature-256 matches the raw body?", [A("Reject with 403"), E]),
                      A("For each messaging event: ignore echoes and unknown Pages"),
                      D("Message id (mid) already stored?", [A("Ignore the duplicate"), E], side="yes", main_label="no"),
                      A("Find or create the chat for this shop and customer"), A("Save the message and its received time; update the 24-hour window"),
                      A("Queue process_incoming_message in Celery and answer 200 quickly"),
                      A("Worker takes a lock for the chat"),
                      D("Shop suspended, AI paused, no Page, outside 24 hours or limit reached?", [A("Mark the message skipped with the reason"), E], side="yes", main_label="no"),
                      A("Reserve one reply from the monthly allowance; run the AI engine"),
                      D("Facebook accepted the reply?", [A("Mark failed or skipped; give the reserved reply back"), E]),
                      A("Set sent_at and mark the message replied"), E]

ACT["act_reply"] = [S, A("Seller opens a chat in the Inbox"), A("Seller writes a reply and presses Send"),
                    D("Chat is a Messenger chat and inside the 24-hour window?", [A("Reject with a clear message; nothing is sent"), E]),
                    A("Save the message as sender 'seller'"), A("Send it through the same Messenger sender (RESPONSE type, retries)"),
                    D("Facebook accepted?", [A("Show the send error"), E]),
                    A("Set sent_at; the reply appears in the chat"), E]

ACT["act_delete"] = [S, A("Owner opens Settings and the Danger zone"), A("Enters the exact shop name and the current password"),
                     D("Shop name matches and password is correct?", [A("Reject (422 or 403)"), E]),
                     A("Tell Facebook to stop sending events (best effort)"), A("Delete the product photo files and the shop's Redis keys"),
                     A("Delete the shop row: cascade removes users, products, chats, messages, orders and the rest"),
                     A("Add the current token to the deny list"), E]

ACT["act_insights"] = [S, A("Celery beat starts the task every Sunday at 20:00 UTC"), A("For each active shop, find the customer messages of the finished week (Monday to Sunday)"),
                       D("Any customer messages?", [A("Skip this shop"), E]),
                       A("Remove phone numbers and similar details from the text"), A("Map step: LLM summarises each batch; reduce step joins them"),
                       A("Save top questions and missing products in weekly_insights"), A("Log the AI usage as operation weekly_insights"),
                       A("Owner reads the summary on the Reports page"), E]

ACT["act_flow"] = [S, A("Seller registers, adds products and policy, tests the AI"), A("Seller connects the Facebook Page"),
                   A("Customer writes on Messenger; webhook stores the message"), A("Worker runs the AI engine and sends the reply"),
                   D("Handover needed?", [A("Chat is flagged, AI paused; seller replies in the Inbox"), E], side="yes", main_label="no"),
                   D("Customer gave a complete order?", [A("AI keeps asking for the missing details")], side="no", main_label="yes", rejoin=True),
                   A("Draft order is created"), A("Seller confirms or cancels the order"), A("Seller exports confirmed orders for the courier"), E]


# ------------------------------------------------------------------------------------------------ sequence diagrams
SEQ = {}
SEQ["sq_messenger"] = (["Customer", "Facebook", "Webhook\nroute", "Worker\n(Celery)", "AI engine", "PostgreSQL /\nRedis"], [
    (0, 1, "sends a message", "call"), (1, 2, "POST + X-Hub-Signature-256", "call"), (2, 2, "check signature, skip echo", "self"),
    (2, 5, "de-duplicate by mid, save message", "call"), (2, 3, "queue process_incoming_message", "async"), (2, 1, "200 OK", "return"),
    (3, 5, "lock chat, read shop, Page, plan", "call"), (3, 5, "reserve one reply", "call"), (3, 4, "reply_to_stored_message", "call"),
    (4, 5, "memory, products, vector search", "call"), (4, 3, "reply, intent, order result", "return"), (3, 5, "save AI message, usage log", "call"),
    (3, 1, "Send API (24-hour window)", "call"), (1, 0, "reply appears", "return"), (3, 5, "set sent_at", "call")])
SEQ["sq_retrieval"] = (["Conversation\nservice", "AI engine", "Tools", "PostgreSQL\n(pgvector)", "Embedding\nprovider", "LLM"], [
    (0, 1, "message + memory + shop id", "call"), (1, 5, "understanding (intent, entities)", "call"), (5, 1, "JSON answer", "return"),
    (1, 2, "vector_search(query)", "call"), (2, 4, "embed the query", "call"), (4, 2, "vector (1536)", "return"),
    (2, 3, "nearest chunks of this shop (cosine)", "call"), (3, 2, "chunks", "return"), (1, 2, "search_products / check_stock", "call"),
    (2, 3, "SQL on products of this shop", "call"), (3, 2, "rows", "return"), (1, 5, "reply from facts", "call"), (5, 1, "text", "return"),
    (1, 1, "grounding check", "self"), (1, 0, "reply + extras", "return")])
SEQ["sq_order"] = (["Customer", "Conversation\nservice", "AI engine", "LLM", "PostgreSQL", "Seller"], [
    (0, 1, "I want the red saree, 1 piece", "call"), (1, 2, "message + pending order", "call"), (2, 3, "extract_order", "call"), (3, 2, "fields (JSON)", "return"),
    (2, 4, "match product, check size, colour, stock", "call"), (2, 2, "validate phone", "self"), (2, 1, "ask for the missing field or phone", "return"),
    (1, 0, "question", "return"), (0, 1, "name, phone, address", "call"), (1, 2, "complete fields", "call"), (2, 1, "order_ready", "return"),
    (1, 4, "INSERT order (draft), clear pending", "call"), (1, 0, "order summary, waiting for seller", "return"), (5, 4, "review, edit, confirm", "call")])
SEQ["sq_seller_reply"] = (["Seller\n(browser)", "API\n/chats/id/reply", "Messenger\nSender", "Facebook\nSend API", "PostgreSQL"], [
    (0, 1, "POST reply text (JWT)", "call"), (1, 4, "load chat of this shop", "call"), (1, 1, "check Messenger chat and 24-hour window", "self"),
    (1, 4, "save message, sender = seller", "call"), (1, 2, "send_text", "call"), (2, 3, "POST /me/messages (RESPONSE)", "call"), (3, 2, "message id", "return"),
    (2, 1, "accepted", "return"), (1, 4, "set sent_at", "call"), (1, 0, "201 message", "return")])
SEQ["sq_fb_oauth"] = (["Owner\n(browser)", "Frontend", "Backend API", "Redis", "Facebook"], [
    (0, 1, "Connect Facebook Page", "call"), (1, 2, "GET /facebook/connect-url", "call"), (2, 2, "sign state (10 min, nonce)", "self"), (2, 1, "login URL", "return"),
    (1, 4, "redirect to Facebook login", "call"), (4, 2, "callback with code and state", "call"), (2, 3, "use the state nonce once", "call"),
    (2, 4, "exchange code, read permissions, list Pages", "call"), (4, 2, "user token, Pages", "return"), (2, 3, "keep Pages encrypted, 10 min", "call"),
    (0, 2, "choose a Page (POST pages/connect)", "call"), (2, 4, "subscribe Page to 'messages'", "call"), (2, 2, "encrypt Page token, save", "self"), (2, 0, "connected", "return")])
SEQ["sq_login"] = (["Browser", "Backend API", "Redis", "PostgreSQL"], [
    (0, 1, "POST /auth/login", "call"), (1, 2, "rate limit by IP and e-mail", "call"), (1, 3, "find user, check bcrypt hash, shop status", "call"),
    (1, 1, "create JWT (jti, role, shop_id)", "self"), (1, 0, "access token", "return"), (0, 1, "request with Bearer token", "call"),
    (1, 2, "is the jti on the deny list?", "call"), (1, 0, "data", "return"), (0, 1, "POST /auth/logout", "call"), (1, 2, "deny jti until expiry", "call")])
SEQ["sq_embedding"] = (["Owner\n(browser)", "API\n/products", "PostgreSQL", "Redis\n(queue)", "Worker", "Embedding\nprovider"], [
    (0, 1, "create or edit a product", "call"), (1, 2, "save product", "call"), (1, 3, "queue embed_product(id)", "async"), (1, 0, "product saved", "return"),
    (3, 4, "task", "async"), (4, 2, "read product", "call"), (4, 5, "embed the product text", "call"), (5, 4, "vector (1536)", "return"),
    (4, 2, "replace the product chunk", "call")])
SEQ["sq_testchat"] = (["Owner\n(browser)", "API\n/test-chat", "Conversation\nservice", "AI engine", "PostgreSQL"], [
    (0, 1, "POST message (JWT, owner)", "call"), (1, 2, "handle_customer_message", "call"), (2, 4, "save customer message (channel test)", "call"),
    (2, 3, "run the AI engine", "call"), (3, 2, "reply, extras, usage", "return"), (2, 4, "save AI message, order (is_test), usage log", "call"),
    (1, 0, "reply and cards", "return")])
SEQ["sq_insights"] = (["Celery beat", "Worker", "PostgreSQL", "AI engine", "LLM"], [
    (0, 1, "Sunday 20:00 UTC: weekly task", "async"), (1, 2, "active shops, messages of the finished week", "call"), (1, 1, "remove phone numbers", "self"),
    (1, 3, "insights (map-reduce)", "call"), (3, 4, "summarise each batch, then combine", "call"), (4, 3, "summaries", "return"),
    (3, 1, "top questions, missing products", "return"), (1, 2, "save weekly_insights, usage log", "call")])


def build_all():
    out = []
    for name, steps in ACT.items():
        out.append(activity(name, steps, gap=(4.8 if len(steps) > 11 else 6.5)).save())
    for name, (parts, msgs) in SEQ.items():
        out.append(sequence(name, parts, msgs).save())
    return out


if __name__ == "__main__":
    import sys

    only = sys.argv[1:]
    for name, steps in ACT.items():
        if not only or name in only:
            print(activity(name, steps, gap=(4.8 if len(steps) > 11 else 6.5)).save())
    for name, (parts, msgs) in SEQ.items():
        if not only or name in only:
            print(sequence(name, parts, msgs).save())
