"""FastAPI bootstrap for the CavaAI data engine."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router as research_api_router
from app.api.routes.health import router as health_router
from app.core.auth import get_research_principal
from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.core.rate_limit import enforce_rate_limit
from app.core.raw_body import RawBodyMiddleware
from app.llm.factory import validate_llm_configuration
from app.llm.model_aliases import configure_model_aliases
from app.seed import ensure_company_master

try:  # preload optional probe modules during process startup, not in a request
    import urllib.request  # noqa: F401

    import redis  # noqa: F401
except Exception:  # noqa: BLE001 — readiness reports the unavailable dependency
    pass


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
    # Los executores de sonda son de nivel de modulo: sin apagarlos, un
    # TestClient que abre y cierra muitas veces deja hilos vivos por proceso.
    # wait=False porque pueden tener sondas colgadas.
    _HEALTH_REQUIRED_EXECUTOR.shutdown(wait=False)
    _HEALTH_PROBE_EXECUTOR.shutdown(wait=False)


_app_env = get_settings().app_env.strip().lower()
_EXPOSE_SCHEMA = _app_env in {"local", "test", "ci", "dev", "development"}

# /docs, /redoc y /openapi.json se montan SIN firma porque cuelgan de app, no
# del research router. Publicar el esquema completo de las 188 rutas firmadas es
# un plano gratis para quien intente reutilizar una firma capturada. Solo se
# exponen en entornos locales; data-engine/scripts/export_openapi.py sigue
# generando el JSON via app.openapi() sin necesidad de HTTP.
app = FastAPI(
    title="CavaAI Research Engine",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _EXPOSE_SCHEMA else None,
    redoc_url="/redoc" if _EXPOSE_SCHEMA else None,
    openapi_url="/openapi.json" if _EXPOSE_SCHEMA else None,
)

app.add_middleware(
    RawBodyMiddleware,
    max_body_bytes_by_prefix={
        # La ruta de subida valida contra MAX_DOCUMENT_BYTES (15MB); el
        # middleware le deja pasar hasta 16MB para que sea ella quien
        # responda con su error de validacion, no un 413 generico.
        "/api/knowledge/documents/upload": 16 * 1024 * 1024,
        # Misma regla para la ingesta de fuentes: la ruta valida el fichero
        # decodificado contra MAX_DOCUMENT_BYTES (15MB) y el middleware deja
        # margen de ~1MB para el overhead multipart (boundaries + headers).
        "/api/sources/documents/ingest-file": 16 * 1024 * 1024,
    },
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CavaAI-Tenant", "X-CavaAI-User", "X-CavaAI-Timestamp", "X-CavaAI-Nonce", "X-CavaAI-Method", "X-CavaAI-Path", "X-CavaAI-Body-Hash", "X-CavaAI-Signature"],
)

private_dependencies = [Depends(get_research_principal), Depends(enforce_rate_limit)]

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


HEALTH_READY_TIMEOUT_SECONDS = 1.0
# Dos executors y no uno. La BD es la unica dependencia hard-required: si
# comparte pool con Redis/Qdrant/MinIO, tres sondas opcionales que se quedan
# colgadas (aceptan la conexion y nunca responden) consumian los 4 hilos y la
# sonda de BD ya nofindaba ninguno -> checks["database"] != "ok" -> 503
# permanente con la base de datos perfectamente sana, y sin reaper que lo
# desbloquee. asyncio.wait_for cancela la espera, no el hilo.
_HEALTH_REQUIRED_EXECUTOR = ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="cavaai-health-required"
)
# Un executor dedicado evita que ``asyncio.run``/el cierre de un test espere a
# los hilos de sondas que vencieron su timeout. Las sondas conservan su propio
# timeout de red y los hilos remanentes terminan solos al concluir.
_HEALTH_PROBE_EXECUTOR = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="cavaai-health-probe"
)


def _probe_database(_settings) -> str:
    """Comprueba la BD sin convertir errores de infraestructura en 500."""
    from sqlalchemy import text

    from app.core.database import SessionLocal

    with SessionLocal() as db:
        # statement_timeout acota la sonda a nivel de servidor. Sin el, un
        # lock de Postgres puede dejar el hilo bloqueado indefinidamente y
        #Slottear el executor dedicado para siempre. En SQLite no aplica.
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            db.execute(text("SET LOCAL statement_timeout = '1s'"))
        db.execute(text("SELECT 1"))
    return "ok"


def _probe_redis(settings) -> str:
    """Redis es opcional en SQLite local, pero su estado se reporta siempre."""
    import redis

    client = redis.from_url(
        settings.redis_url,
        socket_connect_timeout=HEALTH_READY_TIMEOUT_SECONDS,
        socket_timeout=HEALTH_READY_TIMEOUT_SECONDS,
    )
    client.ping()
    return "ok"


def _probe_qdrant(settings) -> str:
    """Qdrant liveness; un 4xx/5xx nunca se considera una respuesta sana.

    Unificado con docker-compose (GET /healthz vía bash /dev/tcp).
    /readyz exigía colecciones/shards listos y marcaba degraded en
    arranques fríos aunque Qdrant ya aceptaba tráfico.
    """
    import urllib.request

    with urllib.request.urlopen(
        f"{settings.qdrant_url.rstrip('/')}/healthz",
        timeout=HEALTH_READY_TIMEOUT_SECONDS,
    ) as resp:
        return "ok" if resp.status < 500 else f"error:status_{resp.status}"


def _probe_minio(settings) -> str:
    """MinIO: cualquier respuesta HTTP <500 prueba que el endpoint está vivo."""
    import urllib.error
    import urllib.request

    endpoint = settings.minio_endpoint
    if not endpoint.startswith("http"):
        endpoint = f"http://{endpoint}"
    try:
        with urllib.request.urlopen(
            endpoint, timeout=HEALTH_READY_TIMEOUT_SECONDS
        ) as resp:
            return "ok" if resp.status < 500 else f"error:status_{resp.status}"
    except urllib.error.HTTPError as exc:
        return "ok" if exc.code < 500 else f"error:status_{exc.code}"


async def _run_health_probe(
    name: str, probe, settings, executor=None
) -> tuple[str, str]:
    """Ejecuta una sonda en un hilo y la corta al deadline compartido."""
    try:
        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(
            executor or _HEALTH_PROBE_EXECUTOR, probe, settings
        )
        result = await asyncio.wait_for(
            future,
            timeout=HEALTH_READY_TIMEOUT_SECONDS,
        )
        return name, str(result)
    except TimeoutError:
        return name, "error:TimeoutError"
    except Exception as exc:  # noqa: BLE001 — reportar y continuar
        return name, f"error:{type(exc).__name__}"


@app.get("/health/ready")
async def health_ready():
    """Readiness concurrente: la BD es la única dependencia hard-required local.

    Redis, Qdrant y MinIO se sondean simultáneamente, con un timeout de un
    segundo. Una dependencia caída se informa en la respuesta, pero no mantiene
    bloqueada la ruta ni convierte un backend SQLite sano en 503.
    """
    settings = get_settings()
    # La BD va a un executor propio: es la unica que puede tirar el 503, y no
    # puede quedarse sin hilo por culpa de las opcionales.
    results = await asyncio.gather(
        _run_health_probe(
            "database", _probe_database, settings, _HEALTH_REQUIRED_EXECUTOR
        ),
        *(
            _run_health_probe(name, probe, settings)
            for name, probe in (
                ("redis", _probe_redis),
                ("qdrant", _probe_qdrant),
                ("minio", _probe_minio),
            )
        ),
    )
    checks = dict(results)

    # La BD es la única dependencia hard-required. Redis, Qdrant y MinIO se
    # reportan sin convertir una caída opcional en un 503 ni alargar la ruta.
    ready = checks.get("database") == "ok"

    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "degraded",
            "checks": checks,
        },
    )
