"""F402: reverse DCF and scenario values must share one share basis for ADRs."""

import pytest

from app.core.database import SessionLocal, init_db
from app.services.valuation_service import ValuationService
from tests.test_valuation_engines_refined import (
    _add_facts,
    _add_price,
    _add_traceable_wacc,
    _cleanup,
    _make_company,
)

FACTS = {"revenue": 1000, "free_cash_flow": 120, "revenue_growth": 0.07, "shares_diluted": 100, "net_debt": 200}


def _value(db, ticker, tags, price):
    company = _make_company(
        db, ticker, company_type="standard", valuation_model="standard_dcf", factor_tags=tags
    )
    _add_facts(db, company, FACTS)
    _add_price(db, company, price)
    _add_traceable_wacc(db, company)
    return ValuationService().value_company(db, company)


def test_adr_reverse_dcf_uses_ordinary_share_price():
    init_db()
    db = SessionLocal()
    tickers = ["ADRA", "ORDA"]
    try:
        adr = _value(db, "ADRA", ["adr:2"], 30.0)  # 2 ordinary shares per ADR
        ordinary = _value(db, "ORDA", [], 15.0)
        assert adr["status"] == "ok" and ordinary["status"] == "ok"
        assert adr["value_per_share_basis"] == "ordinary_share"
        # Same economic price per ordinary share => same reverse DCF result.
        assert adr["reverse_dcf"]["market_price"] == pytest.approx(15.0)
        assert adr["reverse_dcf"]["required_revenue_growth"] == pytest.approx(
            ordinary["reverse_dcf"]["required_revenue_growth"]
        )
        # Listed-share (ADR) equivalents are explicit, not implied.
        assert adr["listed_share_values"]["base"] == pytest.approx(adr["base_value"] * 2)
        assert ordinary["listed_share_values"] is None
    finally:
        _cleanup(db, tickers)
        db.close()
