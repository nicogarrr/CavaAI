"""fact_chunk_service: chunks RAG desde financial_facts, honestos e idempotentes."""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, Document, DocumentChunk, FinancialFact
from app.services.fact_chunk_service import sync_company_fact_chunks


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db) -> Company:
    company = Company(ticker="TEF", name="TELEFONICA SA", exchange="BME", currency="EUR",
                      company_type="research_candidate", valuation_model="unassigned",
                      special_sources=[], special_risks=[], factor_tags=[])
    db.add(company)
    db.flush()
    return company


def _fact(db, company, metric, value, year, unit="EUR", source="ESEF") -> None:
    db.add(
        FinancialFact(
            company_id=company.id,
            metric=metric,
            value=Decimal(str(value)),
            unit=unit,
            period=f"{year}-12-31:FY",
            fiscal_year=year,
            fiscal_quarter="FY",
            source_type=source,
            is_reported=True,
        )
    )
    db.flush()


def test_sync_creates_one_chunk_per_year_with_real_figures(db):
    company = _company(db)
    db.add(Document(company_id=company.id, title="ESEF XBRL facts - TEF", source_type="ESEF"))
    db.flush()
    _fact(db, company, "revenue", 41315000000, 2024)
    _fact(db, company, "net_income", -49000000, 2024)
    _fact(db, company, "revenue", 41000000000, 2023)

    stats = sync_company_fact_chunks(db, company)
    assert stats == {"sources": 1, "chunks": 2}

    chunks = list(db.scalars(select(DocumentChunk).order_by(DocumentChunk.chunk_index)).all())
    assert len(chunks) == 2
    latest = chunks[0]
    assert "TELEFONICA SA (TEF)" in latest.text
    assert "2024" in latest.text
    assert "ingresos 41,31 mil M EUR" in latest.text
    assert "beneficio neto -49,00 M EUR" in latest.text
    assert "fuente ESEF" in latest.text


def test_sync_is_idempotent_and_replaces_stale_chunks(db):
    company = _company(db)
    db.add(Document(company_id=company.id, title="ESEF XBRL facts - TEF", source_type="ESEF"))
    db.flush()
    _fact(db, company, "revenue", 100, 2024)
    sync_company_fact_chunks(db, company)
    sync_company_fact_chunks(db, company)
    assert len(list(db.scalars(select(DocumentChunk)).all())) == 1

    # Si los hechos desaparecen (re-ingesta sin datos), el chunk tambien:
    # nada de cifras viejas en el indice.
    db.query(FinancialFact).delete()
    stats = sync_company_fact_chunks(db, company)
    assert stats["chunks"] == 0
    assert len(list(db.scalars(select(DocumentChunk)).all())) == 0


def test_ratio_and_share_units_format(db):
    company = _company(db)
    db.add(Document(company_id=company.id, title="SEC XBRL facts - X", source_type="SEC"))
    db.flush()
    _fact(db, company, "net_margin", "0.1523", 2024, unit="decimal", source="SEC")
    _fact(db, company, "eps_diluted", "1.234", 2024, unit="USD/share", source="SEC")
    sync_company_fact_chunks(db, company)
    text = db.scalar(select(DocumentChunk)).text
    assert "margen neto 15,23 %" in text
    assert "BPA diluido 1,23 USD/accion" in text


def test_company_without_documents_is_a_noop(db):
    company = _company(db)
    _fact(db, company, "revenue", 100, 2024)
    stats = sync_company_fact_chunks(db, company)
    assert stats == {"sources": 0, "chunks": 0}
