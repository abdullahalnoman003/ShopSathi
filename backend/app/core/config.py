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
