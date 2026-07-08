from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    app_name: str = "Portfolio Research OS"
    api_prefix: str = "/api"

    database_url: str = "sqlite:///./portfolio_research_os.db"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    duckdb_path: Path = Path("./storage/analytics.duckdb")

    minio_endpoint: str = "localhost:9002"
    minio_access_key: str = "portfolio"
    minio_secret_key: str = "portfoliosecret"
    minio_bucket: str = "research"

    fmp_api_key: str | None = None
    ibkr_flex_token: str | None = None
    ibkr_flex_query_id: str | None = None
    sec_user_agent: str = "PortfolioResearchOS/0.1 contact@example.com"
    fred_api_key: str | None = None
    quartr_api_key: str | None = None
    quartr_api_base_url: str = "https://api.quartr.com"

    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_daily_cap_eur: float = Field(default=1.50, ge=0)
    llm_monthly_cap_eur: float = Field(default=40.00, ge=0)

    langfuse_enabled: bool = False
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
