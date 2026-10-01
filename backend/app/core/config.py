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


@lru_cache
def get_settings() -> Settings:
    return Settings()
