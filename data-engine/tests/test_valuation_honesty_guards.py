"""Valuation honesty guards in LongTermModelService.

A Gordon-growth DCF with WACC <= terminal growth produces a crash or a
negative/nonsense terminal value - it must be skipped with an explicit note,
never shown as a valuation. A reverse DCF without net-debt data must report
insufficient_data, never silently assume the company is debt-free.
"""

from decimal import Decimal

from app.models.entities import FinancialFact
from app.services.long_term_model_service import Assumption, LongTermModelService


def _assumption(value):
    return Assumption(
        value=value, unit="decimal", source_type="model_policy",
        basis="test", source_fact_ids=[], confidence=0.8,
    )


def _fact(metric, year, value):
    return FinancialFact(
        company_id=1, metric=metric, value=Decimal(str(value)),
        unit="USD", period=f"FY{year}", fiscal_year=year, source_type="seed",
    )


def _forecast_point(year, revenue, fcf, shares=100.0):
    return {
        "year": year,
        "revenue": revenue,
        "fcf_margin": fcf / revenue,
        "free_cash_flow": fcf,
        "shares_diluted": shares,
        "evidence": {
            "revenue": {"calculation": "prior revenue * (1 + scenario revenue growth)", "source_fact_ids": []},
            "free_cash_flow": {"source_fact_ids": []},
        },
    }


def _spec(wacc, terminal):
    return {
        "probability": 0.5, "probability_basis": {},
        "growth": 0.05, "fcf_margin": 0.2,
        "wacc": wacc, "terminal_growth": terminal,
        "drivers": [],
    }


ASSUMPTIONS = {
    "revenue_growth": _assumption(0.05),
    "fcf_margin": _assumption(0.2),
    "wacc": _assumption(0.09),
    "terminal_growth": _assumption(0.02),
}

FACT_CACHE = {
    "revenue": [_fact("revenue", 2025, 1000)],
    "net_debt": [_fact("net_debt", 2025, 200)],
    "free_cash_flow": [_fact("free_cash_flow", 2025, 200)],
    "operating_cash_flow": [_fact("operating_cash_flow", 2025, 250)],
    "capital_expenditure": [_fact("capital_expenditure", 2025, -50)],
}


def test_dcf_skipped_when_wacc_not_above_terminal_growth():
    service = LongTermModelService()
    payload = service._scenario_payload(
        name="base",
        spec=_spec(wacc=0.02, terminal=0.025),
        forecast=[_forecast_point(2026, 1050, 210)],
        assumptions=ASSUMPTIONS,
        fact_cache=FACT_CACHE,
        latest_year=2025,
    )
    assert payload["valuation"] is None
    assert "WACC must exceed terminal growth" in payload["valuation_note"]


def test_dcf_computed_when_wacc_above_terminal_growth():
    service = LongTermModelService()
    payload = service._scenario_payload(
        name="base",
        spec=_spec(wacc=0.09, terminal=0.02),
        forecast=[_forecast_point(2026, 1050, 210)],
        assumptions=ASSUMPTIONS,
        fact_cache=FACT_CACHE,
        latest_year=2025,
    )
    assert payload["valuation"] is not None
    assert payload["valuation_note"] is None
    assert payload["valuation"]["trace"]["terminal_value"] > 0


def test_reverse_dcf_refuses_missing_net_debt():
    service = LongTermModelService()
    cache = {
        "revenue": [_fact("revenue", 2025, 1000)],
        "shares_diluted": [_fact("shares_diluted", 2025, 100)],
        "net_debt": [],  # no data: must NOT be treated as debt-free
    }
    result = service._reverse_dcf(
        current_price=50.0,
        assumptions=ASSUMPTIONS,
        fact_cache=cache,
        horizon=5,
        source_year=2025,
    )
    assert result["status"] == "insufficient_data"
    assert "net_debt" in result["missing_inputs"]


def test_reverse_dcf_solves_with_net_debt_present():
    service = LongTermModelService()
    cache = {
        "revenue": [_fact("revenue", 2025, 1000)],
        "shares_diluted": [_fact("shares_diluted", 2025, 100)],
        "net_debt": [_fact("net_debt", 2025, 200)],
    }
    result = service._reverse_dcf(
        current_price=50.0,
        assumptions=ASSUMPTIONS,
        fact_cache=cache,
        horizon=5,
        source_year=2025,
    )
    assert result["status"] == "ok"
    assert "required_revenue_growth" in result
