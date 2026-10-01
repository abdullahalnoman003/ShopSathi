from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    database_url: str = "postgresql+psycopg://shopsathi:shopsathi_local@localhost:5432/shopsathi"
    # Database connection pool, per process (the API and every Celery worker process). A worker with many threads needs
    # at least that many connections, plus a few for the API.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout_seconds: int = 30
    test_database_url: str = (
        "postgresql+psycopg://shopsathi:shopsathi_local@localhost:5432/shopsathi_test"
    )
    redis_url: str = "redis://localhost:6379/0"
    frontend_origin: str = "http://localhost:3000"
    # Public base URL of this backend; product photo URLs are built from it
    backend_public_url: str = "http://localhost:8000"

    # Uploaded media (git-ignored folder, served at /media)
    media_root: str = "media"
    max_upload_mb: int = 5

    # AI engine settings (the backend passes them to shopsathi_ai; it does not read os.environ itself)
    llm_provider: str = "mock"
    llm_model: str = "gpt-4o-mini"
    embedding_provider: str = "mock"  # openai | local | mock
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536  # must match the embedding_chunks.embedding column
    openai_api_key: str = ""
    gemini_api_key: str = ""
    # Cost per model in USD per 1M tokens, used for ai_usage_logs.estimated_cost. JSON in the env var.
    ai_cost_rates: dict[str, dict[str, float]] = {
        "text-embedding-3-small": {"input_per_1m": 0.02},
        "text-embedding-3-large": {"input_per_1m": 0.13},
        "gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60},
        "gemini-2.0-flash": {"input_per_1m": 0.10, "output_per_1m": 0.40},
    }

    # Facebook Page connection (Meta Messenger Platform). All from the environment, never in code.
    fb_app_id: str = ""
    fb_app_secret: str = ""
    fb_graph_api_version: str = "v21.0"  # check Meta's changelog: old versions are retired after ~2 years
    #: where Facebook sends the browser back after login: this backend's /api/v1/facebook/callback
    fb_oauth_redirect_uri: str = ""
    #: Fernet key used to encrypt Page tokens at rest (NFR-03)
    fb_token_encryption_key: str = ""
    #: where the browser is sent after Facebook login; falls back to FRONTEND_ORIGIN when empty
    frontend_url: str = ""
    #: the secret Meta sends back when it verifies the webhook URL (you choose it, in the Meta app and here)
    fb_verify_token: str = ""
    #: sending a reply: attempts for temporary errors, and the pause between them
    fb_send_max_attempts: int = 3
    fb_send_retry_delay_seconds: float = 0.5
    # Dev/test only: point at a local fake Facebook (backend/scripts/fake_facebook.py). Leave the defaults in production.
    # Reverse proxies (nginx ...) whose X-Forwarded-For / X-Forwarded-Proto headers are believed: comma separated IPs, or "*".
    # Behind HTTPS termination set this to the proxy address so rate limits see the real client and URLs stay https.
    trusted_proxies: str = "127.0.0.1"
    fb_graph_base_url: str = "https://graph.facebook.com"
    fb_dialog_base_url: str = "https://www.facebook.com"

    # Chat pipeline
    chat_memory_turns: int = 8  # last N turns of a chat kept in Redis as short-term memory
    chat_memory_ttl_seconds: int = 21600  # memory expires 6 hours after the last message
    rag_min_score: float = 0.2  # retrieved chunks below this similarity are ignored
    rag_min_product_score: float = 0.3
    # Understanding confidence below this flags the chat for a person (reason low_confidence)
    ai_confidence_threshold: float = 0.5
    report_max_range_days: int = 366  # the longest date range the Reports page may ask for
    order_pending_ttl_hours: int = 24  # an unfinished order collection is forgotten after this long  # semantic product matches below this similarity are ignored

    # Background jobs: run Celery tasks inline (used by automated tests only)
    celery_task_always_eager: bool = False

    # CSV/Excel product import limits
    max_import_mb: int = 2
    max_import_rows: int = 1000

    # Auth (no default for the secret: it must come from the environment)
    jwt_secret: str
    access_token_expire_minutes: int = 720
    password_min_length: int = 8
    password_reset_expire_minutes: int = 60

    # Rate limits (fixed window, Redis)
    login_rate_limit: int = 10
    login_rate_window_seconds: int = 300
    reset_rate_limit: int = 5
    reset_rate_window_seconds: int = 900

    # SMTP; when smtp_host is empty, emails are logged to the console instead
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "ShopSathi <no-reply@shopsathi.local>"
    smtp_use_tls: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
