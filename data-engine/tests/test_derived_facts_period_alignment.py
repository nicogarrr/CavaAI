"""Anclaje de ejercicio de las derivadas de la via FMP.

Cada par derivado se resuelve DENTRO de un solo fiscal_year: FCF = OCF +
capex, margen = FCF / revenue y deuda neta = deuda - caja. Resolver cada
metrica por separado ("el ultimo de cada una") y luego combinarlas mezclaba
ejercicios: OCF de FY2024 con capex de FY2025, FCF de un ano sobre revenue de
otro, deuda de un ano contra caja del siguiente. La deuda neta asi fabricada
entra en el puente de equity del DCF (EV - net_debt) como valor que no consta
en ningun balance. Cuando al ano le falta uno de los dos componentes, la
derivada NO se persiste: ausente es el estado honesto, no un cero ni un
estimate silencioso.

Tests hermeticos: doble de FMP inyectado por constructor, sin red.
"""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, Document, FinancialFact
from app.services.financial_ingestion_service import FinancialIngestionService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session) -> Company:
    company = Company(
        ticker="ALG", name="Alignment Corp", exchange="NASDAQ", currency="USD",
        sector="Technology", industry="Software", company_type="software_ai",
        valuation_model="standard_dcf", special_sources=[], special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _seed_sec(db: Session, company: Company, by_year: dict[int, dict[str, str]]) -> None:
    """10-K ya ingerido: hechos CRUDOS por ejercicio, que es lo que publica la
    SEC (las derivadas las calcula el propio servicio)."""
    document = Document(
        company_id=company.id,
        title=f"SEC XBRL facts - {company.ticker}",
        source_type="SEC",
        source_url=(
            "https://www.sec.gov/cgi-bin/browse-edgar"
            f"?action=getcompany&ticker={company.ticker}&type=10-K"
        ),
        metadata_={"provider": "SEC", "normalized": True},
    )
    db.add(document)
    db.flush()
    for year, metrics in by_year.items():
        for metric, value in metrics.items():
            db.add(
                FinancialFact(
                    company_id=company.id,
                    metric=metric,
                    value=Decimal(value),
                    unit="USD",
                    period=f"{year}-12-31:FY",
                    fiscal_year=year,
                    fiscal_quarter="FY",
                    source_id=document.id,
                    source_type="SEC",
                    is_reported=True,
                    confidence=Decimal("0.95"),
                )
            )
    db.commit()


def _seed_sec_derived(db: Session, company: Company, metric: str, year: int, value: str) -> None:
    """Derivada que el propio servicio de la SEC ya dejo persistida (no reportada)."""
    document = db.scalar(
        select(Document).where(
            Document.company_id == company.id, Document.source_type == "SEC"
        )
    )
    db.add(
        FinancialFact(
            company_id=company.id,
            metric=metric,
            value=Decimal(value),
            unit="USD",
            period=f"{year}-12-31:FY",
            fiscal_year=year,
            fiscal_quarter="FY",
            source_id=document.id,
            source_type="SEC",
            is_reported=False,
            confidence=Decimal("0.85"),
        )
    )
    db.commit()


class FakeFMP:
    """financial-summary de FMP con solo los campos que cada test declara."""

    def __init__(self, *, income=(), balance=(), cash_flow=(), ratios=()):
        self._income = list(income)
        self._balance = list(balance)
        self._cash_flow = list(cash_flow)
        self._ratios = list(ratios)

    async def income_statement(self, ticker: str, limit: int = 10):
        return list(self._income)

    async def balance_sheet(self, ticker: str, limit: int = 10):
        return list(self._balance)

    async def cash_flow(self, ticker: str, limit: int = 10):
        return list(self._cash_flow)

    async def ratios(self, ticker: str, limit: int = 10):
        return list(self._ratios)

    async def company_profile(self, ticker: str):
        return []

    async def quote(self, ticker: str):
        return []


def _refresh(db: Session, company: Company, client: FakeFMP) -> dict:
    return asyncio.run(FinancialIngestionService().refresh_from_fmp(db, company, client=client))


def _derived(db: Session, company: Company, metric: str) -> dict[int, FinancialFact]:
    """Derivadas de `metric` por fiscal_year (las reportadas del proveedor no
    cuentan: lo que se comprueba aqui es lo que el servicio calculo)."""
    return {
        fact.fiscal_year: fact
        for fact in db.scalars(
            select(FinancialFact).where(
                FinancialFact.company_id == company.id,
                FinancialFact.metric == metric,
                FinancialFact.is_reported.is_(False),
            )
        )
    }


def test_ocf_fy2024_con_capex_fy2025_no_persiste_fcf(db):
    """OCF solo de FY2024 y capex solo de FY2025: no hay ningun ano con los dos
    componentes, luego no hay FCF. Antes sumaba 900 + (-400) y lo vendia como
    el FCF de la compañía."""
    company = _company(db)
    _seed_sec(db, company, {2024: {"revenue": "9000", "operating_cash_flow": "900"}})
    client = FakeFMP(
        income=[{"date": "2025-12-31", "calendarYear": "2025", "period": "FY", "revenue": 11_000}],
        cash_flow=[
            {"date": "2025-12-31", "calendarYear": "2025", "period": "FY", "capitalExpenditure": -400}
        ],
    )

    result = _refresh(db, company, client)

    assert result["facts_imported"] > 0
    assert _derived(db, company, "free_cash_flow") == {}
    assert result["latest_periods"]["free_cash_flow"] is None


def test_deuda_fy2024_contra_caja_fy2025_no_persiste_deuda_neta(db):
    """Deuda de FY2024 (2.000) contra caja de FY2025 (1.200) fabricaba 800 de
    deuda neta: 700 de deuda que no estan en ningun balance, y el puente de
    equity del DCF los capitaliza como valor. FY2024 si tiene ambos componentes,
    asi que su deuda neta si es legitima."""
    company = _company(db)
    _seed_sec(
        db,
        company,
        {
            2024: {
                "revenue": "9000",
                "operating_cash_flow": "900",
                "capital_expenditure": "-300",
                "total_debt": "2000",
                "cash_and_equivalents": "500",
            }
        },
    )
    client = FakeFMP(
        balance=[
            {"date": "2025-12-31", "calendarYear": "2025", "period": "FY",
             "cashAndCashEquivalents": 1200}
        ]
    )

    _refresh(db, company, client)

    net_debt = _derived(db, company, "net_debt")
    assert set(net_debt) == {2024}
    assert net_debt[2024].value == Decimal("1500")  # 2000 - 500, no 2000 - 1200


def test_par_del_mismo_ano_se_persiste_con_el_valor_correcto(db):
    """Los dos componentes del mismo ejercicio si se combinan: FCF, margen y
    deuda neta de FY2024, con el periodo de ese mismo ejercicio."""
    company = _company(db)
    _seed_sec(
        db,
        company,
        {
            2024: {
                "revenue": "9000",
                "operating_cash_flow": "900",
                "capital_expenditure": "-300",
                "total_debt": "2000",
                "cash_and_equivalents": "500",
            }
        },
    )
    client = FakeFMP(
        income=[{"date": "2025-12-31", "calendarYear": "2025", "period": "FY", "revenue": 11_000}]
    )

    _refresh(db, company, client)

    fcf = _derived(db, company, "free_cash_flow")
    assert set(fcf) == {2024}
    assert fcf[2024].value == Decimal("600")  # 900 - 300
    assert fcf[2024].period == "2024-12-31:FY"

    margin = _derived(db, company, "fcf_margin")
    assert set(margin) == {2024}
    assert abs(margin[2024].value - Decimal("600") / Decimal("9000")) < Decimal("0.000001")

    net_debt = _derived(db, company, "net_debt")
    assert set(net_debt) == {2024}
    assert net_debt[2024].value == Decimal("1500")


def test_fcf_margin_no_mezcla_ejercicios(db):
    """El caso del informe: FCF de FY2024 (600) sobre revenue de FY2025 (11.000)
    daba 5,45% en vez del 6,67% real, y además atribuido al ano que no lo
    soporta. El margen de FY2025 no existe: no hay FCF de FY2025."""
    company = _company(db)
    _seed_sec(
        db,
        company,
        {2024: {"revenue": "9000", "operating_cash_flow": "900", "capital_expenditure": "-300"}},
    )
    client = FakeFMP(
        income=[{"date": "2025-12-31", "calendarYear": "2025", "period": "FY", "revenue": 11_000}],
        balance=[
            {"date": "2025-12-31", "calendarYear": "2025", "period": "FY",
             "cashAndCashEquivalents": 1200}
        ],
    )

    _refresh(db, company, client)

    margin = _derived(db, company, "fcf_margin")
    assert set(margin) == {2024}
    assert abs(margin[2024].value - Decimal("600") / Decimal("9000")) < Decimal("0.000001")
    assert margin[2024].period == "2024-12-31:FY"
    # 600 / 11.000 = 5,45% era el valor fabricado para FY2025.
    assert not any(abs(value.value - Decimal("600") / Decimal("11000")) < Decimal("0.000001")
                   for value in margin.values())


def test_fcf_publicado_por_fmp_da_un_margen_por_anio(db):
    """Cuando el proveedor publica el FCF, cada ejercicio se mide contra SU
    revenue: el margen sigue existiendo (no se pierde por anclar) y gana uno
    por ano, no solo el ultimo."""
    company = _company(db)
    client = FakeFMP(
        income=[
            {"date": "2025-12-31", "calendarYear": "2025", "period": "FY", "revenue": 11_000},
            {"date": "2024-12-31", "calendarYear": "2024", "period": "FY", "revenue": 9_000},
        ],
        cash_flow=[
            {"date": "2025-12-31", "calendarYear": "2025", "period": "FY", "freeCashFlow": 660},
            {"date": "2024-12-31", "calendarYear": "2024", "period": "FY", "freeCashFlow": 540},
        ],
    )

    _refresh(db, company, client)

    margin = _derived(db, company, "fcf_margin")
    assert set(margin) == {2024, 2025}
    assert abs(margin[2025].value - Decimal("660") / Decimal("11000")) < Decimal("0.000001")
    assert abs(margin[2024].value - Decimal("540") / Decimal("9000")) < Decimal("0.000001")


def test_derivada_ya_persistida_por_la_sec_no_se_duplica(db):
    """La SEC ya derivo el FCF de FY2024: la via FMP no escribe una segunda
    fila del mismo (metrica, ano), que el DCF leeria como otro hecho."""
    company = _company(db)
    _seed_sec(
        db,
        company,
        {2024: {"operating_cash_flow": "900", "capital_expenditure": "-300", "revenue": "9000"}},
    )
    _seed_sec_derived(db, company, "free_cash_flow", 2024, "600")
    client = FakeFMP(
        income=[{"date": "2025-12-31", "calendarYear": "2025", "period": "FY", "revenue": 11_000}]
    )

    _refresh(db, company, client)

    fcf_rows = db.scalars(
        select(FinancialFact).where(
            FinancialFact.company_id == company.id,
            FinancialFact.metric == "free_cash_flow",
        )
    ).all()
    assert len(fcf_rows) == 1
    assert fcf_rows[0].source_type == "SEC"
    assert fcf_rows[0].value == Decimal("600")