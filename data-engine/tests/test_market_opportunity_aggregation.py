"""Contract tests for the market-opportunity engine.

Two defects made the engine contradict itself or treat a broken input as a
constraint:

* the bottom-up value was a flat ``min()`` over formulas regardless of whether
  they were additive revenue lines or independent upper bounds on the SAME
  revenue, so a launcher that sells launch services AND space systems got a
  ceiling equal to the smaller of the two, below the revenue its own driver
  model projects (it sums the same two branches);
* a negative capacity (a sign-flipped source value) won that min(), and the
  verdict then computed ``base_revenue / negative`` <= 0.80 and printed
  "reasonable" next to a -2000% ratio.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Company, FinancialFact
from app.models.entities import Base
from app.services.company_framework import resolve_company_framework
from app.services.market_opportunity_service import MarketOpportunityEngine, _combine_of


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _company(db, ticker, *, company_type="standard", valuation_model="standard_dcf", tags=None):
    row = Company(
        ticker=ticker,
        name=ticker,
        exchange="TEST",
        currency="USD",
        sector="Industrials",
        industry="Aerospace",
        company_type=company_type,
        valuation_model=valuation_model,
        special_sources=[],
        special_risks=[],
        factor_tags=tags or [],
    )
    db.add(row)
    db.flush()
    return row


def _fact(db, company, metric, value, *, year=2024, unit="USD"):
    row = FinancialFact(
        company_id=company.id,
        metric=metric,
        value=Decimal(str(value)),
        unit=unit,
        period=f"{year}-12-31:FY",
        fiscal_year=year,
        fiscal_quarter="FY",
        source_type="SEC",
        is_reported=True,
        is_adjusted=False,
        confidence=Decimal("0.9"),
    )
    db.add(row)
    db.flush()
    return row


def _bottom_up(db, company, metrics):
    engine = MarketOpportunityEngine()
    framework = resolve_company_framework(company)
    cache: dict[str, list[FinancialFact]] = {}
    for metric, value in metrics.items():
        cache[metric] = [_fact(db, company, metric, value)]
    return engine._bottom_up(fact_cache=cache, framework=framework)


def _verdict(top_down_value, bottom_up_value, base_revenue=1_000.0):
    return MarketOpportunityEngine()._verdict(
        top_down={"future_market": {"value": top_down_value}},
        bottom_up={"value": bottom_up_value},
        implied={},
        base_scenario={"terminal_year": {"revenue": base_revenue}},
    )


# --------------------------------------------------------------------------
# additive vs ceiling classification
# --------------------------------------------------------------------------


def _combines(db, ticker, **kwargs):
    company = _company(db, ticker, **kwargs)
    framework = resolve_company_framework(company)
    definitions = MarketOpportunityEngine()._formula_definitions(framework)
    return {d.key: d.combine for d in definitions}


def test_space_defense_lines_are_additive(db):
    """Launch services and space systems are DISTINCT revenue lines."""
    assert _combines(db, "RKLB") == {
        "launch_opportunity": "sum",
        "backlog_conversion": "sum",
    }


def test_platform_lines_are_additive(db):
    """Payments and mobility are DISTINCT revenue lines."""
    assert set(_combines(db, "PYPL").values()) == {"sum"}


def test_space_network_estimates_are_ceilings_on_the_same_revenue(db):
    """Demand-side and supply-side measures of ONE revenue: min is correct."""
    assert set(_combines(db, "ASTS").values()) == {"ceiling"}


def test_software_ai_estimates_are_ceilings_on_the_same_revenue(db):
    """Seats x ARPU and ARR x retention are two measurements of one revenue."""
    assert set(_combines(db, "SOFT1", tags=["software", "ai"]).values()) == {"ceiling"}


def test_combine_of_defaults_to_ceiling_for_unknown_keys():
    assert _combine_of({"key": "nope"}, []) == "ceiling"


# --------------------------------------------------------------------------
# bottom-up aggregation
# --------------------------------------------------------------------------


LAUNCH = {"launches": 20, "price_per_launch": 50_000_000}
BACKLOG = {"backlog": 3_000_000_000, "backlog_conversion": 0.25}


def test_additive_lines_are_summed_not_minimised(db):
    """20 launches x 50M = 1.000M plus 3.000M backlog x 25% = 750M -> 1.750M.

    The flat min() reported a 750M ceiling for a business whose own driver
    model sums the same two branches, so the engine capped itself 57% below its
    own revenue projection and then clipped scenario growth to -3,1%.
    """
    company = _company(db, "RKLB")
    result = _bottom_up(db, company, {**LAUNCH, **BACKLOG})

    assert result["status"] == "ok"
    assert result["additive_total"] == pytest.approx(1_750_000_000.0)
    assert result["value"] == pytest.approx(1_750_000_000.0)
    assert result["binding_basis"] == "sum of the additive revenue lines"
    assert result["rejected_estimates"] == []


def test_one_negative_estimate_leaves_the_survivor_in_the_total(db):
    """A sign-flipped backlog must not become the binding capacity."""
    company = _company(db, "RKLB")
    result = _bottom_up(
        db, company, {**LAUNCH, "backlog": -1000, "backlog_conversion": 0.25}
    )

    assert result["additive_total"] == pytest.approx(1_000_000_000.0)
    assert [r["key"] for r in result["rejected_estimates"]] == ["backlog_conversion"]
    assert result["rejected_estimates"][0]["reason"] == "non_positive_or_non_finite"


def test_ceilings_are_minimised(db):
    """A satellite operator is bounded by whichever of demand or supply binds."""
    company = _company(db, "ASTS")
    result = _bottom_up(
        db,
        company,
        {
            "addressable_subscribers": 1_000_000,
            "penetration": 0.1,
            "monthly_arpu": 10,
            "revenue_share": 1.0,
            "satellites": 100,
            "capacity_per_satellite": 1000,
            "utilization": 0.5,
            "price_per_gb": 1,
        },
    )

    # demand: 1e6 * 0.1 * (10*12) * 1.0 = 12.000.000
    # supply:  100 * 1000 * 0.5 * 1     =      50.000
    assert result["value"] == pytest.approx(50_000.0)
    assert result["additive_total"] is None
    assert result["binding_basis"] == "tightest independent ceiling"


def test_a_single_additive_line_is_still_labelled_as_a_sum(db):
    company = _company(db, "RKLB")
    result = _bottom_up(db, company, LAUNCH)

    assert result["additive_keys"] == ["launch_opportunity"]
    assert result["binding_basis"] == "sum of the additive revenue lines"


# --------------------------------------------------------------------------
# verdict: a broken estimate must never become the binding capacity
# --------------------------------------------------------------------------


def test_negative_estimate_does_not_drive_the_ratio_negative():
    """Before the fix: ratio = 1000 / -45000 = -0,022 <= 0,80 -> "reasonable"."""
    verdict = _verdict(50_000.0, -45_000.0, base_revenue=1_000.0)
    assert verdict["base_revenue_to_binding_capacity"] == pytest.approx(0.02)
    assert verdict["label"] == "reasonable"
    assert "-2000" not in verdict["conclusion"]


def test_unknown_when_the_only_estimate_is_negative():
    verdict = _verdict(None, -45_000.0, base_revenue=1_000.0)
    assert verdict["label"] == "unknown"
    assert "evidencia suficiente" in verdict["conclusion"]


def test_unknown_when_no_evidence_at_all():
    verdict = _verdict(None, None, base_revenue=1_000.0)
    assert verdict["label"] == "unknown"
    assert "evidencia suficiente" in verdict["conclusion"]


def test_reasonable_when_revenue_fits_under_the_binding_capacity():
    verdict = _verdict(50_000.0, 40_000.0, base_revenue=1_000.0)
    assert verdict["label"] == "reasonable"
    assert verdict["base_revenue_to_binding_capacity"] == pytest.approx(0.025)
