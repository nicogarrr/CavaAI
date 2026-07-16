from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    app_name: str = "CavaAI Research Engine"
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    # Research OS is private by default. Tests that intentionally exercise the
    # public dependency graph must opt out explicitly with
    # RESEARCH_AUTH_REQUIRED=false.
    research_auth_required: bool = True
    research_auth_secret: str | None = Field(default=None, repr=False, min_length=32)
    research_auth_max_age_seconds: int = Field(default=300, ge=30, le=3600)
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = Field(default=120, ge=10, le=10000)
    rate_limit_expensive_requests_per_minute: int = Field(default=20, ge=1, le=1000)
    financial_document_retention_days: int = Field(default=2555, ge=1)
    market_price_max_age_days: int = Field(default=3, ge=0, le=30)

    database_url: str = "sqlite:///./portfolio_research_os.db"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    duckdb_path: Path = Path("./storage/analytics.duckdb")

    minio_endpoint: str = "localhost:9002"
    minio_access_key: str = "portfolio"
    minio_secret_key: str = "portfoliosecret"
    minio_bucket: str = "research"
    document_storage_backend: str = "minio"

    fmp_api_key: str | None = None
    finnhub_api_key: str | None = None
    ibkr_flex_token: str | None = None
    ibkr_flex_query_id: str | None = None
    sec_user_agent: str = "CavaAI/0.1 contact@example.com"
    fred_api_key: str | None = None
    quartr_api_key: str | None = None
    quartr_api_base_url: str = "https://api.quartr.com"

    openrouter_api_key: str | None = Field(default=None, repr=False)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_enabled: bool = True
    openrouter_model: str = "deepseek/deepseek-chat"
    openrouter_site_url: str | None = None
    openrouter_app_name: str = "CavaAI"

    openai_enabled: bool = True
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    anthropic_enabled: bool = True
    anthropic_api_key: str | None = Field(default=None, repr=False)
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_api_version: str = "2023-06-01"
    anthropic_model: str = "claude-3-5-sonnet-latest"

    gemini_enabled: bool = True
    gemini_api_key: str | None = Field(default=None, repr=False)
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-2.0-flash"

    llm_enabled: bool = True
    llm_provider: str = "auto"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_model_overrides: dict[str, str] = Field(default_factory=dict)
    llm_daily_cap_eur: float = Field(default=1.50, ge=0)
    llm_monthly_cap_eur: float = Field(default=40.00, ge=0)

    langfuse_enabled: bool = False
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        if self.app_env.lower() not in {"production", "prod"}:
            return self
        if not self.research_auth_secret:
            raise ValueError("RESEARCH_AUTH_SECRET is required in production")
        if self.document_storage_backend != "minio":
            raise ValueError("MinIO is required for production document originals")
        if self.minio_secret_key in {"portfoliosecret", "minioadmin", "change-me"}:
            raise ValueError("MINIO_SECRET_KEY must not use a development default in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
