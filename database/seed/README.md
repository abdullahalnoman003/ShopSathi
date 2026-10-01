# Demo seed data

`demo_shops.json` lists two fictional demo shops with owner accounts; `python -m app.cli seed` (run in `backend/`) creates them idempotently. Demo passwords come from `DEMO_PASSWORD` or are generated and printed once. Later prompts add more demo data here (loaded with `python -m app.cli seed` from `backend/`).

Only **fictional** demo shops and products belong here - never real customer data.

`plans.json` holds the Free/Basic/Pro plans. **Prices and message limits are placeholders - the proposal gives none; team to decide.** `python -m app.cli seed` upserts them by code.

`demo_products.json` holds fictional demo products (clothes, handicrafts, food, cosmetics, gadgets; one or more out of stock) per demo shop owner email. They have no photos; add some through the dashboard.

`sample_products_import.csv` is a test file for the dashboard's CSV/Excel import: 11 fictional rows, of which 4 import and 7 fail (missing name, price 0, non-numeric price, 6 photos, negative stock, duplicate size, several problems). It is not loaded by `app.cli seed`.

`demo_policies.json` holds fictional shop policies (delivery areas with charges, delivery time, return rules, payment options) per demo shop owner email.

`demo_products.json` also contains "Eid Special Panjabi" (in stock, 1450) and "Premium Silk Panjabi" (sold out) so product suggestions can be tried with the proposal's example "eid er jonno 1500 er moddhe panjabi".

`demo_chats.json` holds fictional Messenger conversations per demo shop owner: three handed to the shop (complaint, refund, human_requested: AI paused, notification created, one already read) and one normal chat. They let the notification bell be tried before the Messenger integration exists.

`demo_history.json` holds about six weeks of fictional Messenger history per demo shop (32 chats in total with AI replies, 8 handovers and 16 orders in every status) so the Reports page and the weekly AI summary can be shown. Days are relative to the day you run the seed (Asia/Dhaka), names are made up and the phone numbers (`0170000xxxx`) look valid but are fake. Chats with a `hist-*` id are skipped if they already exist; handovers there are already handled (no notifications).
