"""F370: el momentum historico solo usa precios hasta as_of."""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models import CalculatedMetric, MarketPrice
from app.services.propicks_price_service import compute_momentum_metrics
from tests.test_propicks_prices import _company, _db


def _seed(db, start, days, price_fn):
    company = _company("MOM")
    db.add(company)
    db.flush()
    for i in range(days):
        day = start + timedelta(days=i)
        db.add(MarketPrice(company_id=company.id, date=day, close=Decimal(price_fn(i)),
                           adj_close=Decimal(price_fn(i)), source="test"))
    db.flush()
    return company


def test_historical_as_of_ignores_future_bars():
    db = _db()
    start = date(2024, 1, 1)
    # 400 dias: sube de 100 a ~140, y despues del dia 300 se dispara a 1000.
    company = _seed(db, start, 400, lambda i: 100 + i * 0.1 if i < 300 else 1000)
    as_of = start + timedelta(days=299)
    compute_momentum_metrics(db, [company], as_of=as_of)
    metric = db.scalar(
        select(CalculatedMetric).where(
            CalculatedMetric.company_id == company.id,
            CalculatedMetric.metric == "momentum_6m",
        )
    )
    assert metric is not None
    assert metric.calculation_trace["last_bar_date"] == as_of.isoformat()
    assert metric.value < Decimal("1")  # con datos futuros seria > 5
