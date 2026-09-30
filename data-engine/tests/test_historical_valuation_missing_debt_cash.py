"""F371: missing debt/cash must not be imputed as 0 in enterprise value."""

from datetime import date
from decimal import Decimal

from app.models.entities import MarketPrice
from app.services.historical_valuation_service import HistoricalValuationService
from tests.test_historical_valuation_service import _company, _fact, db  # noqa: F401


def _seed(db, *, debt=None, cash=None):
    company = _company(db)
    db.add(MarketPrice(
        company_id=company.id, date=date(2024, 12, 31), open=Decimal("190"),
        high=Decimal("200"), low=Decimal("189"), close=Decimal("200"),
        adj_close=Decimal("200"), source="Finnhub",
    ))
    db.commit()
    for metric, value in (("eps", "10"), ("shares_diluted", "100"),
                          ("free_cash_flow", "1000"), ("revenue", "4000")):
        _fact(db, company, metric=metric, fiscal_year=2024, value=value)
    if debt is not None:
        _fact(db, company, metric="total_debt", fiscal_year=2024, value=debt)
    if cash is not None:
        _fact(db, company, metric="cash_and_equivalents", fiscal_year=2024, value=cash)
    return company


def _point(db, company):
    result = HistoricalValuationService().build(db, company, as_of=date(2026, 9, 23))
    return next(p for p in result["series"] if p["year"] == 2024), result


def test_missing_debt_makes_ev_multiples_missing(db):  # noqa: F811
    point, result = _point(db, _seed(db, cash="100"))
    assert point["ev_to_fcf"] is None and point["ev_to_revenue"] is None
    assert result["coverage"]["complete_valuation_points"] == 0


def test_missing_cash_makes_ev_multiples_missing(db):  # noqa: F811
    point, _ = _point(db, _seed(db, debt="300"))
    assert point["ev_to_fcf"] is None


def test_reported_zero_debt_and_cash_is_used(db):  # noqa: F811
    point, _ = _point(db, _seed(db, debt="0", cash="0"))
    assert point["ev_to_fcf"] == Decimal("20")
