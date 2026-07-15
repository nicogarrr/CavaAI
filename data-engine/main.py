"""FastAPI bootstrap for the CavaAI data engine."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router as research_api_router
from app.core.config import get_settings
from app.core.auth import get_research_principal
from app.core.database import init_db
from app.seed import ensure_company_master
from routers.analytics import router as analytics_router
from routers.fundamentals import router as fundamentals_router
from routers.market import router as market_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.app_env.lower() == "test":
        # Tests use an isolated disposable schema. Runtime environments migrate
        # with Alembic before the process starts.
        init_db()
    if settings.app_env.lower() != "production":
        ensure_company_master()
    yield


app = FastAPI(title="CavaAI Research Engine", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

private_dependencies = [Depends(get_research_principal)]

app.include_router(fundamentals_router, dependencies=private_dependencies)
app.include_router(market_router, dependencies=private_dependencies)
app.include_router(analytics_router, dependencies=private_dependencies)
app.include_router(
    research_api_router,
    prefix="/api",
    dependencies=private_dependencies,
)


@app.get("/")
async def root():
    return {"status": "ok", "service": "CavaAI Research Engine"}


@app.get("/health")
@app.get("/health/live")
async def health_live():
    """Liveness — process is up. Does not check dependencies."""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready():
    """Readiness — verifies critical dependencies when configured."""
    from sqlalchemy import text

    from app.core.config import get_settings
    from app.core.database import SessionLocal

    settings = get_settings()
    checks: dict[str, str] = {}

    # Postgres / SQLite
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 — surface dependency status
        checks["database"] = f"error:{type(exc).__name__}"

    # Redis (optional locally)
    try:
        import redis

        client = redis.from_url(settings.redis_url, socket_connect_timeout=1)
        client.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error:{type(exc).__name__}"

    # Qdrant
    try:
        import urllib.request

        with urllib.request.urlopen(f"{settings.qdrant_url.rstrip('/')}/readyz", timeout=1) as resp:
            checks["qdrant"] = "ok" if resp.status < 500 else f"error:status_{resp.status}"
    except Exception as exc:  # noqa: BLE001
        checks["qdrant"] = f"error:{type(exc).__name__}"

    # MinIO — best-effort TCP/HTTP probe via endpoint string
    try:
        import urllib.request

        endpoint = settings.minio_endpoint
        if not endpoint.startswith("http"):
            endpoint = f"http://{endpoint}"
        with urllib.request.urlopen(endpoint, timeout=1) as resp:
            checks["minio"] = "ok" if resp.status < 500 else f"error:status_{resp.status}"
    except Exception as exc:  # noqa: BLE001
        checks["minio"] = f"error:{type(exc).__name__}"

    ready = all(value == "ok" for key, value in checks.items() if key == "database")
    # Database is hard-required; other deps are reported but do not fail local SQLite-only runs
    # unless explicitly configured as non-sqlite.
    if not settings.database_url.startswith("sqlite"):
        ready = all(value == "ok" for value in checks.values())

    return {
        "status": "ready" if ready else "degraded",
        "checks": checks,
    }
