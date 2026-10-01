from fastapi import FastAPI
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.log_masking import install_log_masking

settings = get_settings()
install_log_masking()  # no personal data or secrets in the logs

app = FastAPI(title="ShopSathi API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api/v1")
# Behind a reverse proxy that ends HTTPS: believe X-Forwarded-For / X-Forwarded-Proto, but only from TRUSTED_PROXIES.
# (Added last, so it runs first.) Without it every client looks like the proxy and the login rate limit is shared.
_proxies = [p.strip() for p in settings.trusted_proxies.split(",") if p.strip()]
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*" if "*" in _proxies else _proxies)

# Uploaded product photos are served at /media/... (reachable by URL, e.g. for Messenger).
_media_root = Path(settings.media_root)
_media_root.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=_media_root), name="media")
