from decimal import Decimal

from app.models import Company, FinancialFact
from app.services.company_framework import resolve_company_framework
from app.services.market_opportunity_service import MarketOpportunityEngine


def _fact(metric: str, value: float, fact_id: int) -> FinancialFact:
    return FinancialFact(
        id=fact_id,
        company_id=1,
        metric=metric,
        value=Decimal(str(value)),
        unit="USD",
        period="FY2025",
        fiscal_year=2025,
        fiscal_quarter="FY",
        source_type="test_market",
        is_reported=True,
        confidence=Decimal("0.90"),
    )


def test_bottom_up_formula_is_selected_from_the_company_framework():
    company = Company(
        ticker="ASTS",
        name="AST SpaceMobile",
        exchange="TEST",
        currency="USD",
        sector="Communication Services",
        industry="Satellite telecom",
        company_type="space_telecom_pre_fcf",
        valuation_model="scenario",
        special_sources=[],
        special_risks=[],
        factor_tags=["space", "telecom"],
    )
    framework = resolve_company_framework(company)
    fact_cache = {metric: [] for metric in MarketOpportunityEngine.metrics_for_framework(framework)}
    for fact_id, (metric, value) in enumerate(
        {
            "addressable_subscribers": 100_000_000,
            "penetration": 0.05,
            "monthly_arpu": 5,
            "revenue_share": 0.5,
        }.items(),
        start=1,
    ):
        fact_cache[metric].append(_fact(metric, value, fact_id))

    result = MarketOpportunityEngine()._bottom_up(fact_cache, framework)

    assert result["status"] == "ok"
    assert result["value"] == 150_000_000
    assert result["formulas"][0]["source_fact_ids"] == [1, 2, 3, 4]
