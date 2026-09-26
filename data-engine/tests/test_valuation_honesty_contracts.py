"""Contract tests for the valuation honesty invariants.

These are the invariants the product states as non-negotiable ("missing data is
not an estimated fact"). They had no coverage before: the suite only protected
the honest path in ``long_term_model_service`` while four engines coerced a
missing ``net_debt`` to zero and flipped the sign of a negative FCF margin.
"""

import math
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base
from app.models import CalculatedMetric, Company, FinancialFact
from app.services.valuation_service import ValuationService
from app.valuation.engines.base import (
    apply_publication_blockers,
    clamp_fcf_margin,
    traceable_wacc,
)
from app.valuation.financial_snapshot import FinancialSnapshotBuilder
from app.valuation.reverse_dcf import ReverseDCFInputs, solve_required_growth


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def company(db):
    row = Company(
        ticker="HONCONTR",
        name="Honesty Contract Co",
        exchange="NASDAQ",
        currency="USD",
        sector="Technology",
        industry="Software",
        company_type="standard",
        valuation_model="standard_dcf",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------------
# clamp_fcf_margin must never flip the sign of a known value
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,ceiling,expected",
    [
        (-0.40, 0.50, -0.40),  # a known burn stays a burn
        (-0.08, 0.50, -0.08),
        (0.00, 0.50, 0.00),
        (0.15, 0.50, 0.15),
        (0.90, 0.50, 0.50),  # the ceiling still applies
    ],
)
def test_clamp_fcf_margin_preserves_sign(raw, ceiling, expected):
    clamped, was_clamped = clamp_fcf_margin(raw, ceiling=ceiling)
    assert clamped == pytest.approx(expected)
    assert math.copysign(1, clamped) == math.copysign(1, expected) or clamped == 0
    assert was_clamped is (clamped != raw)


def test_clamp_fcf_margin_never_turns_a_burn_into_profit():
    for raw in (-0.9, -0.4, -0.2, -0.01):
        clamped, _ = clamp_fcf_margin(raw, ceiling=0.50)
        assert clamped <= 0, raw


# --------------------------------------------------------------------------
# a publication blocker has to block publication
# --------------------------------------------------------------------------


def test_publication_blockers_demote_a_result_that_claims_to_be_final():
    result = {
        "status": "ok",
        "publishable": True,
        "publication_blockers": ["traceable_wacc"],
        "trace": {"publishable": True, "status": "ok"},
    }
    demoted = apply_publication_blockers(result)
    assert demoted["publishable"] is False
    assert demoted["status"] == "partial"
    # The numbers stay: an orientation with its assumptions named is worth more
    # than a refusal, and the trace has to agree with the top-level label.
    assert demoted["trace"]["publishable"] is False
    assert demoted["trace"]["status"] == "partial"
    assert "traceable_wacc" in demoted["trace"]["publication_blockers"]
    assert demoted["trace"]["notice"]


def test_a_result_without_blockers_is_untouched():
    result = {"status": "ok", "publishable": True, "trace": {}}
    assert apply_publication_blockers(result)["publishable"] is True


def test_insufficient_data_stays_insufficient_data_when_blocked():
    result = {
        "status": "insufficient_data",
        "publishable": False,
        "publication_blockers": ["segment:beta_operating_metric"],
        "trace": {},
    }
    blocked = apply_publication_blockers(result)
    assert blocked["status"] == "insufficient_data"
    assert blocked["publishable"] is False


def test_dcf_on_a_tag_default_wacc_is_not_publishable(db, company):
    """The discount rate was an assumption; the label has to say so."""
    for metric, value in {
        "revenue": 1000,
        "free_cash_flow": 120,
        "revenue_growth": 0.07,
        "shares_diluted": 100,
        "net_debt": 200,
    }.items():
        db.add(
            FinancialFact(
                company_id=company.id,
                metric=metric,
                value=Decimal(str(value)),
                unit="USD",
                period="FY2025",
                fiscal_year=2025,
                fiscal_quarter="FY",
                source_type="contract_test",
                confidence=Decimal("0.9"),
            )
        )
    db.commit()

    result = ValuationService().value_company(db, company)
    assert "traceable_wacc" in result["publication_blockers"]
    assert result["publishable"] is False
    assert result["status"] == "partial"
    # The valuation is still computed and still legible.
    assert result["expected_value"] is not None


def test_dcf_with_a_persisted_wacc_is_publishable(db, company):
    for metric, value in {
        "revenue": 1000,
        "free_cash_flow": 120,
        "revenue_growth": 0.07,
        "shares_diluted": 100,
        "net_debt": 200,
    }.items():
        db.add(
            FinancialFact(
                company_id=company.id,
                metric=metric,
                value=Decimal(str(value)),
                unit="USD",
                period="FY2025",
                fiscal_year=2025,
                fiscal_quarter="FY",
                source_type="contract_test",
                confidence=Decimal("0.9"),
            )
        )
    db.add(
        CalculatedMetric(
            company_id=company.id,
            metric="wacc",
            value=0.08,
            unit="decimal",
            period="2025-12-31:FY",
            fiscal_year=2025,
            status="ok",
            definition_version="WACC_STANDARD_V1",
            formula="ke*E/(D+E) + kd*(1-t)*D/(D+E)",
        )
    )
    db.commit()

    result = ValuationService().value_company(db, company)
    assert result["publication_blockers"] == []
    assert result["publishable"] is True
    assert result["status"] == "ok"


def test_a_sotp_with_an_unvalued_segment_is_not_the_company_sotp(db, company):
    """A total with one of its parts missing is a value for nobody's business.

    The detectable case is a segment the company HAS a multiple for but no
    operating metric for: the engine knows the segment exists and cannot value
    it, so summing the rest and publishing the total would state a value for a
    part of the company the model never looked at.
    """
    company.company_type = "multi_segment"
    company.valuation_model = "sotp"
    company.factor_tags = ["sotp"]
    for metric, value in {
        "shares_diluted": 100,
        "net_debt": 200,
        "holding_company_discount": 0.12,
        "segment_alpha_operating_metric": 80,
        "segment_alpha_valuation_multiple": 12,
        "segment_beta_valuation_multiple": 1.1,
    }.items():
        db.add(
            FinancialFact(
                company_id=company.id,
                metric=metric,
                value=Decimal(str(value)),
                unit="USD",
                period="FY2025",
                fiscal_year=2025,
                fiscal_quarter="FY",
                source_type="contract_test",
                confidence=Decimal("0.9"),
            )
        )
    db.commit()

    result = ValuationService().value_company(db, company)
    assert result["publishable"] is False
    assert result["status"] == "partial"
    assert "segment:segment_beta_operating_metric" in result["publication_blockers"]
    assert result["missing_inputs"] == ["segment_beta_operating_metric"]
    assert result["trace"]["segments_valued"] == ["alpha"]
    # The sum of what IS known stays legible, and the reverse DCF is not
    # pretended: this is not a single-firm DCF in disguise.
    assert result["expected_value"] is not None
    assert result["reverse_dcf"] == {}


# --------------------------------------------------------------------------
# Reverse DCF must withhold its value when the price is not valueable
# --------------------------------------------------------------------------


def _reverse_inputs(price):
    return ReverseDCFInputs(
        market_price=price,
        revenue=1000.0,
        fcf_margin=0.15,
        wacc=0.09,
        terminal_growth=0.025,
        net_debt=100.0,
        shares_outstanding=100.0,
    )


def test_reverse_dcf_withholds_required_growth_when_price_is_out_of_bounds():
    """A price below the whole valueable range has no 'required growth'.

    The bisection saturates at low_growth, so publishing that number made the
    product state "the price requires -25% revenue growth" when the truth is
    "this price is not reproducible by any scenario in the model".
    """
    solved = solve_required_growth(_reverse_inputs(1.0))
    assert solved["out_of_bounds"] is True
    assert solved["status"] == "out_of_bounds"
    assert solved["required_revenue_growth"] is None
    assert solved["reason"]


def test_reverse_dcf_still_solves_inside_the_range():
    solved = solve_required_growth(_reverse_inputs(25.0))
    assert solved["out_of_bounds"] is False
    assert solved["status"] == "ok"
    assert solved["required_revenue_growth"] is not None
    # The saturated search bound is still recoverable for auditing.
    assert "bound_values" in solved["trace"]


# --------------------------------------------------------------------------
# net_debt is a required DCF input, not an implicit zero
# --------------------------------------------------------------------------


def _fact(db, company, metric, value, period="2024-12-31:FY", unit="USD"):
    row = FinancialFact(
        company_id=company.id,
        metric=metric,
        value=value,
        unit=unit,
        period=period,
        fiscal_year=2024,
        fiscal_quarter="FY",
        source_type="SEC",
        is_reported=True,
        confidence=0.9,
    )
    db.add(row)
    db.flush()
    return row


def test_snapshot_without_net_debt_is_not_coherent(db, company):
    """Without net_debt the equity bridge is unknown, so nothing is coherent."""
    _fact(db, company, "revenue", 2000)
    _fact(db, company, "shares_diluted", 200)
    _fact(db, company, "free_cash_flow", 300)

    snapshot = FinancialSnapshotBuilder().build(db, company)

    assert "net_debt" in snapshot.missing_inputs
    assert snapshot.coherent is False


def test_snapshot_with_net_debt_is_coherent(db, company):
    _fact(db, company, "revenue", 2000)
    _fact(db, company, "shares_diluted", 200)
    _fact(db, company, "free_cash_flow", 300)
    _fact(db, company, "net_debt", 800)

    snapshot = FinancialSnapshotBuilder().build(db, company)

    assert snapshot.missing_inputs == []
    assert snapshot.coherent is True


def test_snapshot_accepts_negative_net_debt_as_net_cash(db, company):
    """Net cash is a real, bullish input: presence is required, not positivity."""
    _fact(db, company, "revenue", 2000)
    _fact(db, company, "shares_diluted", 200)
    _fact(db, company, "free_cash_flow", 300)
    _fact(db, company, "net_debt", -800)

    snapshot = FinancialSnapshotBuilder().build(db, company)

    assert snapshot.missing_inputs == []
    assert snapshot.coherent is True
    assert snapshot.value("net_debt") == pytest.approx(-800.0)


def test_snapshot_treats_a_nan_fact_as_missing(db, company):
    """Numeric(24, 6) admits NaN in Postgres; every clamp here is NaN-transparent.

    ``max(min(nan, 0.5), 0.01)`` evaluates to ``nan`` in Python, so a single
    poisoned fact used to reach the API as ``status: "ok", base_value: NaN``.
    SQLite cannot store NaN (it coerces it to NULL), so the guard is exercised
    on the snapshot accessor, which is the single boundary every engine reads.
    """
    from app.valuation.financial_snapshot import FinancialSnapshot

    poisoned = _fact(db, company, "fcf_margin", 0.15)
    db.flush()
    # Postgres Numeric(24, 6) round-trips NaN; force the in-memory value.
    poisoned.value = float("nan")

    snapshot = FinancialSnapshot(facts={"fcf_margin": poisoned})

    assert snapshot.value("fcf_margin") is None


def test_snapshot_treats_an_infinite_fact_as_missing(db, company):
    from app.valuation.financial_snapshot import FinancialSnapshot

    poisoned = _fact(db, company, "net_debt", 0.0)
    db.flush()
    poisoned.value = float("inf")

    snapshot = FinancialSnapshot(facts={"net_debt": poisoned})

    assert snapshot.value("net_debt") is None


def test_snapshot_rejects_ttm_anchor_paired_with_fy_fact(db, company):
    """A TTM revenue must not be divided by an FY free cash flow."""
    _fact(db, company, "revenue", 1000, period="TTM 2024", unit="USD")
    _fact(db, company, "shares_diluted", 100)
    _fact(db, company, "net_debt", 100)
    _fact(db, company, "free_cash_flow", 125, period="2024-12-31:FY")

    snapshot = FinancialSnapshotBuilder().build(db, company)

    assert "free_cash_flow" not in snapshot.facts
    assert any("free_cash_flow" in warning for warning in snapshot.warnings)


def test_snapshot_flags_a_cross_year_balance_sheet(db, company):
    _fact(db, company, "revenue", 2000, period="2024-12-31:FY")
    _fact(db, company, "shares_diluted", 200, period="2024-12-31:FY")
    _fact(db, company, "free_cash_flow", 300, period="2024-12-31:FY")
    net_debt = _fact(db, company, "net_debt", 500, period="2025-12-31:FY")
    net_debt.fiscal_year = 2025

    snapshot = FinancialSnapshotBuilder().build(db, company)

    assert any("net_debt" in warning and "fiscal year" in warning for warning in snapshot.warnings)


# --------------------------------------------------------------------------
# The traceable WACC must win over the tag-based policy default
# --------------------------------------------------------------------------


def test_traceable_wacc_prefers_the_persisted_calculated_metric(db, company):
    db.add(
        CalculatedMetric(
            company_id=company.id,
            metric="wacc",
            value=0.062,
            unit="decimal",
            period="2024-12-31:FY",
            fiscal_year=2024,
            status="ok",
            definition_version="WACC_STANDARD_V1",
            formula="ke*E/(D+E) + kd*(1-t)*D/(D+E)",
        )
    )
    db.flush()

    assert traceable_wacc(db, company) == pytest.approx(0.062)


def test_traceable_wacc_ignores_non_ok_and_out_of_range_rows(db, company):
    db.add(
        CalculatedMetric(
            company_id=company.id, metric="wacc", value=0.5, unit="decimal",
            period="2024-12-31:FY", fiscal_year=2024, status="insufficient_data",
            definition_version="v1", formula="x",
        )
    )
    db.flush()
    assert traceable_wacc(db, company) is None

    db.add(
        CalculatedMetric(
            company_id=company.id, metric="wacc", value=47.0, unit="decimal",
            period="2025-12-31:FY", fiscal_year=2025, status="ok",
            definition_version="v1", formula="x",
        )
    )
    db.flush()
    assert traceable_wacc(db, company) is None


def test_traceable_wacc_returns_none_without_a_persisted_metric(db, company):
    assert traceable_wacc(db, company) is None
