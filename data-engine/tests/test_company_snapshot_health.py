"""Salud del snapshot de empresa: la etiqueta debe acompanar al score topado.

Auditoria 2026-09-25 (P2): el score queda topado a 69 cuando hay tesis pero
0 afirmaciones; la etiqueta "healthy" en ese caso era contradictoria. Debe
ser "incomplete".
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import (
    Base,
    CalculatedMetric,
    Claim,
    Company,
    Document,
    FinancialFact,
    FundamentalModelVersion,
    ThesisVersion,
)
from app.services.company_snapshot_service import CompanySnapshotService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session) -> Company:
    company = Company(
        ticker="TEST", name="Test Co", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _complete_without_claims(db: Session, company: Company) -> None:
    """Documento + hecho + tesis + modelo + metrica calculada, pero 0 claims."""
    db.add(Document(company_id=company.id, title="10-K", source_type="sec"))
    db.add(FinancialFact(company_id=company.id, metric="revenue", value=Decimal("100"), period="FY2025"))
    db.add(ThesisVersion(
        company_id=company.id, version=1, status="published",
        thesis_markdown="# T", executive_summary="resumen",
    ))
    db.add(FundamentalModelVersion(
        company_id=company.id, version=1, engine_version="e1", algorithm_version="a1",
        framework_key="growth", horizon_years=5, status="ok",
        input_fingerprint="f" + str(company.id), forecast_fingerprint="ff" + str(company.id),
        market_snapshot_fingerprint="mf" + str(company.id), valuation_snapshot_fingerprint="vf" + str(company.id),
    ))
    db.add(CalculatedMetric(company_id=company.id, metric="growth", value=Decimal("0.1"), period="FY2025", formula="x"))
    db.commit()


def test_capped_health_without_claims_is_incomplete(db: Session):
    company = _company(db)
    _complete_without_claims(db, company)
    snapshot = CompanySnapshotService().build(db, company)
    assert snapshot.research_health.score == 69  # topado: sin afirmaciones no hay notable
    assert snapshot.research_health.status == "incomplete"  # la etiqueta acompaña al tope


def test_complete_health_with_claims_is_healthy(db: Session):
    company = _company(db)
    _complete_without_claims(db, company)
    db.add(Claim(company_id=company.id, statement="crece", status="verified"))
    db.commit()
    snapshot = CompanySnapshotService().build(db, company)
    assert snapshot.research_health.score == 100
    assert snapshot.research_health.status == "healthy"
