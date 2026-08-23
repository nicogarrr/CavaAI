"""FastAPI bootstrap for the CavaAI data engine."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router as research_api_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.auth import get_research_principal
from app.core.database import SessionLocal, init_db
from app.core.rate_limit import RateLimitMiddleware
from app.llm.factory import validate_llm_configuration
from app.llm.model_aliases import configure_model_aliases
from app.seed import ensure_company_master


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.app_env.lower() == "test":
        # Tests use an isolated disposable schema. Runtime environments migrate
        # with Alembic before the process starts.
        init_db()
    with SessionLocal() as db:
        configure_model_aliases(db)
    validate_llm_configuration(settings)
    if settings.app_env.lower() != "production":
        ensure_company_master()

    # Schedule the worker jobs (Dramatiq enqueues) in the background without
    # blocking startup. Flagged off in tests via WORKERS_ENABLED=false.
    scheduler = None
    if settings.workers_enabled:
        from app.workers.scheduler import build_scheduler

        scheduler = build_scheduler(background=True)
        scheduler.start()

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="CavaAI Research Engine", version="1.0.0", lifespan=lifespan)

app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

private_dependencies = [Depends(get_research_principal)]

# /api/health es público (sin firma): lo montamos fuera del research API
# para que orquestación/monitoreo pueda consultarlo sin identidad.
app.include_router(health_router, prefix="/api")

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

    # MinIO — best-effort TCP/HTTP probe via endpoint string. MinIO answers
    # anonymous GETs on the S3 API with 4xx, which still proves reachability.
    try:
        import urllib.error
        import urllib.request

        endpoint = settings.minio_endpoint
        if not endpoint.startswith("http"):
            endpoint = f"http://{endpoint}"
        try:
            with urllib.request.urlopen(endpoint, timeout=2) as resp:
                checks["minio"] = "ok" if resp.status < 500 else f"error:status_{resp.status}"
        except urllib.error.HTTPError as exc:
            checks["minio"] = "ok" if exc.code < 500 else f"error:status_{exc.code}"
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
