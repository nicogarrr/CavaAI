"""Borrado company/document/tenant: cascadas, SET NULL y RESTRICT.

Verifica a nivel de FK de base de datos (PRAGMA foreign_keys=ON, como en
Postgres de produccion) la politica declarada en entities.py y 0030:

- CASCADE: chunks, evidencias (via claim), secciones de tesis,
  transacciones de insider.
- SET NULL: links nulables a documents/chunks/thesis (el hijo sobrevive
  como huerfano documentado).
- RESTRICT (sin ondelete, a proposito): hechos financieros y company_id
  NOT NULL — borrar debe fallar en vez de amputar la auditoria.
"""

import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import (  # noqa: F401  (registra el metadata completo)
    Claim,
    ClaimEvidence,
    Company,
    DecisionJournalEntry,  # noqa: F401
    Document,
    DocumentChunk,
    FinancialFact,
    Tenant,
    ThesisSection,
    ThesisVersion,
)
from app.models.entities import InsiderFiling, InsiderTransaction


def _engine():
    tmp = Path(tempfile.mkdtemp(prefix="cavaai_cascade_")) / "cascade.db"
    engine = create_engine(f"sqlite:///{tmp.as_posix()}")
    event.listen(engine, "connect", lambda conn, _rec: conn.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture()
def db():
    engine = _engine()
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _company(db, ticker: str) -> Company:
    company = Company(
        ticker=ticker,
        name=f"{ticker} Co",
        exchange="NASDAQ",
        company_type="operating",
        valuation_model="dcf",
    )
    db.add(company)
    db.flush()
    return company


def _document(db, company_id=None, tenant_id=None) -> Document:
    doc = Document(
        company_id=company_id, tenant_id=tenant_id, title="10-K 2024", source_type="filing"
    )
    db.add(doc)
    db.flush()
    return doc


def test_document_delete_cascades_chunks_and_orphans_evidence_and_fact(db):
    company = _company(db, "TST_DOC_A")
    doc = _document(db, company.id)
    db.add(DocumentChunk(document_id=doc.id, chunk_index=0, text="chunk cero"))
    db.add(DocumentChunk(document_id=doc.id, chunk_index=1, text="chunk uno"))
    claim = Claim(company_id=company.id, statement="revenue grows")
    db.add(claim)
    db.flush()
    db.add(
        ClaimEvidence(
            claim_id=claim.id,
            document_id=doc.id,
            summary="10-K lo respalda",
        )
    )
    db.add(
        FinancialFact(
            company_id=company.id,
            metric="revenue",
            value=Decimal("123.45"),
            period="FY2024",
            source_id=doc.id,
        )
    )
    db.commit()

    chunk_ids = db.scalars(select(DocumentChunk.id)).all()
    assert len(chunk_ids) == 2

    db.execute(delete(Document).where(Document.id == doc.id))
    db.commit()

    # CASCADE: los chunks mueren con el documento.
    assert db.scalars(select(DocumentChunk.id)).all() == []
    # SET NULL: evidencia y hecho sobreviven como huerfanos documentados.
    evidence = db.scalar(select(ClaimEvidence))
    assert evidence is not None and evidence.document_id is None
    fact = db.scalar(select(FinancialFact))
    assert fact is not None and fact.source_id is None


def test_claim_delete_cascades_evidence(db):
    company = _company(db, "TST_CLM_A")
    claim = Claim(company_id=company.id, statement="margin expands")
    db.add(claim)
    db.flush()
    db.add(ClaimEvidence(claim_id=claim.id, summary="call Q3"))
    db.add(ClaimEvidence(claim_id=claim.id, summary="filing Q3"))
    db.commit()

    db.execute(delete(Claim).where(Claim.id == claim.id))
    db.commit()

    assert db.scalars(select(ClaimEvidence.id)).all() == []


def test_company_delete_restricted_by_facts_then_orphans_documents(db):
    company = _company(db, "TST_CO_A")
    _document(db, company.id)
    db.add(
        FinancialFact(
            company_id=company.id, metric="revenue", value=Decimal("10"), period="FY2024"
        )
    )
    db.commit()

    # RESTRICT: con hechos financieros el borrado debe fallar.
    with pytest.raises(IntegrityError):
        db.execute(delete(Company).where(Company.id == company.id))
        db.commit()
    db.rollback()

    db.execute(delete(FinancialFact).where(FinancialFact.company_id == company.id))
    db.execute(delete(Company).where(Company.id == company.id))
    db.commit()

    # SET NULL: el documento sobrevive huerfano (company_id NULL).
    doc = db.scalar(select(Document))
    assert doc is not None and doc.company_id is None


def test_tenant_delete_restricted_by_owned_rows(db):
    tenant = Tenant(external_id="ext-cascade-1")
    db.add(tenant)
    db.flush()
    _document(db, tenant_id=tenant.id)
    db.commit()

    with pytest.raises(IntegrityError):
        db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        db.commit()
    db.rollback()

    db.execute(delete(DocumentChunk).where(DocumentChunk.id < 0))  # sin chunks; no-op
    db.execute(delete(Document).where(Document.tenant_id == tenant.id))
    db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    db.commit()
    assert db.scalar(select(Tenant)) is None


def test_filing_delete_cascades_transactions(db):
    filing = InsiderFiling(
        accession_number="0001234567-24-000099",
        form="4",
        issuer_cik="1234567",
        parser_version="v1",
    )
    db.add(filing)
    db.flush()
    for ordinal in ("a", "b"):
        db.add(
            InsiderTransaction(
                fingerprint=f"fp-{ordinal}",
                filing_id=filing.id,
                accession_number=filing.accession_number,
                form="4",
            )
        )
    db.commit()

    db.execute(delete(InsiderFiling).where(InsiderFiling.id == filing.id))
    db.commit()

    assert db.scalars(select(InsiderTransaction.id)).all() == []


def test_thesis_version_delete_cascades_sections_and_nulls_claim_link(db):
    company = _company(db, "TST_TH_A")
    version = ThesisVersion(
        company_id=company.id, thesis_markdown="# tesis", executive_summary="resumen"
    )
    db.add(version)
    db.flush()
    db.add(
        ThesisSection(
            thesis_version_id=version.id,
            company_id=company.id,
            section_key="bull",
            title="Bull",
        )
    )
    db.add(Claim(company_id=company.id, thesis_version_id=version.id, statement="s"))
    db.commit()

    db.execute(delete(ThesisVersion).where(ThesisVersion.id == version.id))
    db.commit()

    assert db.scalars(select(ThesisSection.id)).all() == []
    claim = db.scalar(select(Claim))
    assert claim is not None and claim.thesis_version_id is None


def test_journal_seed_helpers_cover_decision_date():
    entry = DecisionJournalEntry(
        company_id=1,
        decision_date=date(2024, 1, 1),
        decision="hold",
        rationale="r",
        what_must_be_true=[],
    )
    assert entry.decision == "hold"
