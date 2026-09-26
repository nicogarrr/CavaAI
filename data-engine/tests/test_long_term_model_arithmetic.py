"""Contract tests for the long-term fundamental model arithmetic.

Each of these pinned a number that the model produced for the wrong reason:
a dilution that destroyed value at market price, an unknown EBITDA that became
100% equity issuance, a negative tax rate clamped to zero (maximising NOPAT), a
terminal share count charged against a cash flow stream that never received the
issuance proceeds, and an ADR quote divided by ordinary shares.
"""

import pytest

from app.valuation.dilution_model import DilutionInput, run_dilution
from app.valuation.engines.base import adr_ratio, is_adr_without_ratio


def _company(**kwargs):
    from app.models import Company

    base = dict(
        ticker="T",
        name="n",
        exchange="E",
        currency="USD",
        sector="S",
        industry="I",
        company_type="standard",
        valuation_model="standard_dcf",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    base.update(kwargs)
    return Company(**base)


# --------------------------------------------------------------------------
# run_dilution must credit the cash that the issuance raises
# --------------------------------------------------------------------------


def test_market_price_issuance_is_value_neutral():
    """Raising cash at the current share price must not change value per share.

    100M shares at 10,00 (equity 1.000M) issuing 100M of new shares at 10,00:
    equity becomes 1.100M over 110M shares, which is still 10,00. Spreading
    the PRE-issuance equity over the pro-forma count returned 9,09, a 9.1%
    destruction of value for a transaction that is economically neutral.
    """
    result = run_dilution(
        DilutionInput(
            current_shares=100.0,
            new_capital_needed=100.0,
            issuance_price=10.0,
            current_value_per_share=10.0,
        )
    )

    assert result["diluted_value_per_share"] == pytest.approx(10.0)
    assert result["pre_equity_value"] == pytest.approx(1000.0)
    assert result["post_equity_value"] == pytest.approx(1100.0)
    assert result["issuance_premium_to_value"] == pytest.approx(1.0)
    # The old behaviour is retained only so the delta stays auditable.
    assert result["value_per_share_without_issuance_credit"] == pytest.approx(9.0909, rel=1e-3)


def test_dilutive_issuance_reduces_value_per_share():
    """Issuing below value does dilute, and the loss is bounded by the discount."""
    result = run_dilution(
        DilutionInput(
            current_shares=100.0,
            new_capital_needed=100.0,
            issuance_price=5.0,
            current_value_per_share=10.0,
        )
    )

    # 20M new shares; (1000 + 100) / 120 = 9.1667
    assert result["new_shares"] == pytest.approx(20.0)
    assert result["diluted_value_per_share"] == pytest.approx(1100.0 / 120.0)
    assert result["diluted_value_per_share"] < 10.0
    assert result["issuance_premium_to_value"] == pytest.approx(0.5)


def test_accretive_issuance_increases_value_per_share():
    result = run_dilution(
        DilutionInput(
            current_shares=100.0,
            new_capital_needed=100.0,
            issuance_price=20.0,
            current_value_per_share=10.0,
        )
    )

    # 5M new shares; 1100 / 105 = 10.476
    assert result["diluted_value_per_share"] == pytest.approx(1100.0 / 105.0)
    assert result["diluted_value_per_share"] > 10.0


def test_zero_capital_needed_is_a_no_op():
    result = run_dilution(
        DilutionInput(
            current_shares=100.0,
            new_capital_needed=0.0,
            issuance_price=10.0,
            current_value_per_share=7.0,
        )
    )

    assert result["new_shares"] == 0.0
    assert result["dilution_pct"] == 0.0
    assert result["diluted_value_per_share"] == pytest.approx(7.0)


def test_negative_capital_needed_is_clamped_to_zero():
    result = run_dilution(
        DilutionInput(
            current_shares=100.0,
            new_capital_needed=-50.0,
            issuance_price=10.0,
            current_value_per_share=7.0,
        )
    )

    assert result["capital_raised"] == 0.0
    assert result["diluted_value_per_share"] == pytest.approx(7.0)


# --------------------------------------------------------------------------
# ADR ratio must be explicit before mixing filing shares with an ADR quote
# --------------------------------------------------------------------------


def test_adr_ratio_is_read_from_the_factor_tag():
    company = _company(factor_tags=["china", "adr:8", "ecommerce"])
    assert adr_ratio(company) == pytest.approx(8.0)
    assert is_adr_without_ratio(company) is False


def test_adr_tagged_company_without_ratio_is_refused():
    company = _company(factor_tags=["china", "adr"])
    assert adr_ratio(company) is None
    assert is_adr_without_ratio(company) is True


def test_non_adr_company_needs_no_ratio():
    company = _company(factor_tags=["quality", "software"])
    assert adr_ratio(company) is None
    assert is_adr_without_ratio(company) is False


@pytest.mark.parametrize("tag", ["adr:0", "adr:-8", "adr:abc"])
def test_malformed_adr_tags_do_not_produce_a_ratio(tag):
    company = _company(factor_tags=[tag])
    assert adr_ratio(company) is None
    assert is_adr_without_ratio(company) is True
