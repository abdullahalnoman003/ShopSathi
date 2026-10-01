# ShopSathi local demo database

PostgreSQL 16 (with the `pgvector` extension) and Redis 7, run with Docker Compose.

## Start

```bash
cd database
cp .env.example .env     # first time only; local, non-secret defaults
docker compose up -d
docker compose ps        # both services should become "healthy"
```

On the first start `init/01-extensions.sql` enables `vector` in the `shopsathi` database and creates the `shopsathi_test` database (also with `vector`) used by the automated tests.

## Stop

```bash
docker compose down      # keeps data
```

## Fully reset (deletes ALL demo data)

```bash
docker compose down -v
docker compose up -d
```

The init SQL runs again on the fresh volume. Then re-apply the schema (below).

## Schema migrations

Migrations use **Alembic** and live in `backend/alembic/` because they are tied to the SQLAlchemy models. This folder only provides the database server and seed data.

```bash
cd backend
alembic upgrade head
```

## Seed data

See `seed/README.md`.
