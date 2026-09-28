"""Tests herméticos del chequeo de umbrales del Modelo 720 (sin red).

Run from data-engine/:
    pytest tests/test_tax_modelo720_service.py -v
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import (
    CashBalance,
    CashDailySnapshot,
    Company,
    Portfolio,
    PortfolioDailySnapshot,
    Position,
    PositionDailySnapshot,
    Tenant,
)
from app.services.tax_modelo720_service import Modelo720Service


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _PARENTS.clear()
        yield session


def _seed(db: Session):
    tenant = Tenant(external_id="m720-test", name="M720 test")
    db.add(tenant)
    db.flush()
    portfolio = Portfolio(
        tenant_id=tenant.id, name="Main", base_currency="EUR", is_default=True
    )
    db.add(portfolio)
    db.flush()
    return tenant, portfolio


def _position_row(db, tenant, portfolio, company, source="ibkr_flex"):
    db.add(Position(
        tenant_id=tenant.id,
        company_id=company.id,
        portfolio_id=portfolio.id,
        quantity=Decimal("10"),
        average_cost=Decimal("100"),
        market_value=Decimal("1000"),
        base_currency="EUR",
        source=source,
    ))
    db.flush()


def _cash_balance_row(db, tenant, currency, source="ibkr_flex"):
    db.add(CashBalance(
        tenant_id=tenant.id,
        currency=currency,
        balance=Decimal("0"),
        source=source,
    ))
    db.flush()


def _company(db: Session, tenant, ticker: str, isin: str | None = None) -> Company:
    company = Company(
        ticker=ticker,
        name=ticker,
        exchange="X",
        currency="USD",
        sector="S",
        industry="I",
        company_type="imported_holding",
        valuation_model="unassigned",
        isin=isin,
    )
    db.add(company)
    db.flush()
    return company


_PARENTS = {}


def _parent_snapshot(db, tenant, portfolio, day):
    # Un único snapshot padre por fecha (unique tenant+portfolio+fecha).
    key = day
    if key in _PARENTS:
        return _PARENTS[key]
    snap = PortfolioDailySnapshot(
        tenant_id=tenant.id,
        portfolio_id=portfolio.id,
        snapshot_date=day,
        base_currency="EUR",
        positions_value_base=Decimal("0"),
        cash_value_base=Decimal("0"),
        total_value_base=Decimal("0"),
    )
    db.add(snap)
    db.flush()
    _PARENTS[key] = snap
    return snap


def _position_snapshot(db, tenant, portfolio, company, day, value_base):
    snap = _parent_snapshot(db, tenant, portfolio, day)
    db.add(
        PositionDailySnapshot(
            tenant_id=tenant.id,
            portfolio_snapshot_id=snap.id,
            portfolio_id=portfolio.id,
            company_id=company.id,
            snapshot_date=day,
            quantity=Decimal("10"),
            market_price_native=Decimal("100"),
            currency="USD",
            fx_rate=Decimal("1"),
            market_value_native=Decimal(str(value_base or 0)),
            market_value_base=Decimal(str(value_base)) if value_base is not None else None,
        )
    )
    db.flush()


def _cash_snapshot(db, tenant, portfolio, currency, balance, fx, day=date(2025, 12, 31)):
    snap = _parent_snapshot(db, tenant, portfolio, day)
    db.add(
        CashDailySnapshot(
            tenant_id=tenant.id,
            portfolio_snapshot_id=snap.id,
            portfolio_id=portfolio.id,
            snapshot_date=day,
            currency=currency,
            balance_native=Decimal(str(balance)),
            fx_rate=Decimal(str(fx)) if fx is not None else None,
        )
    )
    db.flush()


def test_thresholds_per_category_below(db):
    tenant, portfolio = _seed(db)
    c = _company(db, tenant, "AAPL", isin="US0378331005")
    _position_row(db, tenant, portfolio, c)
    _position_snapshot(db, tenant, portfolio, c, date(2025, 12, 31), 40000)
    _cash_balance_row(db, tenant, "EUR")
    _cash_snapshot(db, tenant, portfolio, "EUR", 30000, 1)

    result = Modelo720Service().check_thresholds(db, 2025)

    assert result["threshold_base"] == 50000.0
    assert result["categories"]["valores"]["exceeds"] is False
    assert result["categories"]["valores"]["status"] == "por_debajo"
    assert result["categories"]["valores"]["total_base"] == 40000.0
    assert result["categories"]["valores"]["positions"][0]["isin"] == "US0378331005"
    # Cuentas: aunque el saldo a 31/12 no supera, falta la media del 4T →
    # resultado no concluyente (tri-estado), nunca un "no" rotundo.
    assert result["categories"]["cuentas"]["exceeds"] is None
    assert result["categories"]["cuentas"]["status"] == "desconocido"
    assert result["categories"]["cuentas"]["average_q4_missing"] is True
    assert result["categories"]["inmuebles"]["exceeds"] is None
    assert result["categories"]["inmuebles"]["status"] == "no_evaluable"
    assert result["categories"]["inmuebles"]["total_base"] is None
    assert result["incomplete"] is False


def test_thresholds_exceeds_valores_and_missing_isin(db):
    tenant, portfolio = _seed(db)
    c1 = _company(db, tenant, "AAPL", isin="US0378331005")
    c2 = _company(db, tenant, "MSFT")  # sin ISIN
    _position_row(db, tenant, portfolio, c1)
    _position_row(db, tenant, portfolio, c2)
    _position_snapshot(db, tenant, portfolio, c1, date(2025, 12, 31), 30000)
    _position_snapshot(db, tenant, portfolio, c2, date(2025, 12, 31), 25000)

    result = Modelo720Service().check_thresholds(db, 2025)

    valores = result["categories"]["valores"]
    assert valores["exceeds"] is True
    assert valores["status"] == "supera"
    assert valores["total_base"] == 55000.0
    assert valores["missing_isin"] == ["MSFT"]
    # Las cuentas no heredan el exceso: el umbral es por categoría.
    assert result["categories"]["cuentas"]["exceeds"] is not True


def test_unvalued_position_excluded_and_flagged(db):
    tenant, portfolio = _seed(db)
    c1 = _company(db, tenant, "AAPL", isin="US0378331005")
    c2 = _company(db, tenant, "XYZ")
    _position_row(db, tenant, portfolio, c1)
    _position_row(db, tenant, portfolio, c2)
    _position_snapshot(db, tenant, portfolio, c1, date(2025, 12, 31), 10000)
    _position_snapshot(db, tenant, portfolio, c2, date(2025, 12, 31), None)

    result = Modelo720Service().check_thresholds(db, 2025)

    assert result["categories"]["valores"]["total_base"] == 10000.0
    # Con un valor fuera del total, un "por_debajo" sería falso verde.
    assert result["categories"]["valores"]["exceeds"] is None
    assert result["categories"]["valores"]["status"] == "desconocido"
    assert result["incomplete"] is True
    assert result["unvalued"][0]["ticker"] == "XYZ"
    assert "valorar a mano" in result["unvalued"][0]["reason"]


def test_latest_snapshot_before_year_end_used(db):
    tenant, portfolio = _seed(db)
    c = _company(db, tenant, "AAPL", isin="US0378331005")
    _position_row(db, tenant, portfolio, c)
    # Snapshot viejo (noviembre) y el de cierre: manda el más reciente ≤ 31/12.
    _position_snapshot(db, tenant, portfolio, c, date(2025, 11, 30), 10000)
    _position_snapshot(db, tenant, portfolio, c, date(2025, 12, 31), 60000)

    result = Modelo720Service().check_thresholds(db, 2025)

    assert result["categories"]["valores"]["total_base"] == 60000.0
    assert result["categories"]["valores"]["exceeds"] is True


def test_cash_without_fx_is_unvalued(db):
    tenant, portfolio = _seed(db)
    _cash_balance_row(db, tenant, "USD")
    _cash_snapshot(db, tenant, portfolio, "USD", 60000, None)

    result = Modelo720Service().check_thresholds(db, 2025)

    assert result["categories"]["cuentas"]["total_base"] == 0.0
    assert result["categories"]["cuentas"]["exceeds"] is None
    assert result["categories"]["cuentas"]["status"] == "desconocido"
    assert result["incomplete"] is True
    assert result["unvalued"][0]["ticker"] == "cash-USD"


def test_cash_converted_with_fx_exceeds(db):
    tenant, portfolio = _seed(db)
    _cash_balance_row(db, tenant, "USD")
    _cash_snapshot(db, tenant, portfolio, "USD", 60000, 0.9)

    result = Modelo720Service().check_thresholds(db, 2025)

    assert result["categories"]["cuentas"]["total_base"] == 54000.0
    assert result["categories"]["cuentas"]["exceeds"] is True
    assert result["categories"]["cuentas"]["status"] == "supera"


def test_stale_snapshot_is_unknown_not_negative(db):
    tenant, portfolio = _seed(db)
    c = _company(db, tenant, "AAPL", isin="US0378331005")
    _position_row(db, tenant, portfolio, c)
    # Último snapshot de junio: 184 días antes del cierre → no afirma nada.
    _position_snapshot(db, tenant, portfolio, c, date(2025, 6, 30), 60000)

    result = Modelo720Service().check_thresholds(db, 2025)

    valores = result["categories"]["valores"]
    assert valores["exceeds"] is None
    assert valores["status"] == "desconocido"
    assert valores["snapshot_lag_days"] == 184
    assert any("antiguo" in r for r in valores["reasons"])


def test_short_position_excluded_from_total(db):
    tenant, portfolio = _seed(db)
    c = _company(db, tenant, "AAPL", isin="US0378331005")
    _position_row(db, tenant, portfolio, c)
    _position_snapshot(db, tenant, portfolio, c, date(2025, 12, 31), -30000)

    result = Modelo720Service().check_thresholds(db, 2025)

    # Un corto es una deuda, no un bien: no suma al umbral vía abs().
    assert result["categories"]["valores"]["total_base"] == 0.0
    assert result["short_positions"][0]["ticker"] == "AAPL"
    assert result["short_positions"][0]["value_base"] == -30000.0


def test_foreign_custody_unverified_excluded(db):
    tenant, portfolio = _seed(db)
    c = _company(db, tenant, "AAPL", isin="US0378331005")
    _position_row(db, tenant, portfolio, c, source="manual")  # sin origen extranjero
    _position_snapshot(db, tenant, portfolio, c, date(2025, 12, 31), 60000)

    result = Modelo720Service().check_thresholds(db, 2025)

    valores = result["categories"]["valores"]
    # 60k reales pero custodia extranjera no verificada → fuera del total.
    assert valores["total_base"] == 0.0
    assert valores["exceeds"] is None
    assert valores["status"] == "desconocido"
    assert result["foreign_unverified"][0]["ticker"] == "AAPL"
    assert result["incomplete"] is True


def test_no_snapshots_at_all_is_unknown(db):
    tenant, portfolio = _seed(db)
    result = Modelo720Service().check_thresholds(db, 2025)
    assert result["categories"]["valores"]["exceeds"] is None
    assert result["categories"]["valores"]["status"] == "desconocido"
    assert result["categories"]["cuentas"]["exceeds"] is None
