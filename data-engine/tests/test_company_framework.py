from app.models import Company
from app.services.company_framework import resolve_company_framework
from app.services.driver_operating_model import DriverOperatingModel
from app.models import FinancialFact
from decimal import Decimal


def _company(ticker: str, company_type: str, tags: list[str]) -> Company:
    return Company(
        ticker=ticker,
        name=ticker,
        exchange="TEST",
        currency="USD",
        sector="Test",
        industry="Test",
        company_type=company_type,
        valuation_model="test",
        special_sources=[],
        special_risks=[],
        factor_tags=tags,
    )


def test_framework_is_company_specific_for_network_and_holding_businesses():
    asts = resolve_company_framework(_company("ASTS", "space_telecom_pre_fcf", ["space", "telecom"]))
    brookfield = resolve_company_framework(_company("BN", "asset_manager_holding", ["sotp"]))

    assert asts.key == "space_network"
    assert asts.market_opportunity_mode == "required"
    assert "satellites" in asts.revenue_drivers
    assert "unit_economics" in asts.active_modules

    assert brookfield.key == "holding_asset_manager"
    assert brookfield.market_opportunity_mode == "reinvestment_runway"
    assert "holdco_debt" in brookfield.kpis
    assert "sotp" in brookfield.active_modules


def test_framework_routes_financials_and_reits_to_their_economic_drivers():
    bank = resolve_company_framework(_company("BANK", "bank", []))
    insurer = resolve_company_framework(_company("INSR", "insurer", []))
    reit = resolve_company_framework(_company("PROP", "reit", []))

    assert bank.key == "bank"
    assert "net_interest_margin" in bank.revenue_drivers
    assert "cet1_ratio" in bank.required_fact_metrics
    assert insurer.key == "insurer"
    assert "combined_ratio" in insurer.required_fact_metrics
    assert reit.key == "reit"
    assert "net_operating_income" in reit.required_fact_metrics


def test_space_network_formula_uses_sourced_demand_and_capacity_drivers():
    company = _company("ASTS", "space_telecom_pre_fcf", ["space", "telecom"])
    framework = resolve_company_framework(company)
    values = {
        "addressable_subscribers": 1000,
        "penetration": 0.10,
        "monthly_arpu": 10,
        "revenue_share": 0.50,
        "satellites": 10,
        "capacity_per_satellite": 100,
        "utilization": 0.50,
        "price_per_gb": 100,
    }
    units = {
        "addressable_subscribers": "count",
        "penetration": "decimal",
        "monthly_arpu": "USD/subscriber/month",
        "revenue_share": "decimal",
        "satellites": "count",
        "capacity_per_satellite": "GB/satellite/year",
        "utilization": "decimal",
        "price_per_gb": "USD/GB",
    }
    cache = {}
    for index, (metric, value) in enumerate(values.items(), start=1):
        fact = FinancialFact(
            id=index,
            company_id=1,
            metric=metric,
            value=Decimal(str(value)),
            unit=units[metric],
            period="FY2025",
            fiscal_year=2025,
            fiscal_quarter="FY",
            source_type="test",
            confidence=Decimal("0.95"),
        )
        cache[metric] = [fact]
    result = DriverOperatingModel().build(
        framework, cache, latest_year=2025, horizon=1, scenario="base"
    )
    assert result["status"] == "driver_based"
    assert result["years"][0]["segments"]["connectivity_demand"] == 6000
    assert result["years"][0]["segments"]["connectivity_capacity_ceiling"] == 50000
    assert result["years"][0]["output"] == 6000
    assert result["years"][0]["output_dimension"] == "currency/year"
    assert result["dimensional_validation"]["valid"] is True


def test_driver_formula_rejects_an_incompatible_explicit_unit():
    company = _company("ASTS", "space_telecom_pre_fcf", ["space", "telecom"])
    framework = resolve_company_framework(company)
    units = {
        "addressable_subscribers": "count",
        "penetration": "decimal",
        "monthly_arpu": "USD/subscriber/month",
        "revenue_share": "decimal",
        "satellites": "count",
        # Missing the satellite denominator: this is total capacity, not
        # capacity per satellite.
        "capacity_per_satellite": "GB/year",
        "utilization": "decimal",
        "price_per_gb": "USD/GB",
    }
    cache = {
        metric: [
            FinancialFact(
                id=index,
                company_id=1,
                metric=metric,
                value=Decimal("1"),
                unit=unit,
                period="FY2025",
                fiscal_year=2025,
                fiscal_quarter="FY",
                source_type="test",
                confidence=Decimal("0.95"),
            )
        ]
        for index, (metric, unit) in enumerate(units.items(), start=1)
    }

    result = DriverOperatingModel().build(
        framework, cache, latest_year=2025, horizon=1, scenario="base"
    )

    assert result["status"] == "invalid_driver_dimensions"
    assert result["years"] == []
    assert result["dimension_errors"][0]["driver"] == "capacity_per_satellite"
