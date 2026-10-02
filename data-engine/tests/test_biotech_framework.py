"""Marco biotech/pre-FCF: la cesta AI<>Biology ya no cae en 'FCF compounder'."""

import pytest

from app.models import Company
from app.services.company_framework import FRAMEWORKS, resolve_company_framework
from app.services.driver_dimensions import FORMULA_TERMS
from app.services.driver_operating_model import FORMULAS


def _company(ticker: str, company_type: str, tags: list[str]) -> Company:
    return Company(
        ticker=ticker, name=ticker, exchange="TEST", currency="USD", sector="Test",
        industry="Test", company_type=company_type, valuation_model="test",
        special_sources=[], special_risks=[], factor_tags=tags,
    )


@pytest.mark.parametrize("ticker", ["IBRX", "NAUT", "RXRX", "ABCL"])
def test_basket_tickers_resolve_to_the_biotech_framework(ticker):
    framework = resolve_company_framework(_company(ticker, "biotech_pre_fcf", ["biotech"]))
    assert framework.key == "biotech_pre_fcf"


def test_company_type_alone_selects_the_framework():
    assert resolve_company_framework(_company("XYZ", "biotech_pre_fcf", [])).key == "biotech_pre_fcf"


def test_hims_keeps_its_subscriber_framework():
    assert resolve_company_framework(_company("HIMS", "healthcare_regulatory", ["healthcare"])).key == "subscriber"


def test_every_framework_has_a_formula_and_dimension_terms():
    for key in FRAMEWORKS:
        assert key in FORMULAS, key
        assert key in FORMULA_TERMS, key


def test_biotech_framework_invents_no_pipeline_economics():
    fw = FRAMEWORKS["biotech_pre_fcf"]
    assert FORMULAS["biotech_pre_fcf"].inputs == ("revenue",)
    assert "N/D" in fw.unit_economics[0]
    assert fw.required_fact_metrics == ()
