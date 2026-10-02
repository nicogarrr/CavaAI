"""Borrado de financial_facts compatible con las FK de Postgres."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.models import (
    CallClaim,
    ExpectationReview,
    FactRevision,
    FinancialFact,
    KPIExtractionCandidate,
    ManagementPromise,
)

logger = logging.getLogger(__name__)


def tenant_condition(db: Session) -> Any:
    tenant_id = db.info.get("tenant_id")
    return (
        FinancialFact.tenant_id == tenant_id
        if tenant_id is not None
        else FinancialFact.tenant_id.is_(None)
    )


def _human_approved_filter() -> Any:
    """Hechos con correccion humana: FactRevision aprobada o candidato KPI aprobado."""
    return or_(
        FinancialFact.id.in_(
            select(FactRevision.financial_fact_id).where(FactRevision.status == "approved")
        ),
        FinancialFact.id.in_(
            select(KPIExtractionCandidate.canonical_fact_id).where(
                KPIExtractionCandidate.status == "approved",
                KPIExtractionCandidate.canonical_fact_id.is_not(None),
            )
        ),
    )


def delete_financial_facts(db: Session, *conditions: Any) -> int:
    """Borra financial_facts sin violar las FK entrantes en Postgres.

    entities.py declara ``ondelete="SET NULL"``/``"CASCADE"`` en las FK hacia
    ``financial_facts.id``, pero las migraciones no las materializaron (ver el
    docstring de 0032): en Postgres son NO ACTION y un DELETE de un hecho ya
    referenciado revienta con ForeignKeyViolation (visto en prod con
    ``expectation_reviews.actual_fact_id`` al pulsar "Refrescar SEC"). Aqui se
    aplica a mano lo que el modelo promete: se desvinculan las referencias
    anulables y se borran las revisiones del hecho (CASCADE).

    Veracidad: un hecho con correccion humana aprobada (FactRevision approved o
    KPIExtractionCandidate approved apuntandolo) NO se borra; el valor
    aprobado gana al del proveedor. Devuelve cuantos hechos se conservaron por
    eso, para que quien refresca lo cuente como skip y no como error.
    """
    approved = _human_approved_filter()
    kept = int(
        db.scalar(select(func.count()).select_from(FinancialFact).where(*conditions, approved))
        or 0
    )
    if kept:
        logger.info("financial_facts: %d hecho(s) con correccion humana conservados", kept)
    deletable = (*conditions, ~approved)
    ids = select(FinancialFact.id).where(*deletable)
    opts = {"synchronize_session": False}
    for model, column in (
        (KPIExtractionCandidate, "canonical_fact_id"),
        (CallClaim, "linked_result_id"),
        (ExpectationReview, "actual_fact_id"),
        (ManagementPromise, "actual_fact_id"),
    ):
        attr = getattr(model, column)
        db.execute(
            update(model).where(attr.in_(ids)).values({column: None}), execution_options=opts
        )
    db.execute(
        delete(FactRevision).where(FactRevision.financial_fact_id.in_(ids)),
        execution_options=opts,
    )
    db.execute(delete(FinancialFact).where(*deletable), execution_options=opts)
    return kept


def drop_shadowed_facts(db: Session, company_id: int, source_id: int, *conditions: Any) -> int:
    """Tras reingerir, quita los hechos nuevos del proveedor que duplican un hecho
    aprobado por un humano (misma empresa, metrica y periodo). Gana el aprobado.
    """
    db.flush()
    protected = db.execute(
        select(FinancialFact.id, FinancialFact.metric, FinancialFact.period).where(
            FinancialFact.company_id == company_id, *conditions, _human_approved_filter()
        )
    ).all()
    dropped = 0
    for fact_id, metric, period in protected:
        shadow = (
            FinancialFact.company_id == company_id,
            FinancialFact.metric == metric,
            FinancialFact.period == period,
            FinancialFact.source_id == source_id,
            FinancialFact.id > fact_id,
            *conditions,
        )
        dropped += int(
            db.scalar(select(func.count()).select_from(FinancialFact).where(*shadow)) or 0
        )
        delete_financial_facts(db, *shadow)
    if dropped:
        logger.info(
            "financial_facts: %d hecho(s) del proveedor omitidos por duplicar un valor aprobado",
            dropped,
        )
    return dropped
