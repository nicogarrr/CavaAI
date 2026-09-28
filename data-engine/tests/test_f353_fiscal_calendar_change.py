"""F353: _modal_fiscal_end_month computaba la moda del mes de cierre sobre
TODA la historia (todos los metrics x todos los anos). Emisores que cambian
de calendario fiscal quedaban congelados en el ano del cambio: la historia
vieja ganaba la moda y el filtro anual rechazaba los ejercicios nuevos.
Casos reales (28/09/2026, backfill tenant 2): BRT Sep->Dec, ZWS Mar->Dec,
CSR Abr->Dec, JEF Dic->Nov, CMP/FOR Dic->Sep, EYPT/MYGN/LHX Jun->Dic,
VFC Dic->Mar/Abr (52/53 semanas).

Fix: moda sobre la ventana reciente (~5 anos) con mes normalizado (cierres
en los primeros 7 dias del mes = mes anterior), historia solo como desempate.
La proteccion anti-TTM de F28 sigue vigente (regresion AA/AAL incluida).
"""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Company, FinancialFact
from app.services import financial_ingestion_service as ingestion
from app.services.financial_ingestion_service import (
    FinancialIngestionService,
    _modal_fiscal_end_month,
    _normalized_fiscal_month,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db, ticker):
    company = Company(
        ticker=ticker, name=ticker, exchange="NYSE", currency="USD",
        sector="S", industry="I", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _fy(start, end, val, filed, form="10-K"):
    return {"fy": int(end[:4]), "fp": "FY", "form": form, "start": start,
            "end": end, "val": val, "filed": filed}


def _years(start_year, end_year, start_md, end_md, base_val):
    """Serie anual start_year..end_year con cierre end_md (m-d)."""
    out = []
    for y in range(start_year, end_year + 1):
        out.append(_fy(f"{y - 1}-{start_md}", f"{y}-{end_md}", base_val + y, f"{y + 1}-02-01"))
    return out


def _years_cal(start_year, end_year, base_val):
    """Serie anual de ano natural: FY2023 = 2023-01-01 -> 2023-12-31."""
    out = []
    for y in range(start_year, end_year + 1):
        out.append(_fy(f"{y}-01-01", f"{y}-12-31", base_val + y, f"{y + 1}-02-01"))
    return out


class _FakeSEC:
    facts = None

    async def cik_for_ticker(self, ticker):
        return "0000000000"

    async def company_facts(self, cik):
        return self.facts


def _ingest(db, ticker, facts):
    cls = type("FakeSECInstance", (_FakeSEC,), {"facts": facts})
    monkey = cls()
    ingestion.SECClient = lambda *a, **k: monkey
    company = _company(db, ticker)
    asyncio.run(FinancialIngestionService().refresh_from_sec(db=db, company=company))
    return company


def _fy_revenues(db, company):
    rows = db.scalars(select(FinancialFact).where(
        FinancialFact.company_id == company.id,
        FinancialFact.metric == "revenue",
        FinancialFact.fiscal_quarter == "FY",
    ).order_by(FinancialFact.period.desc())).all()
    return {r.period: r.value for r in rows}


def test_zws_cambio_marzo_a_diciembre(db):
    """ZWS: historia Mar (spinoff, hasta 2020-03-31), calendario actual Dic.
    Antes del fix la moda historica (03) rechazaba los FY2022/2023 de dic."""
    rev = {"units": {"USD":
        _years(2017, 2020, "04-01", "03-31", 1_800_000_000)
        + _years_cal(2021, 2023, 1_200_000_000)}}
    company = _ingest(db, "ZWS", {"facts": {"us-gaap": {"Revenues": rev}}})
    periods = _fy_revenues(db, company)
    assert periods["2023-12-31:FY"] == Decimal(str(1_200_000_000 + 2023))
    assert periods["2020-03-31:FY"] == Decimal(str(1_800_000_000 + 2020))
    assert max(periods) == "2023-12-31:FY"


def test_csr_cambio_abril_a_diciembre(db):
    """CSR: historia Abr (hasta 2018-04-30), actual Dic. La moda historica
    (04) ganaba 14 vs 19 al contar todos los metrics y rechazaba dic."""
    rev = {"units": {"USD":
        _years(2012, 2018, "05-01", "04-30", 80_000_000)
        + _years_cal(2019, 2025, 200_000_000)}}
    company = _ingest(db, "CSR", {"facts": {"us-gaap": {"Revenues": rev}}})
    periods = _fy_revenues(db, company)
    assert periods["2025-12-31:FY"] == Decimal(str(200_000_000 + 2025))
    assert max(periods) == "2025-12-31:FY"


def test_jef_cambio_diciembre_a_noviembre(db):
    """JEF: historia Dic, actual Nov (Jefferies movio el cierre a 30-nov)."""
    rev = {"units": {"USD":
        _years_cal(2013, 2019, 10_000_000_000)
        + _years(2020, 2025, "12-01", "11-30", 5_000_000_000)}}
    company = _ingest(db, "JEF", {"facts": {"us-gaap": {"Revenues": rev}}})
    periods = _fy_revenues(db, company)
    assert periods["2025-11-30:FY"] == Decimal(str(5_000_000_000 + 2025))
    assert max(periods) == "2025-11-30:FY"


def test_vfc_52_53_semanas_cruzando_cambio_de_mes(db):
    """VFC: cierres el sabado mas cercano al 31 de marzo: 2023-04-01,
    2024-03-30, 2025-03-29. Sin normalizar, el drift 03/04 parte la moda."""
    rev = {"units": {"USD": [
        _fy("2022-04-03", "2023-04-01", 11_000_000_000, "2023-05-18"),
        _fy("2023-04-02", "2024-03-30", 10_500_000_000, "2024-05-23"),
        _fy("2024-03-31", "2025-03-29", 10_000_000_000, "2025-05-22"),
    ]}}
    company = _ingest(db, "VFC", {"facts": {"us-gaap": {"Revenues": rev}}})
    periods = _fy_revenues(db, company)
    assert len(periods) == 3
    assert periods["2025-03-29:FY"] == Decimal("10000000000")


def test_regresion_aa_ttm_sigue_rechazado(db):
    """F28 sigue vigente: acumulados TTM de ~365 dias que cierran en fin de
    trimestre (caso real AA/AAL) NO entran como ejercicio anual: el ejercicio
    real de diciembre gana la moda en la ventana reciente."""
    rev = {"units": {"USD":
        _years_cal(2018, 2021, 100)
        + [
            _fy("2019-04-01", "2020-03-31", 999, "2021-02-12"),
            _fy("2019-07-01", "2020-06-30", 998, "2021-02-12"),
            _fy("2019-10-01", "2020-09-30", 997, "2021-02-12"),
        ]}}
    company = _ingest(db, "AA", {"facts": {"us-gaap": {"Revenues": rev}}})
    periods = _fy_revenues(db, company)
    assert periods["2021-12-31:FY"] == Decimal(str(100 + 2021))
    assert "2020-03-31:FY" not in periods
    assert "2020-06-30:FY" not in periods
    assert "2020-09-30:FY" not in periods


def test_normalizacion_primeros_7_dias():
    assert _normalized_fiscal_month("2023-04-01") == "03"
    assert _normalized_fiscal_month("2025-03-29") == "03"
    assert _normalized_fiscal_month("2025-01-03") == "12"
    assert _normalized_fiscal_month("2024-12-31") == "12"
    assert _normalized_fiscal_month("2024-09-28") == "09"
    assert _normalized_fiscal_month("2024-09-07") == "08"
    assert _normalized_fiscal_month("basura") is None


def test_moda_ventana_reciente_adopta_calendario_nuevo():
    us_gaap = {"Revenues": {"units": {"USD":
        _years(2010, 2018, "04-01", "03-31", 1)
        + _years_cal(2019, 2023, 2)}}}
    assert _modal_fiscal_end_month(us_gaap) == "12"


def test_moda_sin_cambio_de_calendario_estable():
    us_gaap = {"Revenues": {"units": {"USD": _years(2010, 2023, "10-01", "09-28", 1)}}}
    assert _modal_fiscal_end_month(us_gaap) == "09"


def test_moda_sin_candidatos_devuelve_none():
    assert _modal_fiscal_end_month({"Revenues": {"units": {"USD": []}}}) is None
    assert _modal_fiscal_end_month({}) is None
