"""delete_financial_facts respeta las FK entrantes aunque la BD sea NO ACTION.

En Postgres las migraciones no materializaron los ondelete de entities.py, y
"Refrescar SEC" fallaba con ForeignKeyViolation (expectation_reviews). Aqui el
esquema SQLite se crea SIN acciones referenciales y con FK activas, que es el
comportamiento de prod.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.entities import (
    Base,
    Company,
    Document,
    FactRevision,
    FinancialFact,
    ManagementPromise,
)
from app.services.fact_deletion import delete_financial_facts, drop_shadowed_facts


@pytest.fixture
def db():
    saved = []
    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            saved.append((fk, fk.ondelete))
            fk.ondelete = None
            if fk.constraint is not None:
                fk.constraint.ondelete = None
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _rec):  # pragma: no cover - trivial
        conn.execute("PRAGMA foreign_keys=ON")

    try:
        Base.metadata.create_all(engine)
    finally:
        for fk, action in saved:
            fk.ondelete = action
            if fk.constraint is not None:
                fk.constraint.ondelete = action
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


def _seed(db):
    company = Company(ticker="ASTS", name="AST", exchange="NASDAQ", currency="USD",
                      company_type="holding", valuation_model="unassigned")
    db.add(company)
    db.flush()
    fact = FinancialFact(company_id=company.id, metric="net_income", value=Decimal("1"),
                         unit="USD", period="FY2025", fiscal_year=2025,
                         source_type="SEC", is_reported=False)
    db.add(fact)
    db.flush()
    db.add(FactRevision(financial_fact_id=fact.id, previous_value=Decimal("1"),
                        new_value=Decimal("2"), reason="restated", canonical_version=1))
    promise = ManagementPromise(company_id=company.id, promise="x", promise_date=date(2026, 1, 1),
                                expected_period="FY2026", actual_fact_id=fact.id)
    db.add(promise)
    db.commit()
    return company, fact, promise


def test_plain_delete_violates_fk_without_ondelete(db):
    _company, fact, _promise = _seed(db)
    with pytest.raises(IntegrityError):
        db.execute(delete(FinancialFact).where(FinancialFact.id == fact.id))
        db.flush()
    db.rollback()


def test_helper_detaches_references_and_deletes_fact(db):
    company, fact, promise = _seed(db)
    delete_financial_facts(db, FinancialFact.company_id == company.id)
    db.commit()
    assert db.scalar(select(FinancialFact.id).where(FinancialFact.id == fact.id)) is None
    assert db.scalar(select(FactRevision.id)) is None
    db.refresh(promise)
    assert promise.actual_fact_id is None


def test_helper_keeps_other_companies_facts(db):
    company, fact, _promise = _seed(db)
    other = Company(ticker="X", name="X", exchange="NASDAQ", currency="USD",
                    company_type="holding", valuation_model="unassigned")
    db.add(other)
    db.flush()
    keep = FinancialFact(company_id=other.id, metric="revenue", value=Decimal("5"), unit="USD",
                         period="FY2025", fiscal_year=2025, source_type="SEC", is_reported=True)
    db.add(keep)
    db.commit()
    delete_financial_facts(db, FinancialFact.company_id == company.id)
    db.commit()
    assert db.scalar(select(FinancialFact.id).where(FinancialFact.id == keep.id)) == keep.id


def _approved_revision(db, fact):
    rev = db.scalar(select(FactRevision).where(FactRevision.financial_fact_id == fact.id))
    rev.status = "approved"
    db.commit()


def test_helper_keeps_fact_with_approved_revision(db):
    company, fact, promise = _seed(db)
    _approved_revision(db, fact)
    kept = delete_financial_facts(db, FinancialFact.company_id == company.id)
    db.commit()
    assert kept == 1
    assert db.scalar(select(FinancialFact.id).where(FinancialFact.id == fact.id)) == fact.id
    assert db.scalar(select(FactRevision.id)) is not None
    db.refresh(promise)
    assert promise.actual_fact_id == fact.id


def test_provider_duplicate_of_approved_fact_is_dropped_after_reingest(db):
    company, fact, _promise = _seed(db)
    _approved_revision(db, fact)
    # el refresh no pudo borrar el aprobado; la reingesta inserta el valor del proveedor
    doc = Document(company_id=company.id, title="10-K", source_type="SEC")
    db.add(doc)
    db.flush()
    dup = FinancialFact(company_id=company.id, metric=fact.metric, value=Decimal("9"),
                        unit="USD", period=fact.period, fiscal_year=2025,
                        source_type="SEC", is_reported=True, source_id=doc.id)
    db.add(dup)
    other = FinancialFact(company_id=company.id, metric="revenue", value=Decimal("7"),
                          unit="USD", period=fact.period, fiscal_year=2025,
                          source_type="SEC", is_reported=True, source_id=doc.id)
    db.add(other)
    db.commit()
    dropped = drop_shadowed_facts(db, company.id, doc.id, FinancialFact.tenant_id.is_(None))
    db.commit()
    assert dropped == 1
    ids = set(db.scalars(select(FinancialFact.id)))
    assert fact.id in ids and other.id in ids and dup.id not in ids
