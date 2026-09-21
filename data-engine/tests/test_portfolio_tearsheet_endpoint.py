"""Endpoint GET /api/portfolio/tearsheet + fiscalidad de posiciones.

Run from data-engine/:
    pytest tests/test_portfolio_tearsheet_endpoint.py tests/test_portfolio_fiscal_bucket.py -v
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes import portfolio as portfolio_route
from app.core.database import Base
from app.models import (
    Company,
    Portfolio,
    PortfolioDailySnapshot,
    Position,
    PositionDailySnapshot,
    Tenant,
    Transaction,
)

RETURNS = [0.01, -0.005, 0.02, -0.015, 0.008]


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    tenant = Tenant(external_id="tearsheet-endpoint-test", name="Tearsheet endpoint test")
    db.add(tenant)
    db.flush()
    db.info["tenant_id"] = tenant.id
    return db


def _seed_history(db: Session) -> None:
    portfolio = Portfolio(
        tenant_id=db.info["tenant_id"], name="Main", base_currency="EUR", is_default=True
    )
    db.add(portfolio)
    db.flush()
    company = Company(
        ticker="AAA",
        name="AAA",
        exchange="X",
        currency="EUR",
        sector="S",
        industry="I",
        company_type="imported_holding",
        valuation_model="unassigned",
    )
    db.add(company)
    db.flush()
    wealth = 10000.0
    for day, line_return in enumerate(RETURNS, start=1):
        wealth *= 1.0 + line_return
        snapshot = PortfolioDailySnapshot(
            tenant_id=db.info["tenant_id"],
            portfolio_id=portfolio.id,
            snapshot_date=date(2026, 9, day),
            base_currency="EUR",
            positions_value_base=Decimal(str(round(wealth * 0.8, 2))),
            cash_value_base=Decimal(str(round(wealth * 0.2, 2))),
            total_value_base=Decimal(str(round(wealth, 2))),
            daily_return=Decimal(str(line_return)) if day > 1 else None,
        )
        db.add(snapshot)
        db.flush()
        db.add(
            PositionDailySnapshot(
                tenant_id=db.info["tenant_id"],
                portfolio_snapshot_id=snapshot.id,
                portfolio_id=portfolio.id,
                company_id=company.id,
                snapshot_date=date(2026, 9, day),
                quantity=Decimal("10"),
                market_price_native=Decimal("100"),
                currency="EUR",
                market_value_native=Decimal("1000"),
                market_value_base=snapshot.positions_value_base,
            )
        )
    db.flush()


def test_tearsheet_route_is_registered():
    paths = [route.path for route in portfolio_route.router.routes]
    # El prefijo /api/portfolio se monta en app/api/router.py.
    assert "/tearsheet" in paths


def test_tearsheet_endpoint_returns_sharpe_drawdown_win_rate():
    db = _session()
    try:
        _seed_history(db)
        result = portfolio_route.portfolio_tearsheet(db)
    finally:
        db.close()
    assert result["status"] == "ok"
    metrics = result["metrics"]
    assert metrics["sharpe"] is not None
    assert metrics["max_drawdown"] is not None
    assert metrics["max_drawdown"] <= 0
    assert 0 <= metrics["win_rate"] <= 1
    assert result["exposure"]["n_positions"] == 1
    assert result["trace"]["method"] == "tearsheet_numpy_pandas_v1"


def test_tearsheet_endpoint_degrades_without_portfolio():
    db = _session()
    try:
        result = portfolio_route.portfolio_tearsheet(db)
    finally:
        db.close()
    assert result["status"] == "no_portfolio"
    assert result["metrics"] is None
