"""C2: los motores de bancos/aseguradoras/REITs no mezclan ejercicios.

Un ``book_per_share`` con tangible book de FY2024 y acciones de FY2025 (tras una
recpra) no es un dato: es un cociente entre dos fechas. Y un P/B justificado con
el ROE de un año aplicado al libro de otro mete un flujo de retorno sobre un stock
que ese retorno no midió. Antes cada motor resolvía sus entradas por separado con
"la fila más reciente entre todos los alias", así que el resultado salía
``status="ok"``, ``publishable=True`` y ``missing_inputs=[]`` sin ninguna señal.

Ahora el motor ancla el snapshot al balance y declara ausente todo lo que sólo
existe en otro ejercicio. ``g`` ausente también se declara: un 0.0 supuesto
mueve el P/B de forma material (ROE 14% / CoE 10% → 1,40 con g=0 frente a 1,80
con g=5%).
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.core.database import SessionLocal, init_db
from app.models import Company, FinancialFact
from app.services.valuation_service import ValuationService

# (metric, value, fiscal_year[, fiscal_quarter])
BANK_BASE = [
    ("tangible_book_value", 80000, 2024),
    ("shares_diluted", 900, 2024),
    ("roe", 0.12, 2024),
    ("cost_of_equity", 0.11, 2024),
    ("book_value_growth", 0.0, 2024),
]
INSURER_BASE = [
    ("book_value", 1200, 2024),
    ("shares_diluted", 100, 2024),
    ("roe", 0.13, 2024),
    ("cost_of_equity", 0.10, 2024),
    ("combined_ratio", 0.95, 2024),
    ("book_value_growth", 0.03, 2024),
]
REIT_BASE = [
    ("net_operating_income", 100, 2024),
    ("cap_rate", 0.05, 2024),
    ("net_debt", 600, 2024),
    ("shares_diluted", 100, 2024),
]


@contextmanager
def _valued(db, ticker, *, company_type, valuation_model, facts):
    """Siembra la empresa, la valúa con el servicio y limpia al salir."""
    existing = db.scalar(select(Company).where(Company.ticker == ticker))
    if existing:
        db.execute(delete(FinancialFact).where(FinancialFact.company_id == existing.id))
        db.delete(existing)
        db.commit()
    company = Company(
        ticker=ticker,
        name=f"anchor {ticker}",
        exchange="TEST",
        currency="USD",
        sector="Financials" if company_type != "reit" else "Real Estate",
        industry="Test",
        company_type=company_type,
        valuation_model=valuation_model,
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.flush()
    for row in facts:
        metric, value, fiscal_year = row[0], row[1], row[2]
        quarter = row[3] if len(row) > 3 else "FY"
        db.add(
            FinancialFact(
                company_id=company.id,
                metric=metric,
                value=Decimal(str(value)),
                unit="decimal" if abs(value) < 1 else "USD",
                period=f"FY{fiscal_year}" if quarter == "FY" else f"FY{fiscal_year}{quarter}",
                fiscal_year=fiscal_year,
                fiscal_quarter=quarter,
                source_type="sector_anchor_test",
                is_reported=True,
                confidence=Decimal("0.92"),
            )
        )
    db.commit()
    try:
        yield ValuationService().value_company(db, company)
    finally:
        db.execute(delete(FinancialFact).where(FinancialFact.company_id == company.id))
        db.execute(delete(Company).where(Company.id == company.id))
        db.commit()


def _bank(db, ticker, facts):
    return _valued(
        db,
        ticker,
        company_type="bank",
        valuation_model="bank_residual_income",
        facts=facts,
    )


def _insurer(db, ticker, facts):
    return _valued(
        db,
        ticker,
        company_type="insurer",
        valuation_model="insurance_book_value",
        facts=facts,
    )


def _reit(db, ticker, facts):
    return _valued(
        db,
        ticker,
        company_type="reit",
        valuation_model="reit_nav",
        facts=facts,
    )


def test_bank_book_fy2024_with_shares_fy2025_is_refused_not_mixed():
    """El escenario del hallazgo: 10% de recompra, BVPS mezclado = 80 vs 88,9 real."""
    init_db()
    db = SessionLocal()
    try:
        facts = [
            ("tangible_book_value", 80000, 2024),
            ("shares_diluted", 1000, 2025),  # el banco recompró y amortizó acciones
            ("roe", 0.12, 2024),
            ("cost_of_equity", 0.11, 2024),
            ("book_value_growth", 0.0, 2024),
        ]
        with _bank(db, "C2SHARE", facts) as result:
            assert result["status"] == "insufficient_data"
            assert result["publishable"] is False
            assert result["missing_inputs"] == ["shares_diluted"]
            assert result["base_value"] is None
            assert result["bear_value"] is None and result["bull_value"] is None
            # Nada del cociente_crossed (80000/1000 = 80) llega a publicarse.
            assert "assumptions" not in result["trace"]
            anchor = result["trace"]["period_anchor"]
            assert anchor["metric"] == "tangible_book_value"
            assert anchor["fiscal_year"] == 2024
            excluded = result["trace"]["inputs_excluded_out_of_anchor_period"]
            assert [item["fiscal_year"] for item in excluded["shares_diluted"]] == [2025]
    finally:
        db.close()


def test_bank_uses_the_share_count_of_the_balance_sheet_year_when_both_exist():
    init_db()
    db = SessionLocal()
    try:
        facts = BANK_BASE + [("shares_diluted", 1000, 2025)]
        with _bank(db, "C2BOTH", facts) as result:
            assert result["status"] == "ok"
            assert result["publishable"] is True
            # BVPS del ancla 80000/900 = 88,89 y P/B (0,12-0)/(0,11-0) = 1,0909.
            assert result["trace"]["assumptions"]["book_per_share"] == pytest.approx(80000 / 900)
            assert result["base_value"] == pytest.approx((80000 / 900) * (0.12 / 0.11))
            # El valor mezclado (80 × 1,0909 = 87,27) es exactamente el bug.
            assert result["base_value"] != pytest.approx(87.27, abs=0.05)
            assert result["trace"]["periods"]["shares_diluted"] == "FY2024"
    finally:
        db.close()


def test_bank_roe_alias_from_another_year_is_not_applied_to_the_book():
    """``roe`` de FY2023 y ``return_on_tangible_equity`` de FY2025: manda el ancla."""
    init_db()
    db = SessionLocal()
    try:
        facts = [
            ("tangible_book_value", 80000, 2023),
            ("shares_diluted", 900, 2023),
            ("roe", 0.08, 2023),
            ("return_on_tangible_equity", 0.20, 2025),
            ("cost_of_equity", 0.11, 2023),
            ("book_value_growth", 0.02, 2023),
        ]
        with _bank(db, "C2ROEALIAS", facts) as result:
            assert result["status"] == "ok"
            assert result["trace"]["periods"]["roe"] == "FY2023"
            # ROE 8% del ancla, no el 20% de FY2025: 88,89 × (0,08-0,02)/(0,11-0,02).
            assert result["base_value"] == pytest.approx((80000 / 900) * (0.06 / 0.09))
            assert result["base_value"] < (80000 / 900) * 2.0
    finally:
        db.close()


def test_bank_roe_only_from_another_year_is_declared_missing():
    init_db()
    db = SessionLocal()
    try:
        facts = [
            ("tangible_book_value", 80000, 2024),
            ("shares_diluted", 900, 2024),
            ("roe", 0.12, 2023),
            ("cost_of_equity", 0.11, 2024),
            ("book_value_growth", 0.0, 2024),
        ]
        with _bank(db, "C2ROEMISS", facts) as result:
            assert result["status"] == "insufficient_data"
            assert result["publishable"] is False
            assert result["missing_inputs"] == ["roe"]
            assert result["base_value"] is None
            excluded = result["trace"]["inputs_excluded_out_of_anchor_period"]
            assert [item["fiscal_year"] for item in excluded["roe"]] == [2023]
    finally:
        db.close()


def test_bank_quarterly_shares_are_not_mixed_with_an_annual_book():
    """Un contador de acciones a nueve meses tampoco es el del balance anual."""
    init_db()
    db = SessionLocal()
    try:
        facts = [
            ("tangible_book_value", 80000, 2024),
            ("shares_diluted", 905, 2024, "Q3"),
            ("roe", 0.12, 2024),
            ("cost_of_equity", 0.11, 2024),
            ("book_value_growth", 0.0, 2024),
        ]
        with _bank(db, "C2QUARTER", facts) as result:
            assert result["status"] == "insufficient_data"
            assert result["missing_inputs"] == ["shares_diluted"]
            excluded = result["trace"]["inputs_excluded_out_of_anchor_period"]
            assert [item["fiscal_quarter"] for item in excluded["shares_diluted"]] == ["Q3"]
    finally:
        db.close()


def test_bank_all_facts_in_the_same_year_keeps_the_good_case():
    init_db()
    db = SessionLocal()
    try:
        with _bank(db, "C2GOOD", BANK_BASE) as result:
            assert result["status"] == "ok"
            assert result["publishable"] is True
            assert result["base_value"] == pytest.approx((80000 / 900) * (0.12 / 0.11))
            assert result["bear_value"] <= result["base_value"] <= result["bull_value"]
            assert result["trace"]["engine"] == "bank"
            assert result["trace"]["period_anchor_policy"] == "statement_metrics_share_one_fiscal_period"
            assert result["trace"]["period_anchor"]["fiscal_year"] == 2024
            assert set(result["trace"]["periods"].values()) == {"FY2024"}
            assert result["trace"]["assumptions"]["growth_source"] == "financial_facts"
            assert result["sensitivity"]["rows"]
    finally:
        db.close()


def test_bank_missing_book_value_growth_is_declared_instead_of_a_zero():
    init_db()
    db = SessionLocal()
    try:
        facts = [row for row in BANK_BASE if row[0] != "book_value_growth"]
        with _bank(db, "C2NOGROWTH", facts) as result:
            assert result["status"] == "insufficient_data"
            assert result["publishable"] is False
            assert result["missing_inputs"] == ["book_value_growth"]
            assert result["base_value"] is None
            # El g=0 silencioso ("explicit_zero_growth_policy") ya no existe.
            assert "explicit_zero_growth_policy" not in json.dumps(result)
    finally:
        db.close()


def test_bank_book_value_growth_from_another_year_is_declared_missing():
    init_db()
    db = SessionLocal()
    try:
        facts = [row for row in BANK_BASE if row[0] != "book_value_growth"] + [
            ("book_value_growth", 0.04, 2023),
        ]
        with _bank(db, "C2GROWTHYR", facts) as result:
            assert result["status"] == "insufficient_data"
            assert result["missing_inputs"] == ["book_value_growth"]
            excluded = result["trace"]["inputs_excluded_out_of_anchor_period"]
            assert [item["fiscal_year"] for item in excluded["book_value_growth"]] == [2023]
    finally:
        db.close()


def test_bank_cost_of_equity_is_a_market_rate_not_anchored_to_the_book():
    """El CoE no es un stock ni un flujo: se usa el último y su periodo se expone."""
    init_db()
    db = SessionLocal()
    try:
        facts = [row for row in BANK_BASE if row[0] != "cost_of_equity"] + [
            ("cost_of_equity", 0.11, 2023),
        ]
        with _bank(db, "C2COE", facts) as result:
            assert result["status"] == "ok"
            assert result["trace"]["periods"]["cost_of_equity"] == "FY2023"
            rates = result["trace"]["market_rates_not_period_anchored"]
            assert rates["cost_of_equity"]["fiscal_year"] == 2023
            assert result["trace"]["period_anchor"]["fiscal_year"] == 2024
    finally:
        db.close()


def test_insurer_book_and_combined_ratio_from_different_years_is_refused():
    init_db()
    db = SessionLocal()
    try:
        facts = [row for row in INSURER_BASE if row[0] != "combined_ratio"] + [
            ("combined_ratio", 0.99, 2025)
        ]
        with _insurer(db, "C2INSCOMB", facts) as result:
            assert result["status"] == "insufficient_data"
            assert result["missing_inputs"] == ["combined_ratio"]
            assert result["base_value"] is None
            assert result["trace"]["period_anchor"]["fiscal_year"] == 2024
    finally:
        db.close()


def test_insurer_same_year_valuation_keeps_the_documented_math():
    init_db()
    db = SessionLocal()
    try:
        with _insurer(db, "C2INSGOOD", INSURER_BASE) as result:
            assert result["status"] == "ok"
            justified_pb = (0.13 - 0.03) / (0.10 - 0.03)
            underwriting = 1 + (1 - 0.95) * 2
            assert result["base_value"] == pytest.approx(12.0 * justified_pb * underwriting)
            assert set(result["trace"]["periods"].values()) == {"FY2024"}
            assert result["trace"]["period_anchor"]["metric"] == "book_value"
    finally:
        db.close()


def test_reit_net_debt_from_another_year_is_not_netted_against_the_noi():
    init_db()
    db = SessionLocal()
    try:
        facts = [row for row in REIT_BASE if row[0] != "net_debt"] + [("net_debt", 600, 2025)]
        with _reit(db, "C2REITDEBT", facts) as result:
            assert result["status"] == "insufficient_data"
            assert result["missing_inputs"] == ["net_debt"]
            assert result["base_value"] is None
            excluded = result["trace"]["inputs_excluded_out_of_anchor_period"]
            assert [item["fiscal_year"] for item in excluded["net_debt"]] == [2025]
    finally:
        db.close()


def test_reit_same_year_nav_is_unchanged():
    init_db()
    db = SessionLocal()
    try:
        with _reit(db, "C2REITGOOD", REIT_BASE) as result:
            assert result["status"] == "ok"
            assert result["base_value"] == pytest.approx((100 / 0.05 - 600) / 100)
            assert result["trace"]["period_anchor"]["metric"] == "net_operating_income"
            assert result["trace"]["periods"]["cap_rate"] == "FY2024"
            assert result["trace"]["market_rates_not_period_anchored"]["cap_rate"][
                "fiscal_year"
            ] == 2024
    finally:
        db.close()
