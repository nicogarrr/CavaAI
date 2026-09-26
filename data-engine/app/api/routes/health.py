"""Public health endpoint for the CavaAI data engine.

GET /api/health — sin firma (público): reporta estado de la BD, del
scheduler de workers y la versión del código. Pensado para orquestación
(load balancers, cron de monitoreo, deploy checks) que no tiene identidad
Research OS.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import SessionLocal

router = APIRouter(tags=["health"])

_REPO_ROOT = Path(__file__).resolve().parents[4]  # CavaAI/ (raíz del repo)


def _git_version() -> str:
    """Versión corta 'main-<sha>' del commit desplegado; 'main-unknown' si git no responde."""
    try:
        sha = (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=_REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=2,
            )
            .stdout.strip()
        )
        return f"main-{sha}" if sha else "main-unknown"
    except Exception:  # noqa: BLE001 — el health nunca debe romperse por git
        return "main-unknown"


def _scheduler_status() -> dict:
    """Estado del scheduler de workers.

    La app arranca el scheduler dentro del lifespan (APScheduler en
    background) únicamente si WORKERS_ENABLED=true; no hay una instancia
    global observable desde este proceso, así que `running` refleja la
    config: si los workers están habilitados, el lifespan lo está
    ejecutando. `jobs` cuenta los trabajos registrados por build_scheduler.
    """
    settings = get_settings()
    if not settings.workers_enabled:
        return {
            "enabled": False,
            "running": False,
            "jobs": 0,
            "last_run_at": None,
        }
    try:
        from app.workers.scheduler import build_scheduler

        probe = build_scheduler(background=True)
        jobs = len(probe.get_jobs())
        # Sin start() el probe no lanza hilos; no llamar shutdown() porque
        # APScheduler lanza SchedulerNotRunningError con un scheduler parado.
        return {
            "enabled": True,
            "running": True,
            "jobs": jobs,
            "last_run_at": None,
        }
    except Exception as exc:  # noqa: BLE001 — reportar y seguir
        return {
            "enabled": True,
            "running": False,
            "jobs": 0,
            "last_run_at": None,
            # Solo el tipo de excepcion: este endpoint es publico y el texto
            # de un error de import/config puede traer rutas del host.
            "error": type(exc).__name__,
        }


@router.get("/health")
async def health() -> dict:
    """Readiness: BD (SELECT 1), scheduler y versión."""
    settings = get_settings()

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # noqa: BLE001 — surface dependency status
        database = f"error:{type(exc).__name__}"

    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "scheduler": _scheduler_status(),
        "version": _git_version(),
    }