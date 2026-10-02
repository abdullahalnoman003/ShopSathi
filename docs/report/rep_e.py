"""Sections 51 to 60: testing, results, performance, NFR evaluation."""
from rep_common import FIG, NFR

# (id, feature, input, expected, actual-evidence)  -- every row is backed by a test function that passes
CASES = [
    ("TC-01", "Sign-up", "POST /auth/signup with shop name, e-mail, password", "Shop and owner created; token returned", "Pass (test_signup_creates_shop_and_owner)"),
    ("TC-02", "Password hash", "Sign up, read users row", "Stored value is a bcrypt hash, not the password", "Pass (test_passwords_are_stored_as_bcrypt_hashes...)"),
    ("TC-03", "Login failure", "Wrong password and unknown e-mail", "Same 401 text for both", "Pass (test_login_does_not_reveal_whether_an_account_exists)"),
    ("TC-04", "Logout", "Log out, reuse the token", "Token rejected; other sessions still work", "Pass (test_logout_revokes_the_token...)"),
    ("TC-05", "Tampered token", "Changed role, removed signature, alg none, expired", "401 each time", "Pass (test_tampered_forged_and_expired_tokens_are_rejected)"),
    ("TC-06", "Password reset", "Request link, confirm with token", "Password changed; token cannot be reused", "Pass (test_password_reset_flow)"),
    ("TC-07", "Reset token expiry", "Use token after 60 minutes", "400 invalid or expired", "Pass (test_password_reset_token_expires)"),
    ("TC-08", "Login rate limit", "More wrong logins than the limit", "429 for that account and for that address", "Pass (test_login_rate_limit)"),
    ("TC-09", "Suspended shop", "Login and old token of a suspended shop", "403 / access lost", "Pass (test_suspended_shop_cannot_log_in_or_use_api)"),
    ("TC-10", "Tenant isolation", "Owner of shop B reads shop A product/chat/order", "404 everywhere; nothing changes", "Pass (test_cross_tenant_sweep_shop_b_cannot_reach_shop_a)"),
    ("TC-11", "Role matrix", "Every endpoint, four callers", "Each caller gets the documented answer", "Pass (test_every_endpoint_gives_every_role_the_right_answer)"),
    ("TC-12", "Moderator rights", "Moderator calls staff, plan change, products", "403", "Pass (test_moderator_forbidden_on_staff_and_plan_change)"),
    ("TC-13", "Product create", "POST /products valid data", "201 and product returned; embedding queued", "Pass (test_crud, test_change_hooks_are_called)"),
    ("TC-14", "Product validation", "Invalid price or stock value", "422 with errors", "Pass (test_validation_errors)"),
    ("TC-15", "Photo upload", "6 photos to one product", "Limit of 5 enforced", "Pass (test_photo_upload_serves_url_and_limits_to_five)"),
    ("TC-16", "Fake image", "Upload a text file named .png", "Rejected, nothing saved", "Pass (test_upload_rejects_non_images_all_or_nothing)"),
    ("TC-17", "Photo delete", "DELETE photo by index", "File removed from disk and product", "Pass (test_remove_photo_deletes_file)"),
    ("TC-18", "CSV import", "File with valid and invalid rows", "Valid rows created; invalid rows reported by row number", "Pass (test_mixed_rows_report_row_numbers_and_reasons)"),
    ("TC-19", "Import limits", "File over 2 MB or over 1000 rows", "Rejected with a clear error", "Pass (test_file_too_large_and_too_many_rows)"),
    ("TC-20", "Policy save", "PUT /shop/policy with two areas", "Saved; policy chunk embedded", "Pass (test_save_then_update, test_policy_save_embeds_policy_chunks...)"),
    ("TC-21", "Embeddings on edit", "Edit a product", "Old chunks replaced", "Pass (test_editing_a_product_replaces_its_chunks)"),
    ("TC-22", "Vector index", "Inspect the database index", "HNSW with cosine operator", "Pass (test_index_is_hnsw_cosine)"),
    ("TC-23", "Semantic search isolation", "Search in shop A", "Never a chunk of shop B", "Pass (test_retrieval_never_returns_another_shops_chunks)"),
    ("TC-24", "Price question", "\"Cotton Panjabi er dam koto?\" in Test Chat", "Reply with the price from the catalogue", "Pass (test_proposal_example_messages_get_grounded_replies)"),
    ("TC-25", "Unknown question", "A question with no shop data", "\"I will check with the shop\" style reply", "Pass (test_unknown_question_says_i_will_check_with_the_shop)"),
    ("TC-26", "Bangla reply", "Message in Bangla script", "Reply in Bangla script", "Pass (test_bangla_script_reply_is_in_bangla)"),
    ("TC-27", "AI disclosure", "Two messages in one chat", "Disclosure only in the first AI reply", "Pass (test_disclosure_is_sent_in_the_first_ai_reply_only)"),
    ("TC-28", "Memory", "Ten turns, then a question", "Only the last turns are given to the engine; rebuilt from DB if Redis is empty", "Pass (test_short_term_memory..., test_memory_is_rebuilt...)"),
    ("TC-29", "Suggestion with budget", "Gift request with a budget", "Matching in-stock products with price", "Pass (test_proposal_example_returns_matching_in_stock_products_with_price)"),
    ("TC-30", "Zero stock", "Only out-of-stock products match", "No card for them", "Pass (test_a_zero_stock_product_is_never_suggested)"),
    ("TC-31", "Max three", "Ten products match", "At most three cards", "Pass (test_at_most_three_cards)"),
    ("TC-32", "Order collection", "Product, then name, phone, address over turns", "Asks for what is missing, then creates one draft", "Pass (test_multi_turn_conversation_asks_for_what_is_missing...)"),
    ("TC-33", "AI never confirms", "Customer says \"confirm my order\"", "Status stays draft", "Pass (test_the_ai_never_confirms_an_order)"),
    ("TC-34", "Phone validation", "Invalid and valid numbers, Bangla digits, +88", "Invalid asked again; valid normalised to 01XXXXXXXXX", "Pass (validator tests, 37 tests)"),
    ("TC-35", "Out-of-stock order", "Order of a product with zero stock", "No draft", "Pass (test_out_of_stock_product_is_refused_from_the_catalogue)"),
    ("TC-36", "Handover reasons", "One message per reason (7)", "Chat flagged, AI paused, event saved", "Pass (test_each_reason_flags_the_test_chat..., 7 cases)"),
    ("TC-37", "Notification", "Flagged Messenger chat", "One notification per flag; none for a paused chat", "Pass (test_messenger_chats_create_a_notification_for_every_reason)"),
    ("TC-38", "Pause / resume", "Pause, customer writes, resume", "No AI reply while paused; reply after resume", "Pass (test_a_paused_chat_gets_no_ai_reply_and_a_resumed_one_does)"),
    ("TC-39", "Webhook handshake", "GET with right and wrong verify token", "Challenge echoed; 403 for wrong", "Pass (test_verification_handshake)"),
    ("TC-40", "Webhook signature", "Unsigned, wrong secret, changed body", "403 and nothing stored", "Pass (test_the_webhook_accepts_only_a_correct_signature)"),
    ("TC-41", "Duplicate mid", "Same event twice", "Processed once", "Pass (test_duplicate_mid_is_processed_once)"),
    ("TC-42", "Echo events", "Message sent by the Page itself", "Ignored", "Pass (test_echoes_receipts_and_the_pages_own_messages_are_ignored)"),
    ("TC-43", "Reply delivery", "Signed message through webhook, worker, stub Send API", "Reply sent to the right customer; sent_at set", "Pass (test_message_to_reply_through_the_send_api)"),
    ("TC-44", "24-hour window", "Message older than 24 hours / just inside", "Not answered / answered", "Pass (test_a_message_older_than_24_hours_is_not_answered, ..._just_inside_...)"),
    ("TC-45", "Monthly limit", "Last allowed message and the next", "Last answered; next skipped", "Pass (test_the_last_message_within_the_limit_is_answered...)"),
    ("TC-46", "Limit under load", "24 chats at once, limit 5", "Exactly 5 replies sent", "Pass (test_the_monthly_limit_holds_when_many_chats_are_answered_at_once)"),
    ("TC-47", "Send failure", "Facebook refuses the send", "Not counted; worker keeps running", "Pass (test_a_failed_send_is_not_counted_and_the_worker_survives)"),
    ("TC-48", "Retries", "Temporary Facebook errors", "Limited retries; success counted once", "Pass (test_temporary_errors_are_retried..., test_a_temporary_error_followed_by_success_counts_once)"),
    ("TC-49", "Non-text message", "Customer sends an image", "Placeholder stored; handed to seller", "Pass (test_non_text_messages_are_stored_as_a_placeholder_and_handed_over)"),
    ("TC-50", "Facebook connect", "Full OAuth flow with fake Facebook", "Page stored with encrypted token", "Pass (test_full_connect_flow_stores_the_page_token_encrypted)"),
    ("TC-51", "OAuth state", "Invalid, expired, reused, foreign state", "Rejected; nothing stored", "Pass (test_invalid_expired_reused_and_foreign_states_are_rejected)"),
    ("TC-52", "Page of other shop", "Connect a Page used by another shop", "Rejected", "Pass (test_a_page_connected_to_another_shop_is_rejected)"),
    ("TC-53", "Inbox order", "Flagged and normal chats", "Flagged first, then latest activity", "Pass (test_flagged_chats_come_first_then_latest_activity)"),
    ("TC-54", "Seller reply", "Reply while AI is paused", "Sent through Send API and stored", "Pass (test_reply_is_sent_through_the_send_api_and_stored)"),
    ("TC-55", "Reply rules", "Reply with AI active / outside window", "Rejected / rejected", "Pass (test_reply_is_rejected_while_the_ai_is_not_paused, ..._outside_the_24_hour_window)"),
    ("TC-56", "Order edit", "Change product of a draft", "Catalogue price taken; size and colour re-checked", "Pass (test_changing_the_product_takes_the_catalogue_price...)"),
    ("TC-57", "Order transitions", "Confirm and cancel; confirm a cancelled order", "Allowed for drafts; 409 otherwise", "Pass (test_confirm_and_cancel_transitions)"),
    ("TC-58", "CSV export", "Export with a date range", "Fixed columns, confirmed only, Dhaka days", "Pass (test_export_has_exact_columns..., test_export_range_uses_dhaka_days...)"),
    ("TC-59", "CSV formula", "Customer name starting with =", "Cell neutralised", "Pass (test_export_neutralises_spreadsheet_formulas)"),
    ("TC-60", "Report", "Range with messages, chats, orders", "Counts at the boundaries; test data excluded", "Pass (test_every_metric_at_the_range_boundaries, test_test_chat_data_is_excluded_everywhere)"),
    ("TC-61", "Weekly insights", "Seeded chats, run the job", "Summary stored; phone numbers never reach the model", "Pass (test_generation_from_seeded_chats..., test_customer_names_and_phone_numbers_never_reach_the_model)"),
    ("TC-62", "Plan change", "Change to a paid plan without confirmation", "Rejected; with confirmation a simulated payment row", "Pass (test_paid_plan_without_confirmation_is_rejected)"),
    ("TC-63", "Admin suspend", "Suspend a shop", "Users blocked; customers get no AI reply; logged", "Pass (test_suspend_blocks_the_shops_users..., test_a_suspended_shops_messenger_customers_get_no_ai_reply...)"),
    ("TC-64", "Shop deletion", "Delete with right password and name", "All rows, files and keys removed; other shop intact", "Pass (test_deleting_a_shop_removes_all_its_rows_files_and_keys...)"),
    ("TC-65", "Deletion guard", "Wrong password or wrong name", "Nothing deleted", "Pass (test_wrong_password_or_wrong_name_deletes_nothing)"),
    ("TC-66", "Secrets in logs", "Login, connect, webhook, full chat", "No token, password or customer text in logs", "Pass (test_no_secret_is_written_to_the_logs...)"),
    ("TC-67", "Secrets in repository", "Scan files that would be committed", "No keys, no real .env", "Pass (test_the_repository_contains_no_api_keys_or_private_keys)"),
    ("TC-68", "Health", "Stop the database or Redis", "503 degraded", "Pass (test_health_answers_503_when_a_dependency_is_down)"),
]


def strategy(r):
    r.h1("51. Testing Strategy")
    r.p("The project is tested at four levels: unit tests for pure logic, integration tests with a real PostgreSQL and Redis, API tests through the FastAPI test client, and manual or scripted runs for the whole chain. "
        "The AI is tested with the mock model for the rules and with the real model for quality and speed. All automated suites were run again on 2 October 2026 for this report.")
    r.table(["Level", "What it covers", "Tool", "Where"],
            [("Unit", "Validators, budget parsing, handover rules, chunking, metrics, language, providers", "pytest", "ai_engine/tests, evaluation/tests"),
             ("Integration", "Services with the real database and Redis: embeddings, usage limits, ingest and processor, shop deletion", "pytest with PostgreSQL 16 + pgvector and Redis", "backend/tests"),
             ("API", "Every route, permissions of four callers, validation, tenant sweep", "pytest + FastAPI TestClient", "backend/tests, tests/security"),
             ("AI quality", "Intent, price and stock, order fields, zero-stock rule, phone re-ask, flags", "evaluation harness (mock and real model)", "evaluation/"),
             ("End to end (scripted)", "Sign-up to Test Chat in the browser; signed Messenger events through webhook, worker and a stub Send API", "Browser script, simulate_messenger_event.py, fake Facebook", "backend/scripts"),
             ("UI / responsive", "All listed pages at 375 px and 1366 px", "Browser check", "docs/TEST_REPORT.md section 10"),
             ("Performance", "50 chats on 20 shops; real model and mock", "Load test tool", "backend/scripts/loadtest"),
             ("Security", "47 security tests and a secret scan", "pytest", "backend/tests/security")],
            [2.5, 6.0, 3.8, 3.3], "Test levels", size=8.5)
    r.h2("51.1 Test environment")
    r.p("One developer computer: Intel Core i7-12700K, 15.8 GB RAM, Windows 11, Python 3.14, PostgreSQL 16 with pgvector and Redis 7 in Docker. Facebook was never contacted. "
        "The tests that talk to Facebook use a fake Graph API (`scripts/fake_facebook.py`), a stub Send API, or direct calls with signed test events.")
    r.h2("51.2 Three kinds of AI and Facebook testing")
    r.table(["Kind", "Used for", "What it proves", "What it does not prove"],
            [("Mock / simulated", "All automated backend and AI engine tests, most load tests, the production stack run", "The rules, the code paths and the data flow work", "Answer quality; real Facebook behaviour"),
             ("Real OpenAI model", "Evaluation on 32 sample cases, the NFR-01 load runs, the screenshots of Test Chat, the weekly insights on demo data", "The pipeline works with the real model; typical speed and cost", "Final accuracy (the 200-message set does not exist); behaviour on a bad provider day"),
             ("Real Facebook", "Not used at any point", "-", "Everything that depends on the real Messenger platform: delivery, rate limits, permissions, App Review")],
            [3.0, 4.6, 4.0, 4.0], "Kinds of testing and their limits", size=8.5)


def unit(r):
    r.h1("52. Unit Testing")
    r.p("Unit tests run without a database. The AI engine package has its own test suite that runs in about half a second.")
    r.table(["File (ai_engine/tests)", "Tests", "Covers"],
            [("test_conversation.py", "52", "Engine flow with the mock model: replies, language, fallback, grounding check"), ("test_handover.py", "45", "Seven reasons, priority, keywords, threshold"),
             ("test_orders.py", "42", "Extraction, field checks, phone, stock, partial orders"), ("test_validators.py", "37", "Bangladesh phone numbers, digits, prefixes"),
             ("test_suggestions.py", "31", "Needs, budget, filter, maximum of three"), ("test_insights.py", "28", "Weekly insight map and reduce, redaction"),
             ("test_embeddings_and_retrieval.py", "15", "Chunking, retrieval, scores"), ("test_factory.py", "1", "Provider selection"), ("Total", "251", "All passed (0.55 s)")],
            [5.0, 1.6, 9.0], "Unit tests of the AI engine", size=9)
    r.p("The evaluation package has 82 more tests (metric functions, case-file checks, the in-memory gateway, an end-to-end mock run and the command line). All passed (2.2 s).")


def integration(r):
    r.h1("53. Integration Testing")
    r.p("The backend tests use a real PostgreSQL database with pgvector and a real Redis. They check the services together with the database. Important groups:")
    r.table(["Group", "File", "Tests", "Examples"],
            [("Messenger ingest and delivery", "test_messenger.py", "44", "Message to reply through the stub Send API, duplicate mid, window, limit, retries, order of messages"),
             ("Embeddings", "test_embeddings.py", "19", "Create, edit, delete, re-embed, stale result dropped, usage logged"),
             ("Facebook connection", "test_facebook.py", "21", "Full flow, bad states, permissions, disconnect"),
             ("Shop deletion and privacy", "test_privacy.py", "18", "Everything removed, cross-tenant sweep, log masking"),
             ("Limits under load", "security/test_limits_under_load.py", "6", "24 chats at once, window, suspension while waiting"),
             ("Weekly insights", "test_insights.py", "15", "Job, redaction, Celery task and beat entry")],
            [4.0, 4.6, 1.2, 5.8], "Integration test groups", size=8.5)


def api_tests(r):
    r.h1("54. API Testing")
    r.p("Every route has tests for success, validation, permissions and tenant isolation. The generated role matrix calls all endpoints as anonymous, owner, moderator and platform admin and compares with the documented access table.")
    rows = [("test_auth.py", 13), ("test_plans.py", 14), ("test_staff.py", 7), ("test_products.py", 22), ("test_product_import.py", 17), ("test_policy.py", 19), ("test_test_chat.py", 15),
            ("test_handover_api.py", 25), ("test_inbox.py", 19), ("test_orders_api.py", 13), ("test_orders_dashboard.py", 19), ("test_reports.py", 10), ("test_admin.py", 15),
            ("test_suggestions_api.py", 10), ("test_tenancy.py", 2), ("test_health.py", 5), ("test_loadtest_tools.py", 7)]
    r.table(["File (backend/tests)", "Tests"], rows, [8.0, 2.0], "API test files and test counts", size=9, align=["l", "r"])
    r.p("Sample requests and responses are in section 74.")


def e2e(r):
    r.h1("55. E2E Testing")
    r.p("End-to-end tests here are scripted runs of the real application, not an automated browser test suite. Frontend component or browser tests (for example Playwright or Cypress files in the repository): Not implemented in the current version.")
    r.table(["Run", "What happened", "Result", "Kind"],
            [("NFR-05 walk-through", "A script drove the production build of the dashboard: sign-up, five products, Test Chat question \"Cotton Panjabi er dam koto?\"", "58.5 s machine time in total; the reply came after 6.2 s with the real model", "Real model, local"),
             ("Messenger simulation", "simulate_messenger_event.py sends signed events to the webhook; the Celery worker answers; a stub Send API receives the reply", "Reply reached the stub for the right customer; also run inside the production compose network", "Simulated Facebook"),
             ("Fake Facebook connection", "scripts/fake_facebook.py stands in for the Graph API and login dialog", "Connect, list Pages, subscribe, disconnect worked in tests", "Simulated Facebook"),
             ("Screenshots for this report", "The running app was opened in Edge as owner, moderator and platform admin; a Test Chat conversation created an order draft", "The screens listed in section 76 were captured", "Real model, local"),
             ("Production compose", "Images built; seven containers healthy; migrations ran by themselves; HTTPS with a local certificate", "Passed (see section 61)", "Local only")],
            [3.0, 6.2, 4.2, 2.2], "End-to-end runs", size=8.5)


def ai_testing(r):
    r.h1("56. AI Testing")
    r.p("AI quality is measured by the evaluation harness in `evaluation/`. It runs the real `ConversationEngine` on labelled cases against an invented shop. "
        "The harness reports each metric overall and for Bangla, English and Banglish. The proposal's 200-message labelled test set does not exist, so the run below used the 32 sample cases that test the harness. "
        "The report itself says that these percentages are not results for the product.")
    r.h2("56.1 Real-model run on the 32 sample cases")
    r.p("Run on 2 October 2026 with gpt-4o-mini and OpenAI embeddings: 121 seconds in the engine, 63,108 input and 5,408 output tokens. Cases: Bangla 6, English 15, Banglish 11.")
    r.table(["Metric", "Target", "Result", "Status"],
            [("Intent accuracy (AI-R01)", ">= 85%", "100% (16 of 16)", "Pass on a small sample"),
             ("Prices and stock match the catalogue (AI-R03)", ">= 95%", "93.8% (15 of 16)", "Below target on a small sample"),
             ("Order fields correct (AI-R07)", ">= 90%", "100% (24 of 24)", "Pass on a small sample"),
             ("Zero-stock products suggested (AI-R06)", "0 violations", "0 of 3 suggestions", "Pass on a small sample"),
             ("Invalid phone asked again (AI-R08)", "100%", "100% (2 of 2)", "Pass on a very small sample"),
             ("Flag precision and recall", "reported", "6 of 6 and 6 of 6", "-"),
             ("Correct flag reason", "reported", "83.3% (5 of 6)", "-"),
             ("Language recognised", "reported", "100% (32 of 32)", "-")],
            [6.0, 2.2, 3.8, 3.6], "Evaluation of the real model on 32 sample cases", size=8.5)
    r.h2("56.2 The two failures")
    r.bullets(["`s-int-bl-delivery` (Banglish): the customer asked \"Inside Dhaka e delivery charge koto?\". The reply gave a greeting and said it would check with the shop; it did not state the charge of 60 taka. This is the one price and stock miss.",
               "`s-hov-en-notindata` (English): \"Do you sell laptops?\" was flagged as `off_topic` while the label was `not_in_shop_data`. The chat was handed over correctly, but the reason differs."])
    r.p("With the mock model the harness runs only to prove that it works; the mock result is not a quality result. Both reports are in `evaluation/reports/` (git-ignored).")
    r.h2("56.3 Coverage of the proposal's AI requirements")
    r.table(["ID", "Requirement (short)", "Status in the implementation"],
            [("AI-R01", "Intent accuracy >= 85%", "Implemented. 100% (16 of 16) on the samples; final accuracy not measured."),
             ("AI-R02", "Bangla, English, Banglish; reply in the same style", "Implemented and tested; style recognised in 32 of 32 sample cases; the reply script is checked in code."),
             ("AI-R03", "Prices and stock match the catalogue, >= 95%", "Implemented (live data, grounding check). 93.8% (15 of 16) on the samples, below 95%; final not measured."),
             ("AI-R04", "\"I'll check with the shop\" and flag instead of guessing", "Implemented and tested."),
             ("AI-R05", "Suggest 1 to 3 in-stock products", "Implemented and tested."),
             ("AI-R06", "Never suggest zero stock", "Implemented in code (filter on live data); 0 violations in 3 sample suggestions; tests."),
             ("AI-R07", "Order fields >= 90% correct", "Implemented. 100% (24 of 24) on the samples; final not measured."),
             ("AI-R08", "Check the phone number, ask again", "Implemented and tested (37 validator tests; 2 of 2 on the samples)."),
             ("AI-R09", "Ask for missing order fields", "Implemented and tested."),
             ("AI-R10", "Flag and notify on complaint, refund, abuse, low confidence", "Implemented and tested; 6 of 6 flagged chats correct on the samples, 5 of 6 reasons right."),
             ("AI-R11", "No order confirmation, price change or discount by the AI", "The AI cannot confirm an order (tested). The code has no function that changes a price; numbers in replies must come from the facts."),
             ("AI-R12", "Weekly summary of top 5 questions and missing products", "Implemented and tested; run on demo data with the real model."),
             ("AI-R13", "Embeddings updated within 1 minute", "Implemented as a background task queued at once. The elapsed time was not measured by a test.")],
            [1.6, 5.6, 8.4], "Proposal AI requirements and their status", size=8.5)
    r.h2("56.4 Other AI tests")
    r.bullets(["The backend conversation tests check the rules with the mock model: grounded replies, Bangla script replies, fallback when the model is down, usage logging per shop.",
               "The load tests used the real model with varied Banglish, English and Bangla questions about price, stock, delivery, return policy and order wishes.",
               "Not done: a Gemini run, a local-embeddings run, and a test with real shop owners' messages."])


def ui_testing(r):
    r.h1("57. UI/Responsive Testing")
    r.p("All pages were opened at 375 px and at 1366 px width (each inside a frame of that width), logged in as the demo owner or the platform admin with demo data. "
        "The check was: no sideways scrolling of the page and no element sticking out of the screen, except inside a deliberately scrollable area. The check was first tried on a page known to be too wide.")
    r.table(["Area", "Pages", "375 px", "1366 px"],
            [("Public", "/, /login, /signup, /forgot-password, /reset-password", "Pass", "Pass"),
             ("Seller", "/dashboard, /products, /products/new, /products/[id], /policy, /test-chat, /facebook, /plan, /staff, /settings, /inbox, /inbox/[id], /orders, /orders/[id], /reports", "Pass", "Pass"),
             ("Admin", "/admin, /admin/shops/[id], /admin/plans, /admin/ai-usage, /admin/health", "Pass", "Pass")],
            [2.0, 9.4, 2.1, 2.1], "Page-width checks (docs/TEST_REPORT.md section 10)", size=8.5)
    r.p("The test report records 70 of 70 checks passed and found no layout bug, so no layout was changed. "
        "**Limits:** touch target size, text legibility and a real phone browser were not tested; the narrow width was emulated in a desktop browser. `npm run lint` and `npm run build` are clean.")
    r.p("During the screenshots for this report we saw one visual problem: on a wide screen the notification list opens to the left of the bell and its left edge is about 20 pixels outside the page. On a phone it fits. This was not changed.")


def results(r):
    r.h1("58. Test Results")
    r.table(["Suite", "Tests", "Result", "Date"],
            [("backend (pytest, includes 47 security tests)", "396", "396 passed (5 min 9 s)", "2 Oct 2026"), ("ai_engine (pytest)", "251", "251 passed (0.55 s)", "2 Oct 2026"),
             ("evaluation (pytest)", "82", "82 passed (2.2 s)", "2 Oct 2026"), ("frontend lint and build", "-", "Clean (recorded in docs/TEST_REPORT.md)", "2 Oct 2026"),
             ("Total automated tests", "729", "729 passed, 0 failed", "")], [7.0, 1.6, 4.8, 2.2], "Automated test results", size=9)
    r.h2("58.1 Test case tables")
    r.p("Each row below is one test case that is backed by an automated test. \"Actual\" gives the result and the name of the test. A row is Pass only because the test passes on the final code.")
    for i in range(0, len(CASES), 23):
        chunk = CASES[i:i + 23]
        r.table(["Test ID", "Feature", "Input", "Expected", "Actual", "Status"], [(c[0], c[1], c[2], c[3], c[4], "Pass") for c in chunk],
                [1.2, 2.2, 3.6, 3.5, 4.2, 0.9], f"Test cases {chunk[0][0]} to {chunk[-1][0]}", size=7)
    r.h2("58.2 Defects found by testing")
    r.p("The load and security work found these defects, all fixed and kept as tests: the monthly limit could be passed under concurrency (24 replies sent for a limit of 5), a single-message worker was too slow for 50 chats (p90 42.8 s), "
        "the first burst after a worker start was slow (p90 10.0 s), Celery results piled up in Redis, rate limits saw the proxy instead of the client, and one of our own tests checked nothing. Details are in `docs/TEST_REPORT.md` section 6.")


def performance(r):
    r.h1("59. Performance Evaluation")
    r.h2("59.1 Environment and method")
    r.p("One Windows computer (i7-12700K, 15.8 GB). The load generator, API, worker, PostgreSQL and Redis all ran on it. Facebook was replaced by a stub Send API that answers in 150 ms. "
        "20 test shops (Pro plan, three products each, a policy, a fake connected Page) and 50 chats were created. Each chat sent its messages through the real webhook with a valid signature, one every few seconds, and all chats started within half a second. "
        "Latency is `sent_at - received_at` from the database, the same figure the product records. The real-model runs used 2 messages per chat (100 messages), the mock runs 3 (150 messages).")
    r.h2("59.2 Results")
    r.figure(FIG("perf_real"), "90th percentile reply time with the real model", 14.0,
             "With a worker of 50 threads, p90 was 5.77 s from a fresh start and 5.92 s on the second run, against the 8 s target. The two longer bars are runs before the fixes (16 threads: 14.7 s; no worker warm-up: 10.0 s).")
    r.figure(FIG("perf_mock"), "90th percentile reply time with the offline mock model", 14.0,
             "The mock answers in about 0.1 s, so these runs show the cost of the pipeline itself. A worker that handles one message at a time failed (42.8 s). 50 threads passed with 50 chats; with 100 chats at once p90 was 8.5 s.")
    r.table(["Run (final code)", "p50 / p90 / p99 (s)", "Target", "Result"],
            [("Real model, 50 chats, 50 threads, cold worker", "5.06 / 5.77 / 6.73", "p90 <= 8 s", "Within the target (local, stub Facebook)"),
             ("Real model, same worker, second run", "5.24 / 5.92 / 6.97", "p90 <= 8 s", "Within the target"),
             ("Real model, one idle chat", "3.3 / 4.0", "-", "Baseline"),
             ("Mock, 16 threads, 50 chats", "1.2 / 2.0 / 2.5", "p90 <= 8 s", "Within the target"),
             ("Mock, 50 threads, 50 chats", "1.9 / 2.8 / 3.1", "p90 <= 8 s", "Within the target"),
             ("Mock, 50 threads, 100 chats", "5.6 / 8.5 / 8.7", "p90 <= 8 s", "Just over: limit of one worker process"),
             ("Mock, one message at a time", "24.1 / 42.8 / 47.7", "p90 <= 8 s", "Failed (all 150 handled after 58 s)")],
            [6.0, 3.4, 2.0, 4.2], "Load test results", size=8.5)
    r.h2("59.3 Other measurements")
    r.bullets(["A reply costs about 3 s of AI time (2 to 4 model calls). The rest of the p50 is the burst: 50 messages in one second, then 0.15 s to send.",
               "The webhook answered with p50 89 to 283 ms and p90 344 to 651 ms in the real-model runs.", "The setup of 20 shops plus the two real runs used about 530 model calls, about 5 US cents.",
               "NFR-05: the scripted sign-up with five products and one Test Chat question took 58.5 s of machine time."])
    r.h2("59.4 What is verified and what is not")
    r.bullets(["Verified locally: NFR-01 and NFR-07 on one machine with a stub Facebook.", "Not verified: real Facebook latency and rate limits, a second API process, several worker processes, long runs of hours, and any public server.",
               "The result depends on the provider's speed on the day (about 1 to 1.5 s per call here)."])


def nfr_eval(r):
    r.h1("60. NFR Evaluation")
    rows = [(n[0], n[1], n[2], n[3]) for n in NFR]
    r.table(["ID", "Requirement", "Evidence", "Verdict"], rows, [1.5, 4.0, 7.0, 3.1], "Evaluation of the non-functional requirements", size=8.5)
    r.p("Only NFR-04, NFR-08, NFR-09 and NFR-10 are fully covered by automated tests. NFR-01, NFR-06, NFR-07 and NFR-11 are verified in a local setup. NFR-02 (99% availability) cannot be judged without a running public service and is not claimed.")
