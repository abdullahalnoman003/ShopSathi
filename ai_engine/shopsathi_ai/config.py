from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class AISettings(BaseSettings):
    """AI engine settings, read from environment variables."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    llm_provider: Literal["openai", "gemini", "mock"] = "mock"
    llm_model: str = "gpt-4o-mini"
    embedding_provider: Literal["openai", "local", "mock"] = "mock"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    openai_api_key: str = ""
    gemini_api_key: str = ""


def get_ai_settings() -> AISettings:
    return AISettings()
