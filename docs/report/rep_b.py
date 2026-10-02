"""Sections 21 to 31: requirements, use cases, scenarios and behaviour diagrams."""
from rep_common import BR, FIG, FR, NFR, UC


def requirements(r):
    r.h1("21. Functional Requirements")
    r.p("The table lists the functional requirements of the implemented system. The numbering FR-01 to FR-37 belongs to this report. "
        "The column \"Proposal ref\" shows the matching number from the project proposal where we could verify it; a dash means that the proposal number is not recorded in the repository.")
    r.h2("21.1 Requirement list")
    rows = [(f[0], f[1], f[2], f[3]) for f in FR]
    r.table(["ID", "Requirement", "Proposal ref", "Use case"], rows, [1.4, 9.6, 2.0, 2.6], "Functional requirements", size=8.5)
    r.p("Every requirement is Implemented. The last column of the traceability matrix (section 21.3) shows how far each was tested.")
    r.h2("21.2 Requirements that depend on external services")
    r.bullets(["FR-20 to FR-22 and FR-25 (Facebook) were tested with a fake Graph API, a stub Send API and signed simulated events. They were not tested with a real Facebook Page.",
               "FR-13, FR-16, FR-17 and FR-30 (AI) were tested with the mock AI in the automated tests and with the real gpt-4o-mini model in the evaluation and load runs.",
               "FR-03 sends a reset link by SMTP. Without an SMTP host the link is written to the log in local mode only. A real mail server was not tested.",
               "FR-32 (paid plans) is a simulation. Not implemented in the current version: real payment."])


def nonfunctional(r):
    r.h1("22. Non-Functional Requirements")
    r.p("The NFR numbers NFR-01 to NFR-09 come from the project proposal. NFR-10 and NFR-11 were added during implementation. "
        "The last column states honestly how far each one is verified. Details are in section 60.")
    r.table(["ID", "Requirement", "Evidence", "Status"], NFR, [1.5, 4.4, 6.5, 3.2], "Non-functional requirements", size=8.5)


def business_rules(r):
    r.h1("23. Business Rules")
    r.p("Business rules are decisions about how the shop process must work. Each rule below is enforced in the code or the database.")
    r.table(["ID", "Rule"], BR, [1.6, 14.0], "Business rules", size=9)


def traceability(r):
    # section 21.4 sits at the end of section 21 in the text; it is placed here to keep section 22 and 23 together after the lists
    pass


def traceability_table(r):
    r.h2("21.3 Traceability matrix")
    r.p("The matrix connects each requirement to its use case, module, API, database tables and tests. Test names refer to files in `backend/tests`, `ai_engine/tests` and `evaluation`. "
        "The status shows the strongest evidence we have.")
    rows = [(f[0], f[1][:70] + ("..." if len(f[1]) > 70 else ""), f[3], f[4], f[5], f[6], f[7], f[8]) for f in FR]
    r.table(["Req. ID", "Requirement", "Use case", "Module", "API", "Database", "Test case", "Status"], rows, [1.2, 3.0, 1.2, 1.5, 2.6, 2.1, 2.1, 1.9], "Traceability matrix", size=6.5)


# ---------------------------------------------------------------------------------------------- use cases
def uc_diagrams(r):
    r.h1("24. Use Case Diagram")
    r.p("The system has four kinds of actors: the shop owner, the moderator, the customer and the platform admin. The AI engine, Facebook and the scheduler take part as supporting actors. "
        "We split the use cases into four diagrams so that each stays readable. There are 38 use cases in total (UC-01 to UC-38).")
    r.figure(FIG("uc_setup"), "Use case diagram: shop setup and administration by the owner", 15.0,
             "The owner prepares the shop: account, products, policy, Test Chat, Facebook Page, staff, plan and deletion. OpenAI or Gemini is used when products are embedded and when Test Chat runs. Facebook is used when the Page is connected.")
    r.figure(FIG("uc_daily"), "Use case diagram: daily work in the Inbox and Orders", 15.0,
             "Owner and moderator share the daily work. Reports and the weekly summary are for the owner only. Facebook receives the replies sent from the Inbox.")
    r.figure(FIG("uc_customer"), "Use case diagram: customer chat on Messenger", 15.0,
             "The customer writes to the Page. The AI engine answers, suggests, collects the order or hands over. Facebook delivers the messages.")
    r.figure(FIG("uc_admin"), "Use case diagram: platform administration", 13.0,
             "The platform admin manages shops and plans and watches cost and health. The weekly summary is started by the Celery beat scheduler.")
    r.table(["ID", "Use case", "Actor", "Requirement"], UC, [1.6, 7.0, 4.4, 2.6], "List of use cases", size=8.5)


UCD = [
    ("UC-01", "Sign up and create shop", "Shop owner (new visitor)", "The visitor has no account with this e-mail.",
     "1. The visitor opens the Sign up page.\n2. Enters shop name, owner name, e-mail and password, and chooses a plan.\n3. For a paid plan the visitor confirms the simulated payment.\n4. The system creates the shop (status active) and the owner account.\n5. The system returns an access token and opens the dashboard.",
     "Data invalid: the form shows the errors (HTTP 422).\nE-mail already used: HTTP 409 \"Email is already registered\".\nPaid plan without confirmation: rejected.", "A shop and an owner exist; a simulated payment is recorded for a paid plan.", "FR-01, FR-32"),
    ("UC-02", "Log in and log out", "Owner, moderator, platform admin", "The user has an account.",
     "1. The user enters e-mail and password.\n2. The system checks the rate limit, the password hash and the shop status.\n3. The system creates a token with a unique id and returns it.\n4. The user works. On log out the token id is put on a deny list in Redis.",
     "Too many attempts: HTTP 429.\nWrong e-mail or password: HTTP 401 with the same text for both.\nShop suspended: HTTP 403.", "A valid token exists, or the old token is revoked.", "FR-02"),
    ("UC-03", "Reset password", "Owner, moderator", "The user knows the e-mail address.",
     "1. The user asks for a reset link on the Forgot password page.\n2. The system always answers \"If that email is registered, a reset link has been sent\".\n3. For an active user, a hashed one-time token valid for 60 minutes is stored and the link is e-mailed.\n4. The user opens the link and enters a new password.\n5. The system saves the new hash and marks the token used.",
     "Unknown e-mail: same message, nothing sent.\nToken used, unknown or expired: HTTP 400.\nToo many requests: HTTP 429.", "Password changed; the token cannot be used again.", "FR-03"),
    ("UC-04", "Manage products", "Shop owner", "Logged in as owner.",
     "1. The owner opens Products and chooses Add product or Edit.\n2. Enters name, description, price, stock, sizes and colours.\n3. The system validates and saves the product for this shop.\n4. A background task creates the embedding of the product.",
     "Invalid data: validation errors.\nProduct of another shop: HTTP 404.\nQueue is down: the product is still saved (tested).", "The product is saved and will be searchable after the embedding task.", "FR-07, FR-11"),
    ("UC-06", "Import products from CSV or Excel", "Shop owner", "Logged in as owner; has a file.",
     "1. The owner downloads the template (optional) and uploads the file.\n2. The system reads up to 1000 rows (2 MB).\n3. Each valid row becomes a product through the same service as a manual product.\n4. The result lists created rows and failed rows with the reason.",
     "Wrong type, too large, too many rows or missing columns: the file is rejected with a clear message.\nInvalid rows: skipped and reported.", "Valid products exist; embeddings are queued.", "FR-09"),
    ("UC-09", "Connect a Facebook Page", "Shop owner", "Facebook app settings exist in the server configuration.",
     "1. The owner clicks Connect Facebook Page.\n2. The system returns a Facebook login URL with a signed single-use state.\n3. The owner logs in at Facebook and accepts the permissions.\n4. Facebook calls the callback; the system checks the state, exchanges the code and reads the Pages.\n5. The owner chooses a Page.\n6. The system subscribes the Page to messages, encrypts the Page token and saves it.",
     "Invalid, used or expired state: rejected, nothing stored.\nMissing permission or no Page: explained to the owner.\nPage used by another shop: rejected.\nFacebook refuses the subscription: nothing is connected.", "One Page is connected to the shop.", "FR-20"),
    ("UC-13", "View chat list and read chats", "Owner, moderator", "Logged in; Messenger chats exist.",
     "1. The user opens Inbox.\n2. The system lists chats, flagged ones first, then by latest activity.\n3. The user filters All or Flagged and opens a chat.\n4. The system shows all messages, the order drafts and product cards.",
     "Chat of another shop or a test chat: HTTP 404.", "None (read only).", "FR-23"),
    ("UC-14", "Reply to a customer", "Owner, moderator", "The AI is paused in this chat; a Page is connected.",
     "1. The user writes a reply and presses Send.\n2. The system checks that the chat is a Messenger chat, that the AI is paused and that the 24-hour window is open.\n3. The message is saved as sender seller and sent through the Send API.\n4. The time of sending is stored.",
     "AI not paused: rejected.\nWindow closed: rejected with a clear message.\nFacebook refuses: the reply is not stored.", "The customer has the reply.", "FR-25"),
    ("UC-18", "Confirm or cancel an order", "Owner, moderator", "A draft order exists.",
     "1. The user opens the order and checks the details.\n2. The user presses Confirm or Cancel.\n3. The system sets the status and the time. For confirm it also stores who confirmed.",
     "Order is not a draft: HTTP 409.\nOrder of another shop: HTTP 404.", "The order is confirmed or cancelled. Stock is not changed.", "FR-27"),
    ("UC-19", "Export confirmed orders", "Owner, moderator", "Confirmed orders exist.",
     "1. The user chooses an optional From and To date.\n2. The system selects confirmed orders of the shop for those Bangladesh days.\n3. It writes a CSV file with fixed columns and protects cells that start with =, +, - or @.\n4. The browser downloads the file.",
     "Invalid dates: validation error.\nNo orders: a file with only the header.", "A CSV file is downloaded.", "FR-28"),
    ("UC-23", "Ask about product, price or stock", "Customer", "The Page is connected, AI is active, window is open, limit not reached.",
     "1. The customer writes a question in Messenger.\n2. The system stores it and the worker runs the AI engine.\n3. The engine finds the product and reads price and stock from the database.\n4. The reply is written from these facts and checked.\n5. The reply is sent and counted.",
     "Product not found or fact missing: the AI says it will check with the shop and the chat is flagged (not_in_shop_data).", "The customer has an answer; usage is logged.", "FR-13, FR-14"),
    ("UC-25", "Ask for suggestions with a budget", "Customer", "As UC-23.",
     "1. The customer asks, for example, for a gift under 3000 taka.\n2. The engine extracts the needs and the budget.\n3. Code filters the shop's live products: in stock and inside the budget.\n4. The best three become product cards with photos.\n5. A short text is written and sent with the photos.",
     "No match: an honest reply without cards (tested).", "Suggestion reply sent.", "FR-16"),
    ("UC-26", "Give order details in chat", "Customer", "As UC-23.",
     "1. The customer says which product they want.\n2. The engine extracts product, size, colour, quantity, name, phone and address.\n3. Code checks the product, size, colour, stock and the phone number format.\n4. Missing or invalid fields are asked for again; partial data is kept in the chat for 24 hours.\n5. When all fields are valid a draft order is created.",
     "Out-of-stock or unknown product, bad size or too many pieces: no draft.\nInvalid phone: asked again.", "A draft order waits for the seller.", "FR-17"),
    ("UC-27", "Ask for a human / handover", "Customer, AI engine", "As UC-23.",
     "1. The customer complains, asks for a refund, uses abusive words, asks for a person, writes off-topic, or the AI is not confident.\n2. The engine returns a hand-over reason.\n3. The system saves a hand-over event, flags the chat, pauses the AI and creates a notification.\n4. A short safe reply is sent in the customer's style.",
     "The same chat stays quiet (no AI reply, no second notification) until the seller resumes it.", "The seller sees the flag in the Inbox and the bell.", "FR-18, FR-19"),
    ("UC-32", "Suspend or reactivate a shop", "Platform admin", "Logged in as platform admin.",
     "1. The admin searches the shop and opens it.\n2. The admin presses Suspend or Reactivate.\n3. The system changes the status and writes a row in the admin action log.",
     "Suspending twice is harmless and logged once.", "Suspended: users cannot log in or use old tokens, and customers get no AI reply.", "FR-33"),
    ("UC-12", "Delete shop", "Shop owner", "Logged in as owner.",
     "1. The owner opens Settings, Danger zone, Delete this shop.\n2. Enters the exact shop name and the password.\n3. The system tells Facebook to stop events, deletes photo files and Redis keys, and deletes the shop row; the database removes all shop data.\n4. The current token is revoked.",
     "Wrong name or password: nothing deleted.\nToo many tries: rate limited.\nFacebook or storage failure: the deletion still completes.", "No data of the shop remains; the other shops are untouched.", "FR-36"),
]


def uc_descriptions(r):
    r.h1("25. Use Case Descriptions")
    r.p("The tables below describe the main use cases in detail. The other use cases in Table \"List of use cases\" follow the same pattern and are explained by the activity diagrams in section 29.")
    for u in UCD:
        r.kv_table([("ID and name", f"{u[0]}  {u[1]}"), ("Actor", u[2]), ("Precondition", u[3]), ("Main flow", u[4]), ("Alternative flows", u[5]), ("Postcondition", u[6]), ("Requirement", u[7])],
                   f"Use case description {u[0]}: {u[1]}", widths=(3.3, 12.3), size=9)


def scenarios(r):
    r.h1("26. Scenario Writing")
    r.p("The scenarios below follow typical days of the system. Names and numbers are examples from the demo data and from the automated tests; they are not real customers.")
    sc = [
        ("26.1 Scenario A: a new owner starts", "Rina opens the Sign up page, enters her shop name and e-mail, chooses the Free plan and signs up. The dashboard opens. She adds seven products, uploads one photo, "
         "and fills the policy: delivery charge 60 taka inside Dhaka and 120 outside, with return rules. In Test Chat she writes \"Red Jamdani Saree ta nibo, 1ta. Naam Rina, phone 01711223344, Dhaka Mirpur 10\". "
         "The AI replies with a summary and an \"Order draft created\" card (see the screenshot in section 43). Nothing was sent to Facebook."),
        ("26.2 Scenario B: a customer asks about price and stock", "A customer writes \"Red saree ta ache? Dam koto?\" on Messenger. The webhook stores the message and the worker starts the AI engine. "
         "The engine detects Banglish, finds the product, reads the price and stock from the database, writes the reply in Banglish, checks that the numbers come from the facts, and the sender delivers it. "
         "The measured time from receiving to sending was about 6 seconds in the local load test with the real model."),
        ("26.3 Scenario C: suggestion with a budget", "A customer writes \"Eid-er jonno panjabi lagbe, 1500 takar moddhe\". The engine reads the budget in code, filters the live products (stock above zero and price within the budget), "
         "keeps at most three, and the reply is sent with the photos of those products. A product with zero stock is never shown."),
        ("26.4 Scenario D: order with a wrong phone number", "The customer gives the name, the address and the phone \"0171-1223\". The phone does not match the Bangladesh mobile format, so the draft is not created and the AI asks again. "
         "After the customer sends 01711223344 the draft order is created. The seller sees it under Orders, Draft."),
        ("26.5 Scenario E: complaint and handover", "A customer writes that the product was bad and asks for a refund. The engine returns the reason refund (or complaint). A hand-over event is saved, the chat is flagged, the AI is paused, "
         "and a notification appears in the bell. The customer gets a short polite reply that promises nothing. The seller opens the chat, writes a reply, marks the flag as handled and, if wanted, resumes the AI."),
        ("26.6 Scenario F: the 24-hour window", "A customer wrote two days ago and writes again after a long time. The first message is inside its own window and is answered. If the seller tries to reply to a chat whose last customer message is older than 24 hours, "
         "the system refuses with a clear message and sends nothing."),
        ("26.7 Scenario G: the plan limit", "A Free shop has 100 AI replies per month. The 100th reply is sent; for the 101st message the worker marks the message as skipped with the reason limit_reached. The message stays in the Inbox for the seller. "
         "The owner can change the plan on My plan, which uses a simulated payment."),
        ("26.8 Scenario H: the admin suspends a shop", "The admin finds a shop, presses Suspend, and the action is logged. The shop's users can no longer log in and old tokens stop working. Customers of that shop get no AI reply until the admin presses Reactivate."),
    ]
    for t, text in sc:
        r.h2(t)
        r.p(text)


def context_diagram(r):
    r.h1("27. Context Diagram")
    r.p("The context diagram shows ShopSathi as one system with the people and external services around it. All data flows pass the system boundary.")
    r.figure(FIG("context"), "Context diagram of ShopSathi", 14.5,
             "The owner and moderator use the dashboard. The customer talks to the shop through Facebook Messenger. The platform admin uses the admin pages. "
             "ShopSathi calls the Facebook Graph API and Send API, and it calls OpenAI or Gemini for language and embeddings. The AI provider is chosen by configuration.")


def flowchart(r):
    r.h1("28. System Flowchart")
    r.figure(FIG("act_flow"), "System flowchart: from set-up to the courier list", 11.5,
             "The flow shows the whole life of a sale: the seller prepares the shop and connects the Page, the customer writes, the worker answers, difficult chats are handed over, a complete order becomes a draft, and the seller confirms and exports it. "
             "Each step is explained in detail by an activity diagram in section 29.")


ACT_TEXT = [
    ("act_signup", "Activity diagram: registration, shop creation", "The sign-up form checks the data and the plan choice, rejects a used e-mail, then creates the shop and the owner in one step. A bcrypt hash is stored, never the password. The user is logged in at once."),
    ("act_login", "Activity diagram: login and logout", "Login is rate limited per IP and per e-mail. A wrong e-mail and a wrong password give the same answer. A suspended shop is refused. Logout puts the token id on a Redis deny list."),
    ("act_reset", "Activity diagram: password reset", "The answer is the same for known and unknown e-mails. Only a hash of the token is stored. The token is valid for 60 minutes and works once."),
    ("act_product", "Activity diagram: product creation, update and photos", "A saved product queues an embedding task. Photos are checked by their real file signature and size before they are stored."),
    ("act_import", "Activity diagram: CSV or Excel import", "The file is limited in size and rows. Every row passes the same validation as a manual product. Failed rows are reported by row number."),
    ("act_ai", "Activity diagram: AI message processing", "This is the main pipeline of the AI engine. It checks hand-over first, then handles orders and suggestions, and otherwise answers from facts. The reply is checked before it leaves the engine."),
    ("act_suggest", "Activity diagram: retrieval and suggestion", "The budget is read in code and the filter runs on live data, so a zero-stock product cannot appear even if the language model suggests it."),
    ("act_order", "Activity diagram: order draft", "Code, not the language model, validates the phone number, the product, the size, the colour and the stock. Missing fields are asked for one by one. The AI cannot confirm an order."),
    ("act_manage_order", "Activity diagram: order management", "Only draft orders can be edited, confirmed or cancelled. Changing the product takes the catalogue price. Confirming does not change stock."),
    ("act_export", "Activity diagram: CSV export", "The export covers confirmed orders in Bangladesh time. Cells that look like spreadsheet formulas are neutralised."),
    ("act_handover", "Activity diagram: human handover", "One of 7 reasons triggers the hand-over. The AI stops for that chat until the seller resumes it. A notification is created for Messenger chats."),
    ("act_fb_connect", "Activity diagram: Facebook Page connection", "The state value is signed and works once for 10 minutes. The list of Pages is kept encrypted in Redis for 10 minutes. The Page token is encrypted before it is stored."),
    ("act_webhook", "Activity diagram: Messenger webhook and reply delivery", "The webhook only verifies, stores and queues; it answers quickly. The worker applies the skip rules, reserves one reply from the monthly allowance, runs the engine and sends the reply. A reply is counted only when Facebook accepted it."),
    ("act_reply", "Activity diagram: seller reply from the Inbox", "A manual reply uses the same sender as the AI, so the same window and retry rules apply."),
    ("act_delete", "Activity diagram: shop deletion", "The deletion needs the password and the exact shop name. Cascading foreign keys remove all shop data in one delete."),
    ("act_insights", "Activity diagram: weekly insights", "Personal details are removed before the language model sees any text. The result is stored once per shop and week."),
]


def activity_diagrams(r):
    r.h1("29. Activity Diagrams")
    r.p("The activity diagrams show the real workflows. A diamond is a decision, a rounded box is an action, the black circle starts the flow and the circle with a dot ends it.")
    for i, (name, title, text) in enumerate(ACT_TEXT, 1):
        r.h2(f"29.{i} {title.replace('Activity diagram: ', '').capitalize()}")
        h = {"act_ai": 14.0, "act_webhook": 11.5, "act_fb_connect": 11.5}.get(name, 12.0)
        r.figure(FIG(name), title, h, text)


SEQ_TEXT = [
    ("sq_messenger", "Sequence diagram: customer message to AI reply", "The webhook route verifies the signature, stores the message and queues a task, then answers 200 to Facebook. The worker locks the chat, reserves a reply, runs the AI engine, saves the reply, sends it and sets sent_at."),
    ("sq_retrieval", "Sequence diagram: understanding, retrieval and reply", "The engine asks the language model to understand the message, calls tools for vector search and product data, and writes the reply from the facts. A grounding check runs before the reply leaves the engine."),
    ("sq_order", "Sequence diagram: order collection", "The engine extracts the fields; code checks them against the shop's products and the phone format. When all fields are valid, the conversation service writes the draft order."),
    ("sq_seller_reply", "Sequence diagram: seller reply", "The API checks the chat and the 24-hour window, saves the reply and sends it through the Messenger sender."),
    ("sq_fb_oauth", "Sequence diagram: Facebook Page connection", "The state is signed and used once. The Page list is kept in Redis while the owner chooses. The Page token is encrypted before it is saved."),
    ("sq_login", "Sequence diagram: login, protected request and logout", "Each protected request checks that the token id is not on the deny list. Logout adds the token id to the list until the token would expire."),
    ("sq_embedding", "Sequence diagram: product embedding", "Saving a product returns at once; the worker creates the embedding and replaces the product's chunks."),
    ("sq_testchat", "Sequence diagram: Test Chat", "Test Chat uses the same conversation service as Messenger, but the chat channel is test and nothing goes to Facebook."),
    ("sq_insights", "Sequence diagram: weekly insights", "Celery beat starts the task. Phone numbers are removed before the text goes to the model, which summarises in batches and then combines the summaries."),
]


def sequence_diagrams(r):
    r.h1("30. Sequence Diagrams")
    r.p("The sequence diagrams show the real interactions between parts of the system. Solid arrows are calls, dashed arrows are returns.")
    for i, (name, title, text) in enumerate(SEQ_TEXT, 1):
        r.h2(f"30.{i} {title.replace('Sequence diagram: ', '').capitalize()}")
        r.figure(FIG(name), title, 14.5, text)


def state_diagrams(r):
    r.h1("31. State Diagrams")
    r.p("These state diagrams show states that exist in the code and database: order status, chat control flags, the processing status of a customer message (stored in `messages.extras`), shop status, Facebook connection and order collection.")
    items = [
        ("st_order", "Order status", "The `orders.status` column allows draft, confirmed and cancelled (CHECK constraint). Only a draft can change."),
        ("st_chat", "Chat control: AI pause and flag", "A chat has two independent flags: `ai_paused` and `is_flagged`. A hand-over sets both. Resolve flag does not resume the AI, and resume does not clear the flag."),
        ("st_msg", "Customer message processing", "The status `ai_status` is stored in the message extras: pending, replied, skipped or failed. A skipped or failed reply is not counted against the plan."),
        ("st_shop", "Shop status", "The `shops.status` column allows active and suspended (CHECK constraint)."),
        ("st_fb", "Facebook connection", "The list of Pages is kept in Redis for 10 minutes. After a Page is chosen it is stored with an encrypted token."),
        ("st_collect", "Order collection in chat", "The partly collected order is kept in `chats.pending_order` and forgotten after the time to live (24 hours by default)."),
    ]
    for i, (n, t, text) in enumerate(items, 1):
        r.h2(f"31.{i} {t}")
        r.figure(FIG(n), f"State diagram: {t.lower()}", 14.0, text)
