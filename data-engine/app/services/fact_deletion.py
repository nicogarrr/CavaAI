"""Borrado de financial_facts compatible con las FK de Postgres."""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import (
    CallClaim,
    ExpectationReview,
    FactRevision,
    FinancialFact,
    KPIExtractionCandidate,
    ManagementPromise,
)


def delete_financial_facts(db: Session, *conditions: Any) -> None:
    """Borra financial_facts sin violar las FK entrantes en Postgres.

    entities.py declara ``ondelete="SET NULL"``/``"CASCADE"`` en las FK hacia
    ``financial_facts.id``, pero las migraciones no las materializaron (ver el
    docstring de 0032): en Postgres son NO ACTION y un DELETE de un hecho ya
    referenciado revienta con ForeignKeyViolation (visto en prod con
    ``expectation_reviews.actual_fact_id`` al pulsar "Refrescar SEC"). Aqui se
    aplica a mano lo que el modelo promete: se desvinculan las referencias
    anulables y se borran las revisiones del hecho (CASCADE).
    """
    ids = select(FinancialFact.id).where(*conditions)
    opts = {"synchronize_session": False}
    for model, column in (
        (KPIExtractionCandidate, "canonical_fact_id"),
        (CallClaim, "linked_result_id"),
        (ExpectationReview, "actual_fact_id"),
        (ManagementPromise, "actual_fact_id"),
    ):
        attr = getattr(model, column)
        db.execute(update(model).where(attr.in_(ids)).values({column: None}), execution_options=opts)
    db.execute(
        delete(FactRevision).where(FactRevision.financial_fact_id.in_(ids)),
        execution_options=opts,
    )
    db.execute(delete(FinancialFact).where(*conditions), execution_options=opts)

