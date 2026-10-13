"""Que ha cambiado en una empresa desde la ultima visita del usuario.

Solo lee lo que ya esta guardado (documentos, hechos y cambios de tesis con su
``created_at``). No infiere nada: cuenta y lista. La fecha de "ultima visita"
la aporta el cliente (``since``); aqui no se guarda estado.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Document, FinancialFact, ThesisChange

MAX_ITEMS = 8


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def changes_since(db: Session, company_id: int, since: datetime) -> dict[str, Any]:
    since = _aware(since)
    docs = db.execute(
        select(Document)
        .where(Document.company_id == company_id, Document.created_at > since)
        .order_by(Document.created_at.desc())
        .limit(MAX_ITEMS)
    ).scalars().all()
    docs_total = db.scalar(
        select(func.count()).select_from(Document).where(
            Document.company_id == company_id, Document.created_at > since
        )
    ) or 0
    fact_rows = db.execute(
        select(FinancialFact.metric, func.count())
        .where(FinancialFact.company_id == company_id, FinancialFact.created_at > since)
        .group_by(FinancialFact.metric)
        .order_by(func.count().desc(), FinancialFact.metric)
        .limit(MAX_ITEMS)
    ).all()
    facts_total = db.scalar(
        select(func.count()).select_from(FinancialFact).where(
            FinancialFact.company_id == company_id, FinancialFact.created_at > since
        )
    ) or 0
    changes = db.execute(
        select(ThesisChange)
        .where(ThesisChange.company_id == company_id, ThesisChange.created_at > since)
        .order_by(ThesisChange.created_at.desc())
        .limit(MAX_ITEMS)
    ).scalars().all()
    return {
        "since": since.isoformat(),
        "documentos": {
            "total": docs_total,
            "items": [
                {
                    "titulo": d.title,
                    "tipo": d.source_type,
                    "url": d.source_url,
                    "fecha": d.published_at.date().isoformat() if d.published_at else None,
                }
                for d in docs
            ],
        },
        "hechos": {
            "total": facts_total,
            "por_metrica": [{"metric": metric, "n": n} for metric, n in fact_rows],
        },
        "cambios_tesis": [
            {
                "resumen": c.summary,
                "direccion": c.impact_direction,
                "requiere_revision": bool(c.requires_review),
                "fecha": _aware(c.created_at).date().isoformat(),
            }
            for c in changes
        ],
    }
