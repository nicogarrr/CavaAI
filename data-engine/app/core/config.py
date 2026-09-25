from functools import lru_cache
from pathlib import Path
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Credenciales de desarrollo conocidas: jamas validas en produccion.
_WEAK_CREDENTIAL_PAIRS = {
    "postgres:postgres",
    "postgres:password",
    "postgres:secret",
    "postgres:example",
    "postgres:changeme",
    "postgres:change-me",
    "mongo:mongo",
    "mongo:password",
    "root:root",
    "root:password",
    "root:example",
    "admin:admin",
    "user:password",
    "cavaai:cavaai",
    "cavaai:example",
}
_WEAK_PASSWORDS = {
    "password",
    "secret",
    "example",
    "pass",
    "test",
    "root",
    "admin",
    "changeme",
    "change-me",
    "123456",
}
_WEAK_MINIO_SECRET_KEYS = {
    "portfoliosecret",
    "portfolio",
    "minioadmin",
    "minio-secret",
    "minioadmin123",
    "change-me",
    "secret",
}
_WEAK_MINIO_ACCESS_KEYS = {"minioadmin", "minio", "admin", "change-me", "portfolio"}


def _url_credentials(url: str) -> tuple[str | None, str | None]:
    try:
        parts = urlsplit(url)
    except ValueError:
        return None, None
    if "@" not in parts.netloc:
        return None, None
    userinfo = parts.netloc.rsplit("@", 1)[0]
    user, sep, password = userinfo.partition(":")
    return (user or None, password if sep else None)


def _assert_strong_credentials(url: str, *, label: str) -> None:
    user, password = _url_credentials(url)
    if not user or not password:
        raise ValueError(
            f"{label} must include a username and password in production"
        )
    pair = f"{user}:{password}".lower()
    if pair in _WEAK_CREDENTIAL_PAIRS or password.lower() in _WEAK_PASSWORDS:
        raise ValueError(
            f"{label} must not use default development credentials in production"
        )


class Settings(BaseSettings):
    # extra=ignore a propósito: .env comparte claves de frontend
    # (BETTER_AUTH_*, TWELVE_DATA_*, etc.) que el backend no modela.
    # Los typos de claves backend se cubren con tests de contrato
    # (test_settings_hermeticity) en vez de forbid global.
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
    # Worker scheduler (APScheduler jobs that enqueue Dramatiq actors). Disabled
    # in tests via WORKERS_ENABLED=false so TestClient lifespans stay quiet.
    workers_enabled: bool = True
    rate_limit_requests_per_minute: int = Field(default=300, ge=10, le=10000)
    # Lecturas de mercado (quote/candles/movers/indices): el frontend abanica
    # una llamada por ticker y pagina (ProPicks ~20, backtest ~60) y Vercel
    # serverless no comparte la cache entre instancias -> rafagas grandes en
    # uso normal. Tier propio y alto; son lecturas baratas cacheadas.
    rate_limit_market_requests_per_minute: int = Field(default=900, ge=10, le=100000)
    rate_limit_expensive_requests_per_minute: int = Field(default=20, ge=1, le=1000)
    financial_document_retention_days: int = Field(default=2555, ge=1)
    market_price_max_age_days: int = Field(default=3, ge=0, le=30)

    database_url: str = "sqlite:///./portfolio_research_os.db"
    thesis_graph_checkpoint_path: Path = Path("./storage/thesis_graph_checkpoints.db")
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    duckdb_path: Path = Path("./storage/analytics.duckdb")

    minio_endpoint: str = "localhost:9002"
    minio_access_key: str = "portfolio"
    minio_secret_key: str = "portfoliosecret"
    minio_bucket: str = "research"
    document_storage_backend: str = "minio"
    # Mongo (auth Better Auth del frontend). Se valida aqui solo para poder
    # rechazar credenciales por defecto en produccion; el data-engine no
    # conecta a Mongo.
    mongodb_uri: str | None = Field(default=None, repr=False)

    finnhub_api_key: str | None = None
    # Vendor de quotes/profile del screener real ("finnhub" | "yahoo").
    # Env: SCREENER_QUOTE_VENDOR. Default Finnhub (comportamiento actual).
    screener_quote_vendor: str = "finnhub"
    ibkr_flex_token: str | None = None
    ibkr_flex_query_id: str | None = None
    # SEC fair-access: exige UA declarado con contacto; bloquea placeholders
    # tipo example.com con 403. Este valor verificado 200 desde prod (25/9).
    sec_user_agent: str = "CavaAI research contact@cavaai.local"
    # Directorio con snapshots EDGAR (manifest.json ticker->CIK,
    # companyfacts/CIK##########.json, submissions/CIK##########.json).
    # La SEC bloquea las IPs de datacenter; los snapshots se generan fuera
    # (PC residencial, espejo) y se despliegan con la app.
    sec_snapshot_dir: str | None = None
    # Directorio con snapshots ESEF (manifest.json issuers LEI->{ticker,...},
    # snapshots/<LEI>.json normalizados desde filings.xbrl.org). Mismo motivo
    # que SEC: los datos viajan con la app, nunca se piden en caliente.
    esef_snapshot_dir: str | None = None
    telegram_enabled: bool = False
    telegram_bot_token: str | None = Field(default=None, repr=False)
    telegram_chat_id: str | None = None
    telegram_api_base_url: str = "https://api.telegram.org"
    telegram_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    # Aprobación de tesis por Telegram (human-in-the-loop mínimo viable).
    # Apagado por defecto: sin este flag no se envía nada ni se sondea nada.
    # Env: TELEGRAM_APPROVAL_ENABLED.
    telegram_approval_enabled: bool = False
    # Fichero donde el poller persiste el offset de getUpdates.
    # Env: TELEGRAM_APPROVAL_STATE_PATH.
    telegram_approval_state_path: str = "./storage/telegram_approval_offset"
    # Intervalo del poller entre pasadas getUpdates (solo scripts/poller).
    # Env: TELEGRAM_APPROVAL_POLL_INTERVAL_SECONDS.
    telegram_approval_poll_interval_seconds: int = Field(default=15, ge=5, le=300)
    # Senales insider (Form 4 EDGAR): alerta Telegram 'insider buy' apagada
    # por defecto. Env: INSIDER_ALERTS_ENABLED.
    insider_alerts_enabled: bool = False
    # Langfuse Cloud EU shadow tracing (stage 3): SOLO observabilidad.
    # Apagado por defecto; nunca es fuente de verdad de negocio (eso es
    # Postgres). Sin payloads: solo metadatos de la allowlist. Muestreo del
    # 10% en corridas OK; los fallos se trazan siempre (buffer en memoria).
    # Env: LANGFUSE_ENABLED / LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY /
    # LANGFUSE_HOST / LANGFUSE_SAMPLE_RATE.
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = Field(default=None, repr=False)
    langfuse_secret_key: str | None = Field(default=None, repr=False)
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    fmp_api_key: str | None = None
    fred_api_key: str | None = None
    opencode_go_api_key: str | None = Field(default=None, repr=False)
    opencode_go_base_url: str = "https://opencode.ai/zen/go/v1"
    # Default cheap-but-good model. Overridable WITHOUT code change via env
    # OPENCODE_GO_MODEL (e.g. OPENCODE_GO_MODEL=qwen3.7-plus). Ver también
    # default_model_from_env() en app/llm/model_aliases.py.
    opencode_go_model: str = "space-bunny-free"
    # OpenCode Go exige cabecera x-opencode-session en todas las llamadas
    # (sin ella: MissingSessionID). ID estable por despliegue, mejora el
    # enrutado/cacheo del proveedor. Env: OPENCODE_GO_SESSION.
    opencode_go_session: str = "cavaai-prod"

    # TypeSafe Jev (capa de micro-decisiones, SystemOne API). Env: TYPESAFE_API_KEY.
    # Factura por uso ($0.042/MTok in); sin key el cliente no se construye.
    typesafe_api_key: str | None = None
    typesafe_base_url: str = "https://api.typesafe.ai"
    typesafe_model: str = "jev-latest"
    llm_enabled: bool = True
    # CavaAI intentionally uses one provider for every task.
    llm_provider: str = "opencode-go"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_model_overrides: dict[str, str] = Field(default_factory=dict)
    llm_max_output_tokens: int = Field(default=16_000, ge=1, le=1_000_000)
    llm_daily_cap_eur: float = Field(default=1.50, ge=0)
    llm_monthly_cap_eur: float = Field(default=40.00, ge=0)

    @property
    def is_production(self) -> bool:
        # APP_ENV canonico: acepta los alias 'production' y 'prod'. Toda
        # decision de seguridad debe usar esta propiedad; comparar solo con
        # 'production' dejaba 'prod' sin forzar auth firmada.
        return self.app_env.lower() in {"production", "prod"}

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        if not self.is_production:
            return self
        if not self.research_auth_secret:
            raise ValueError("RESEARCH_AUTH_SECRET is required in production")
        if self.document_storage_backend != "minio":
            raise ValueError("MinIO is required for production document originals")
        if self.minio_secret_key.lower() in _WEAK_MINIO_SECRET_KEYS:
            raise ValueError("MINIO_SECRET_KEY must not use a development default in production")
        if self.minio_access_key.lower() in _WEAK_MINIO_ACCESS_KEYS:
            raise ValueError("MINIO_ACCESS_KEY must not use a development default in production")
        database_scheme = (self.database_url.split(":", 1) or [""])[0].lower()
        if database_scheme in {"postgres", "postgresql"}:
            _assert_strong_credentials(self.database_url, label="DATABASE_URL")
        if self.mongodb_uri:
            _assert_strong_credentials(self.mongodb_uri, label="MONGODB_URI")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
