"""El WACC no rellena con ceros ni con basura los inputs que le faltan.

Dos bugs de dinero, los dos con el mismo efecto: un WACC persisted con
``status="ok"`` que `traceable_wacc` (app/valuation/engines/base.py) acepta y
que el DCF prefiere sobre su default por tags, de modo que la tasa de
descuento de toda la valoracion era un numero que nadie sourced.

1. Prima de riesgo pais ausente tratada como ``Decimal("0")`` duro. Con rf
   4,5%, beta 1,2 y ERP 5,5% el coste de equity salia 11,1% para una
   compania en Argentina, donde la CRP real son ~+10pp: unos ~21%. Como el
   DCF escala con 1/(WACC-g), ese -10pp multiplicaba el valor por accion.
2. Beta sin gate de plausibilidad. Un proveedor que devuelve beta 0,15 (o un
   fact con la escala mal parseada, beta 5) baja el WACC a 3,9% con De/E 1:1
   y deja el spread sobre g=2,5% en 1,4pp: el PV del valor terminal se
   multiplica por ~3,4 con la valoracion marcada publicable.

Regla que fijan estos tests: un input ausente o no creible se DECLARA ausente.
No se sustituye por 0, no se recorta al extremo mas cercano y no se calcula
igualmente "como si fuera 0".
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Base,
    CalculatedMetric,
    Company,
    FinancialFact,
)
from app.services.metric_calculation_service import (
    BETA_PLAUSIBLE_RANGE,
    MetricCalculationService,
)
from app.valuation.engines.base import ValuationContext, traceable_wacc
from app.valuation.engines.standard_dcf import StandardDCFEngine
from app.valuation.financial_snapshot import FinancialSnapshotBuilder

PERIOD = "2025-12-31"
FY = 2025


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _company(db: Session, ticker: str = "WCACCHON") -> Company:
    company = Company(
        ticker=ticker,
        name="WACC Missing Inputs Co",
        exchange="TEST",
        currency="USD",
        sector="Software",
        industry="Application Software",
        company_type="standard",
        valuation_model="standard_dcf",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def _fact(
    company: Company,
    metric: str,
    value: str,
    *,
    period: str = PERIOD,
    fiscal_year: int | None = FY,
    source_type: str = "wacc_test",
    unit: str = "USD",
) -> FinancialFact:
    return FinancialFact(
        company_id=company.id,
        metric=metric,
        value=Decimal(value),
        unit=unit,
        period=period,
        fiscal_year=fiscal_year,
        fiscal_quarter="FY",
        source_type=source_type,
        is_reported=True,
        confidence=Decimal("0.90"),
    )


def _full_wacc_inputs(
    db: Session,
    company: Company,
    *,
    beta: str = "1.2",
    country_risk_premium: str | None = "0.10",
) -> dict[str, FinancialFact]:
    """Todos los inputs del WACC salvo el que el test quiere dejar fuera.

    market_cap y total_debt vienen de fuentes absolutas con la misma unidad
    para que el guard de escala de importes los declare comparables; sin eso
    el WACC quedaria unavailable por otro motivo y el test no probaria nada.
    """
    values = {
        "risk_free_rate": "0.045",
        "beta": beta,
        "equity_risk_premium": "0.055",
        "total_debt": "1000",
        "interest_expense": "40",
        "effective_tax_rate": "0.25",
        "market_cap": "1000",
    }
    if country_risk_premium is not None:
        values["country_risk_premium"] = country_risk_premium
    facts: dict[str, FinancialFact] = {}
    for metric, value in values.items():
        source = (
            "yfinance"
            if metric == "market_cap"
            else "SEC"
            if metric == "total_debt"
            else "wacc_test"
        )
        facts[metric] = _fact(company, metric, value, source_type=source)
        db.add(facts[metric])
    db.commit()
    return facts


def _gated(trace: dict, name: str) -> dict:
    entries = [item for item in trace.get("gated_inputs") or [] if item["input"] == name]
    assert len(entries) == 1, f"expected exactly one gated entry for {name}: {entries}"
    return entries[0]


def _wacc(db: Session, company: Company, persist: bool = False):
    return MetricCalculationService().calculate(db, company, "wacc", persist=persist)


# --------------------------------------------------------------------------
# (a) Prima de riesgo pais ausente nunca es 0
# --------------------------------------------------------------------------


def test_absent_country_risk_premium_is_declared_and_never_zeroed(db):
    db_company = _company(db)
    _full_wacc_inputs(db, db_company, country_risk_premium=None)

    result = _wacc(db, db_company)
    trace = result.calculation_trace

    # Sin CRP no hay WACC: `unavailable`, no "ok" con un 0 por dentro.
    assert result.status == "unavailable"
    assert result.value is None
    assert result.calculation_trace["reason"] == "missing_or_incoherent_inputs"
    assert "country_risk_premium" in trace["missing_inputs"]
    # El input ausente no se presenta como disponible.
    assert "country_risk_premium" not in trace["available_inputs"]

    gated = _gated(trace, "country_risk_premium")
    assert gated["reason"] == "absent_never_defaulted_to_zero"
    assert gated["resolution"] == "treated_as_absent"
    # El motivo es legible, no un codigo opaco.
    assert "0 implicito" in gated["detail"]
    assert "riesgo pais" in gated["detail"]


def test_absent_country_risk_premium_never_persists_an_ok_wacc(db):
    """Lo que `traceable_wacc` lee: sin fila `ok`, el DCF no adopta la tasa."""
    db_company = _company(db)
    _full_wacc_inputs(db, db_company, country_risk_premium=None)

    result = _wacc(db, db_company, persist=True)
    db.commit()

    assert result.status == "unavailable"
    rows = db.scalars(
        select(CalculatedMetric).where(
            CalculatedMetric.company_id == db_company.id,
            CalculatedMetric.metric == "wacc",
        )
    ).all()
    assert rows, "the refusal must be persisted, not silently skipped"
    assert all(row.status != "ok" for row in rows)
    assert all(row.value is None for row in rows)
    # Y por lo tanto el motor de valoracion no lo encuentra trazable.
    assert traceable_wacc(db, db_company) is None


def test_present_country_risk_premium_is_used_and_moves_the_wacc(db):
    """La CRP entra en la formula: mismo company, distinto WACC."""
    without = _company(db, ticker="WCRP0")
    with_crp = _company(db, ticker="WCRPX")

    # CRP 0 explicito y SOURCED (politica para un mercado developed): es un
    # hecho declarado, no el default silencioso del codigo.
    _full_wacc_inputs(db, without, country_risk_premium="0")
    _full_wacc_inputs(db, with_crp, country_risk_premium="0.10")

    zero = _wacc(db, without)
    emerging = _wacc(db, with_crp)

    assert zero.status == "ok" and emerging.status == "ok"
    # De/E = 1:1 con Kd 4% (40/1000) y tax 25%, asi que los +10pp de CRP
    # entran multiplicados por el peso de equity, 0,5.
    assert emerging.value - zero.value == Decimal("0.05000000")
    assert Decimal(emerging.calculation_trace["country_risk_premium"]) == Decimal(
        "0.10"
    )
    # Ke = 4,5% + 1,2 x 5,5% + 10% de CRP
    assert Decimal(emerging.calculation_trace["cost_of_equity"]) == Decimal("0.211")
    # Con CRP declarada no hay nada que gatear.
    assert not (emerging.calculation_trace.get("gated_inputs") or [])


def test_invalid_country_risk_premium_is_declared_not_taken_as_zero(db):
    db_company = _company(db)
    _full_wacc_inputs(db, db_company, country_risk_premium="-1")

    result = _wacc(db, db_company)
    trace = result.calculation_trace

    assert result.status == "unavailable"
    assert result.value is None
    assert "valid_country_risk_premium" in trace["missing_inputs"]
    gated = _gated(trace, "country_risk_premium")
    assert gated["reason"] == "invalid_country_risk_premium"
    assert Decimal(gated["value"]) == Decimal("-1")


# --------------------------------------------------------------------------
# (b) Gate de plausibilidad de beta
# --------------------------------------------------------------------------


@pytest.mark.parametrize("beta", ["0.0", "0.15", "5.0", "-0.4"])
def test_implausible_beta_is_treated_as_absent_never_clamped(db, beta):
    """Fuera de [0.2, 3.0] el fact no es una beta de mercado."""
    db_company = _company(db)
    facts = _full_wacc_inputs(db, db_company, beta=beta)

    result = _wacc(db, db_company, persist=True)
    db.commit()
    trace = result.calculation_trace

    assert result.status == "unavailable"
    assert result.value is None
    assert "beta" in trace["missing_inputs"]
    # No se recorta al extremo: el valor declarado sigue siendo el que se
    # rechazo, y el WACC no existe en ningun sitio.
    assert "beta" not in trace["available_inputs"]
    assert facts["beta"].id not in result.source_fact_ids

    gated = _gated(trace, "beta")
    assert gated["reason"] == "beta_outside_plausible_range"
    assert gated["resolution"] == "treated_as_absent"
    assert Decimal(gated["value"]) == Decimal(beta)
    assert traceable_wacc(db, db_company) is None

    rows = db.scalars(
        select(CalculatedMetric).where(
            CalculatedMetric.company_id == db_company.id,
            CalculatedMetric.metric == "wacc",
        )
    ).all()
    assert all(row.status != "ok" and row.value is None for row in rows)


def test_low_beta_never_produces_the_sub_terminal_spread_wacc(db):
    """Regresion del caso del informe: beta 0,15 daba WACC 3,9%.

    Con ese WACC y g=2,5% el spread es 1,4pp y el PV del valor terminal se
    multiplica por ~3,4. Con la beta gateada no hay tasa que pueda
    multiplicar nada.
    """
    db_company = _company(db)
    _full_wacc_inputs(db, db_company, beta="0.15")

    result = _wacc(db, db_company)

    assert result.status == "unavailable"
    assert result.value is None
    traceable = traceable_wacc(db, db_company)
    assert traceable is None


@pytest.mark.parametrize("beta", ["0.2", "0.85", "1.2", "3.0"])
def test_plausible_beta_is_used_in_the_wacc(db, beta):
    db_company = _company(db)
    _full_wacc_inputs(db, db_company, beta=beta)

    result = _wacc(db, db_company)
    trace = result.calculation_trace

    assert result.status == "ok"
    assert Decimal(trace["beta"]) == Decimal(beta)
    # El gate queda declarado en el trace de lo que si se publico.
    assert trace["beta_plausible_range"] == [
        str(BETA_PLAUSIBLE_RANGE[0]),
        str(BETA_PLAUSIBLE_RANGE[1]),
    ]
    assert not (trace.get("gated_inputs") or [])
    # Ke = 4,5% + beta*5,5% + 10% de CRP
    assert Decimal(trace["cost_of_equity"]) == (
        Decimal("0.045") + Decimal(beta) * Decimal("0.055") + Decimal("0.10")
    )


def test_beta_gate_refuses_before_the_formula_sees_the_value(db):
    """El fact rechazado no llega a la formula: ni cost_of_equity ni trace."""
    db_company = _company(db)
    _full_wacc_inputs(db, db_company, beta="5.0")

    trace = _wacc(db, db_company).calculation_trace

    assert "cost_of_equity" not in trace
    assert "equity_weight" not in trace
    assert "beta" not in trace


# --------------------------------------------------------------------------
# El efecto final: el DCF no descuenta con una tasa fabricada
# --------------------------------------------------------------------------


def _valuation_inputs(db: Session, company: Company) -> None:
    for metric, value, unit in (
        ("revenue", "1000000", "USD"),
        ("fcf_margin", "0.10", "decimal"),
        ("revenue_growth", "0.05", "decimal"),
        ("shares_diluted", "100", "shares"),
        ("net_debt", "0", "USD"),
    ):
        db.add(
            _fact(
                company,
                metric,
                value,
                period="2025-12-31",
                source_type="wacc_test",
                unit=unit,
            )
        )
    db.commit()


def _dcf(db: Session, company: Company) -> dict:
    snapshot = FinancialSnapshotBuilder().build(db, company)
    assert snapshot.coherent is True, snapshot.missing_inputs
    return StandardDCFEngine().value(
        ValuationContext(
            db=db,
            company=company,
            snapshot=snapshot,
            current_price=None,
            engine_key="standard_dcf",
        )
    )


def test_dcf_without_country_risk_premium_falls_back_to_the_tag_default(db):
    """Sin WACC trazable el motor usa su default y lo declara bloqueante.

    Antes de este fix la CRP ausente producia un WACC "ok" de 11,1% que el
    motor adoptaba como trazable: la valoracion saldia publicable con una tasa
    de descuento 10pp mas baja que la del pais real.
    """
    db_company = _company(db, ticker="WDCFNC")
    _full_wacc_inputs(db, db_company, country_risk_premium=None)
    _valuation_inputs(db, db_company)

    result = _dcf(db, db_company)

    assert result["status"] in ("ok", "partial")
    assert result["publishable"] is False
    assert "traceable_wacc" in result["publication_blockers"]
    assert result["trace"]["wacc_source"] == "tag_default"


def test_dcf_with_sourced_country_risk_premium_discounts_at_the_stored_rate(db):
    db_company = _company(db, ticker="WDCFYC")
    _full_wacc_inputs(db, db_company, country_risk_premium="0.10")
    _valuation_inputs(db, db_company)

    stored = _wacc(db, db_company, persist=True)
    db.commit()
    assert stored.status == "ok"
    assert traceable_wacc(db, db_company) == pytest.approx(float(stored.value))

    result = _dcf(db, db_company)

    assert result["trace"]["wacc_source"] == "calculated_metric"
    assert "traceable_wacc" not in result["publication_blockers"]


def test_dcf_does_not_adopt_a_wacc_built_on_an_implausible_beta(db):
    db_company = _company(db, ticker="WDCFBM")
    _full_wacc_inputs(db, db_company, beta="0.15")
    _valuation_inputs(db, db_company)

    result = _dcf(db, db_company)

    assert "traceable_wacc" in result["publication_blockers"]
    assert result["trace"]["wacc_source"] == "tag_default"
