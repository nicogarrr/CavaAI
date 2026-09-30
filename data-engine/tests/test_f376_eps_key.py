"""F376: historical valuation reads the ingested eps_diluted key (eps is a legacy alias)."""

from datetime import date
from decimal import Decimal

from app.models.entities import MarketPrice
from app.services.historical_valuation_service import HistoricalValuationService
from tests.test_historical_valuation_service import _company, _fact, db  # noqa: F401


def _point(db, eps_metric):
    company = _company(db)
    db.add(MarketPrice(
        company_id=company.id, date=date(2024, 12, 31), open=Decimal("190"),
        high=Decimal("200"), low=Decimal("189"), close=Decimal("200"),
        adj_close=Decimal("200"), source="Finnhub",
    ))
    db.commit()
    _fact(db, company, metric=eps_metric, fiscal_year=2024, value="10")
    result = HistoricalValuationService().build(db, company, as_of=date(2026, 9, 23))
    return next(p for p in result["series"] if p["year"] == 2024)


def test_eps_diluted_key_feeds_pe(db):  # noqa: F811
    point = _point(db, "eps_diluted")
    assert point["eps"] == Decimal("10")
    assert point["pe"] == Decimal("20")


def test_legacy_eps_key_still_works(db):  # noqa: F811
    assert _point(db, "eps")["eps"] == Decimal("10")
