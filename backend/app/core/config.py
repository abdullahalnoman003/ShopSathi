from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    database_url: str = "postgresql+psycopg://shopsathi:shopsathi_local@localhost:5432/shopsathi"
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

    # Chat pipeline
    chat_memory_turns: int = 8  # last N turns of a chat kept in Redis as short-term memory
    chat_memory_ttl_seconds: int = 21600  # memory expires 6 hours after the last message
    rag_min_score: float = 0.2  # retrieved chunks below this similarity are ignored
    rag_min_product_score: float = 0.3  # semantic product matches below this similarity are ignored

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
