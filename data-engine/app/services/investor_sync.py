"""Refresco periodico de las carteras de inversores (13F + Form 4).

Hasta ahora el 13F solo entraba por ``POST /api/ownership/managers/sync`` y los
Form 4 de Trump/Bezos por un script manual: /investors se quedaba con lo ultimo
que alguien sincronizo a mano. Esta funcion es el cuerpo del actor semanal.

Un fallo de un gestor o de un declarante NO aborta a los demas: se anota en
``errors`` y se sigue. Nada se infiere; solo se llama a los sincronizadores que
ya existen (SEC EDGAR, gratis, con el throttle compartido).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import redact_secrets
from app.services.investor_portfolio import FORM4_FILER_CIK, sync_form4
from app.services.manager_holding_ingestion_service import (
    REVIEWED_MANAGERS,
    ManagerHoldingIngestionService,
)

logger = logging.getLogger(__name__)


def _describe(exc: Exception) -> str:
    """Texto de error acotado y sin secretos (URLs con token, etc.)."""
    return redact_secrets(f"{type(exc).__name__}: {exc}")[:200]


def sync_investor_holdings(
    db: Session,
    *,
    manager_sync: Callable[[Session, str], dict[str, Any]] | None = None,
    form4_sync: Callable[[Session, str], int] | None = None,
) -> dict[str, Any]:
    if manager_sync is None:
        service = ManagerHoldingIngestionService()

        def default_manager_sync(session: Session, cik: str) -> dict[str, Any]:
            return service.sync_manager(session, cik=cik)

        manager_sync = default_manager_sync

    form4_sync = form4_sync or (lambda session, slug: sync_form4(session, slug))

    managers: dict[str, str] = {}
    errors: list[dict[str, str]] = []
    for cik in REVIEWED_MANAGERS:
        try:
            result = manager_sync(db, cik)
            status = str(result.get("status", "unknown"))
            managers[cik] = status
            if status != "ok":
                # sync_manager NO lanza cuando la SEC falla: devuelve
                # {"status": "unavailable", "reason": ...}. Sin esto el job
                # diria "ok" sin haber refrescado nada y la coalescencia
                # retendria el claim hasta la semana siguiente.
                reason = str(result.get("reason") or result.get("note") or "sin detalle")
                errors.append({"source": f"13f:{cik}", "error": f"{status}: {reason}"[:200]})
        except Exception as exc:  # un gestor caido no frena a los demas
            db.rollback()
            logger.warning("13F sync failed for %s: %s", cik, exc)
            managers[cik] = "error"
            errors.append({"source": f"13f:{cik}", "error": _describe(exc)})

    form4_created: dict[str, int] = {}
    for slug in sorted(FORM4_FILER_CIK):
        try:
            form4_created[slug] = form4_sync(db, slug)
        except Exception as exc:
            db.rollback()
            logger.warning("Form 4 sync failed for %s: %s", slug, exc)
            errors.append({"source": f"form4:{slug}", "error": _describe(exc)})

    attempted = len(managers) + len(FORM4_FILER_CIK)
    failed = len(errors)
    status = "ok" if failed == 0 else ("error" if failed >= attempted else "partial")
    return {
        "status": status,
        "managers": managers,
        "form4_new_movements": form4_created,
        "errors": errors,
    }
