# deploy/

Everything needed to put ShopSathi online. The full guide is `docs/DEPLOYMENT.md`.

| File | What it is |
|---|---|
| `docker-compose.prod.yml` | the VPS option: proxy (Caddy, automatic HTTPS), frontend, api, worker, beat, PostgreSQL + pgvector, Redis, as separate containers |
| `Caddyfile` | the proxy: HTTPS certificates, HTTP to HTTPS, security headers, routes to the api and the frontend |
| `.env.prod.example` | every setting of the stack; copy to `.env.prod` (git-ignored) and fill in |
| `render.yaml` | Render Blueprint for the backend (api, worker, beat, PostgreSQL, Redis); the frontend goes to Vercel |

The images are built from `backend/Dockerfile` (build from the repository root: `docker build -f backend/Dockerfile .`) and
`frontend/Dockerfile`. The local development setup (`database/docker-compose.yml`) is separate and unchanged.
