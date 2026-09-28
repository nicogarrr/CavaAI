"""GET /api/companies/thesis-tickers: una query DISTINCT, semántica del snapshot.

El índice de /research ordena tesis > cartera > watchlist > resto. Saber
qué empresa tiene tesis NO puede costar un snapshot por empresa (~13
queries agregadas por lote de 50): este endpoint lo resuelve en UNA query
y su criterio (cualquier ThesisVersion de la company, sin filtro de
estado) replica la selección de ``latest_thesis`` del snapshot, así el
bucket de orden y la tarjeta nunca discrepan.
"""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.api.routes.companies import thesis_tickers
from app.models.entities import Base, Company, ThesisVersion
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


def _thesis(db: Session, company: Company, version: int) -> None:
    db.add(ThesisVersion(
        company_id=company.id, version=version, status="published",
        thesis_markdown="# T", executive_summary=f"resumen v{version}",
    ))
    db.commit()


def test_una_query_y_distinct(db: Session):
    con_tesis = _company(db, "TESIS")
    _company(db, "SIN")
    doble = _company(db, "DOBLE")
    _thesis(db, con_tesis, 1)
    _thesis(db, doble, 1)
    _thesis(db, doble, 2)  # dos versiones: el ticker sale UNA vez

    engine = db.get_bind()
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    result = thesis_tickers(db)
    event.remove(engine, "before_cursor_execute", count)

    assert result.tickers == ["DOBLE", "TESIS"]  # ordenados y sin duplicar
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 1  # UNA query, no una por empresa


def test_criterio_identico_al_latest_thesis_del_snapshot(db: Session):
    con_tesis = _company(db, "TESIS")
    sin = _company(db, "SIN")
    _thesis(db, con_tesis, 1)

    tickers = set(thesis_tickers(db).tickers)
    service = CompanySnapshotService()
    assert service.build(db, con_tesis).latest_thesis is not None
    assert service.build(db, sin).latest_thesis is None
    assert tickers == {"TESIS"}
