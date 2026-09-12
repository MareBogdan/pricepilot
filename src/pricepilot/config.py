"""Central configuration. Everything comes from the environment / .env — never hardcoded."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- app ---
    app_env: str = "local"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- database ---
    database_url: str = "postgresql+psycopg://pricepilot:pricepilot@localhost:5432/pricepilot"

    # --- mock store ---
    mock_store_port: int = 8001
    mock_store_url: str = "http://localhost:8001"

    # --- scraping (CLAUDE.md §5) ---
    scraper_user_agent: str = "PricePilotBot/0.1 (+mailto:you@example.com)"
    scraper_min_delay_seconds: float = 2.0
    scraper_max_delay_seconds: float = 4.0
    scraper_default_limit: int = 5

    # --- llm (CLAUDE.md §5) ---
    llm_budget_usd: float = Field(default=5.0, ge=0.0)
    anthropic_api_key: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached so the .env file is parsed once per process."""
    return Settings()
