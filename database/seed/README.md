# Demo seed data

`demo_shops.json` lists two fictional demo shops with owner accounts; `python -m app.cli seed` (run in `backend/`) creates them idempotently. Demo passwords come from `DEMO_PASSWORD` or are generated and printed once. Later prompts add more demo data here (loaded with `python -m app.cli seed` from `backend/`).

Only **fictional** demo shops and products belong here - never real customer data.

`plans.json` holds the Free/Basic/Pro plans. **Prices and message limits are placeholders - the proposal gives none; team to decide.** `python -m app.cli seed` upserts them by code.

`demo_products.json` holds fictional demo products (clothes, handicrafts, food, cosmetics, gadgets; one or more out of stock) per demo shop owner email. They have no photos; add some through the dashboard.
