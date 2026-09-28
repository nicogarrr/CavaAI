"""Profile routing does not mistake investment-phase losses for a moat verdict."""

from types import SimpleNamespace

from app.services.moat_profile import financial_quality_profile


def company(**overrides):
    fields = dict(company_type="standard", valuation_model="standard_dcf", sector="Technology", factor_tags=[])
    return SimpleNamespace(**(fields | overrides))


def test_asts_pre_fcf_is_not_classified_by_its_current_revenue():
    profile, reason = financial_quality_profile(company(
        company_type="space_telecom_pre_fcf",
        valuation_model="probability_weighted_scenarios+dilution",
        factor_tags=["space", "speculative", "pre_fcf", "telecom"],
    ))
    assert profile == "early_stage"
    assert "caja" in reason


def test_financial_cyclical_growth_mature_and_unknown_profiles():
    assert financial_quality_profile(company(company_type="bank"))[0] == "financial"
    assert financial_quality_profile(company(sector="Financials"))[0] == "financial"
    assert financial_quality_profile(company(factor_tags=["cyclical"]))[0] == "cyclical"
    assert financial_quality_profile(company(factor_tags=["growth"]))[0] == "growth"
    assert financial_quality_profile(company())[0] == "mature"
    assert financial_quality_profile(company(company_type="", valuation_model=""))[0] == "unknown"


def test_company_creation_placeholders_are_not_mature():
    for kind, model in [
        ("research_candidate", "standard_dcf"),
        ("standard", "unassigned"),
        ("research_candidate", "unassigned"),
    ]:
        assert financial_quality_profile(company(
            company_type=kind, valuation_model=model,
        ))[0] == "unknown"
