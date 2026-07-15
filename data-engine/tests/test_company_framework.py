from app.models import Company
from app.services.company_framework import resolve_company_framework


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
