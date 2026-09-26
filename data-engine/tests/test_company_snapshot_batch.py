"""Snapshot por lote del indice de research: equivalencia con build() y queries acotadas.

El indice pedia un snapshot por empresa (~5 round trips x N). build_many
agrega con window functions + GROUP BY: las queries no crecen con N y el
resultado es IDENTICO al de build() empresa a empresa.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models.entities import (
    Base,
    CalculatedMetric,
    Claim,
    Company,
    Document,
    FinancialFact,
    FundamentalModelVersion,
    ThesisChange,
    ThesisVersion,
    ValuationModel,
)
from app.services.company_snapshot_service import CompanySnapshotService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session, ticker: str) -> Company:
    company = Company(
        ticker=ticker, name=f"{ticker} Co", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _fill(db: Session, company: Company, *, thesis_versions: int, changes: int) -> None:
    db.add(Document(company_id=company.id, title="10-K", source_type="sec"))
    db.add(FinancialFact(company_id=company.id, metric="revenue", value=Decimal("100"), period="FY2025"))
    db.add(Claim(company_id=company.id, statement="crece", status="verified"))
    db.add(CalculatedMetric(company_id=company.id, metric="growth", value=Decimal("0.1"), period="FY2025", formula="x"))
    for version in range(1, thesis_versions + 1):
        db.add(ThesisVersion(
            company_id=company.id, version=version, status="published",
            thesis_markdown="# T", executive_summary=f"resumen v{version}",
        ))
        db.add(FundamentalModelVersion(
            company_id=company.id, version=version, engine_version="e1", algorithm_version="a1",
            framework_key="growth", horizon_years=5, status="ok",
            input_fingerprint=f"f{company.id}-{version}", forecast_fingerprint=f"ff{company.id}-{version}",
            market_snapshot_fingerprint=f"mf{company.id}-{version}", valuation_snapshot_fingerprint=f"vf{company.id}-{version}",
        ))
        db.add(ValuationModel(company_id=company.id, model_type="dcf", version=version, status="ok"))
    for index in range(changes):
        db.add(ThesisChange(company_id=company.id, summary=f"cambio {index}"))
    db.commit()


def _dump(snapshot) -> dict:
    return snapshot.model_dump(mode="json")


def test_build_many_matches_build_company_by_company(db: Session):
    first = _company(db, "AAA")
    second = _company(db, "BBB")
    _fill(db, first, thesis_versions=3, changes=12)
    _fill(db, second, thesis_versions=1, changes=2)

    service = CompanySnapshotService()
    batch = service.build_many(db, [first, second])
    assert set(batch) == {first.id, second.id}
    for company in (first, second):
        assert _dump(batch[company.id]) == _dump(service.build(db, company))
    # La tesis elegida es la ultima version y los cambios quedan capados a 10.
    assert batch[first.id].latest_thesis.version == 3
    assert len(batch[first.id].recent_changes) == 10
    assert len(batch[second.id].recent_changes) == 2


def test_build_many_queries_do_not_grow_with_n(db: Session):
    companies = [_company(db, f"T{i}") for i in range(5)]
    for company in companies:
        _fill(db, company, thesis_versions=1, changes=1)

    engine = db.get_bind()
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def count_statements(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    service = CompanySnapshotService()
    statements.clear()
    service.build_many(db, companies)
    batch_statements = len(statements)

    statements.clear()
    for company in companies:
        service.build(db, company)
    loop_statements = len(statements)

    # El lote agrega: ~13 queries para las 5 empresas, no 5 x N.
    assert batch_statements <= 15
    assert batch_statements < loop_statements


def test_build_many_empty_and_missing_layers(db: Session):
    assert CompanySnapshotService().build_many(db, []) == {}
    empty = _company(db, "EMPTY")
    batch = CompanySnapshotService().build_many(db, [empty])
    snapshot = batch[empty.id]
    assert snapshot.research_health.status == "empty"
    assert snapshot.counts.facts == 0
    assert snapshot.latest_thesis is None


def test_recent_changes_many_returns_deterministic_order(db: Session):
    """Sin ORDER BY externo la subquery con window devolvia orden arbitrario."""
    from datetime import datetime, timedelta

    company = _company(db, "ORD")
    base = datetime(2026, 1, 1, 12, 0, 0)
    for index in range(5):
        db.add(ThesisChange(
            company_id=company.id,
            summary=f"c{index}",
            created_at=base + timedelta(minutes=index),
        ))
    db.commit()

    # El ORDER BY va en la consulta EXTERNA: sin el, la window numera cada
    # particion pero las filas salen en orden arbitrario (Postgres no
    # garantiza el orden de la subquery).
    from sqlalchemy import event

    engine = db.get_bind()
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    service = CompanySnapshotService()
    batch = service.build_many(db, [company])
    changes_queries = [
        s for s in statements
        if "FROM thesis_changes" in s and "row_number()" in s
    ]
    assert len(changes_queries) == 1
    assert changes_queries[0].rstrip().endswith(
        "ORDER BY anon_1.company_id, anon_1.created_at DESC"
    )

    ordered = [change.summary for change in batch[company.id].recent_changes]
    assert ordered == ["c4", "c3", "c2", "c1", "c0"]  # created_at DESC
    assert ordered == [
        change.summary for change in service.build(db, company).recent_changes
    ]
