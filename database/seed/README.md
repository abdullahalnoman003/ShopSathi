# Demo seed data

`demo_shops.json` lists two fictional demo shops with owner accounts; `python -m app.cli seed` (run in `backend/`) creates them idempotently. Demo passwords come from `DEMO_PASSWORD` or are generated and printed once. Later prompts add more demo data here (loaded with `python -m app.cli seed` from `backend/`).

Only **fictional** demo shops and products belong here - never real customer data.
