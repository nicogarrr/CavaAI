"""Historical stress contracts: never synthesize a missing constituent."""
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, Position
from app.services import historical_stress_service as stress


def series(year=2020):
    start = date(year - 1, 12, 24)
    end = date(year + 1, 3, 1)
    return {start + timedelta(days=i): 100.0 for i in range((end-start).days + 1)
            if (start + timedelta(days=i)).weekday() < 5}


def test_return_drawdown_and_recovery():
    prices = series()
    prices[date(2020, 2, 3)] = 120
    prices[date(2020, 3, 2)] = 60
    prices[date(2021, 2, 1)] = 121
    result = stress.calculate_window(prices, 2020)
    assert result['status'] == 'calculated'
    assert result['return'] == 0
    assert result['max_drawdown'] == -0.5
    assert result['peak_date'] == '2020-02-03'
    assert result['trough_date'] == '2020-03-02'
    assert result['recovery_date'] == '2021-02-01'
    assert result['recovery_days'] == (date(2021, 2, 1) - date(2020, 2, 3)).days


def test_recovery_during_crisis_year():
    prices = series()
    prices[date(2020, 3, 2)] = 70
    result = stress.calculate_window(prices, 2020)
    assert result['recovery_date'] == '2020-03-03'


def test_no_drawdown_is_zero_not_missing():
    result = stress.calculate_window(series(), 2020)
    assert result['max_drawdown'] == 0
    assert result['recovery_days'] == 0


def test_new_ipo_and_unadjusted_missing_have_no_scenario():
    assert stress.calculate_window({}, 2008)['status'] == 'SIN_DATOS'
    assert stress.calculate_window({d: p for d, p in series().items() if d.year == 2020}, 2020)['status'] == 'SIN_DATOS'


def test_missing_end_and_interior_gaps_fail_closed():
    prices = series()
    gap = {d: p for d, p in prices.items() if not date(2020, 5, 1) <= d <= date(2020, 6, 1)}
    assert stress.calculate_window(gap, 2020)['reason'] == 'history_gaps'
    assert stress.calculate_window({d: p for d, p in prices.items() if d < date(2020, 12, 1)}, 2020)['status'] == 'SIN_DATOS'


def test_recovery_censoring_and_gap():
    prices = series()
    prices[date(2020, 2, 3)] = 150
    result = stress.calculate_window(prices, 2020)
    assert result['recovery_date'] is None
    assert result['recovery_status'] == 'not_recovered'
    prices[date(2022, 1, 3)] = 160
    assert stress.calculate_window(prices, 2020)['recovery_status'] == 'history_gaps'


def test_invalid_price_fails_closed():
    prices = series()
    prices[date(2020, 3, 2)] = float('nan')
    assert stress.calculate_window(prices, 2020)['status'] == 'SIN_DATOS'


@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info['tenant_id'] = 'tenant-test'
        for ticker, value in [('AAA', 75), ('BBB', 25)]:
            company = Company(ticker=ticker, name=ticker, exchange='NASDAQ', currency='USD', sector='S', industry='I',
                              company_type='holding', valuation_model='unassigned', special_sources=[], special_risks=[], factor_tags=[])
            session.add(company)
            session.flush()
            session.add(Position(company_id=company.id, quantity=Decimal('1'), market_value_base=Decimal(value),
                                 base_currency='EUR', currency='USD', as_of=date(2026, 10, 13)))
        session.commit()
        yield session
    engine.dispose()


def history(prices):
    return {'prices': prices, 'source': 'Yahoo Finance', 'source_url': 'https://query1.finance.yahoo.com',
            'fetched_at': '2026-10-13T18:00:00+00:00', 'currency': 'USD'}


def test_portfolio_buy_hold_not_rebalanced(db, monkeypatch):
    async def load(ticker):
        prices = series()
        prices[date(2020, 12, 31)] = 200 if ticker == 'AAA' else 50
        return history(prices)
    monkeypatch.setattr(stress, 'load_history', load)
    import asyncio
    report = asyncio.run(stress.HistoricalStressService().build(db))
    result = report['portfolio'][1]
    assert result['status'] == 'calculated'
    assert result['return'] == pytest.approx(0.625)
    assert report['data_kind'] == 'INFERIDO'
    assert report['companies'][0]['weight'] == .75
    assert report['companies'][0]['weight_as_of'] == '2026-10-13'


def test_missing_position_not_silently_renormalized(db, monkeypatch):
    async def load(ticker):
        return history(series() if ticker == 'AAA' else {})
    monkeypatch.setattr(stress, 'load_history', load)
    import asyncio
    report = asyncio.run(stress.HistoricalStressService().build(db))
    assert report['portfolio'][1]['status'] == 'SIN_DATOS'
    assert report['portfolio'][1]['missing_tickers'] == ['BBB']
    assert report['companies'][0]['windows'][1]['status'] == 'calculated'


def _add_company(db, ticker, exchange, currency, value=50):
    company = Company(ticker=ticker, name=ticker, exchange=exchange, currency=currency, sector='S', industry='I',
                      company_type='holding', valuation_model='unassigned', special_sources=[], special_risks=[], factor_tags=[])
    db.add(company)
    db.flush()
    db.add(Position(company_id=company.id, quantity=Decimal('1'), market_value_base=Decimal(value),
                    base_currency='EUR', currency=currency, as_of=date(2026, 10, 13)))
    db.commit()


def test_non_us_position_requests_real_listing_symbol(db, monkeypatch):
    _add_company(db, 'SAP', 'XETRA', 'EUR')
    asked = []
    async def load(symbol):
        asked.append(symbol)
        prices = series()
        return {**history(prices), 'currency': 'EUR' if symbol == 'SAP.DE' else 'USD'}
    monkeypatch.setattr(stress, 'load_history', load)
    import asyncio
    report = asyncio.run(stress.HistoricalStressService().build(db, ticker='SAP'))
    assert 'SAP.DE' in asked and 'SAP' not in asked
    assert report['companies'][0]['symbol'] == 'SAP.DE'
    assert report['companies'][0]['windows'][1]['status'] == 'calculated'


def test_unmapped_non_us_symbol_is_sin_datos_not_a_substitute(db, monkeypatch):
    _add_company(db, 'ZZZ', 'UNMAPPED-EXCHANGE', 'EUR')
    asked = []
    async def load(symbol):
        asked.append(symbol)
        return history(series())
    monkeypatch.setattr(stress, 'load_history', load)
    import asyncio
    report = asyncio.run(stress.HistoricalStressService().build(db))
    assert 'ZZZ' not in asked
    assert report['portfolio'][1]['status'] == 'SIN_DATOS'
    assert 'ZZZ' in report['portfolio'][1]['missing_tickers']
    zzz = next(c for c in report['companies'] if c['ticker'] == 'ZZZ')
    assert zzz['history_failure'] == 'no_safe_symbol'
    assert zzz['windows'][1]['reason'] == 'no_safe_symbol'


def test_currency_mismatch_is_rejected(db, monkeypatch):
    _add_company(db, 'SAP', 'XETRA', 'EUR')
    async def load(symbol):
        return history(series())  # Yahoo devuelve USD: otra linea
    monkeypatch.setattr(stress, 'load_history', load)
    import asyncio
    report = asyncio.run(stress.HistoricalStressService().build(db, ticker='SAP'))
    window = report['companies'][0]['windows'][1]
    assert window['status'] == 'SIN_DATOS' and window['reason'] == 'currency_mismatch'


def test_provider_error_reason_is_distinct_from_missing_history(db, monkeypatch):
    async def load(symbol):
        raise httpx.ConnectError('unavailable')
    monkeypatch.setattr(stress, 'load_history', load)
    import asyncio
    report = asyncio.run(stress.HistoricalStressService().build(db, ticker='AAA'))
    assert report['companies'][0]['windows'][1]['reason'] == 'provider_error'


def test_provider_outage_and_empty_portfolio(db, monkeypatch):
    async def load(ticker):
        raise httpx.ConnectError('unavailable')
    monkeypatch.setattr(stress, 'load_history', load)
    import asyncio
    report = asyncio.run(stress.HistoricalStressService().build(db, ticker='AAA'))
    assert report['companies'][0]['windows'][1]['status'] == 'SIN_DATOS'
    assert report['portfolio'] == []
    assert report['companies'][0]['source_url'] is None


def test_missing_valuation_blocks_portfolio(db, monkeypatch):
    from sqlalchemy import select
    position = db.scalars(select(Position)).first()
    position.market_value_base = None
    db.commit()
    async def load(ticker):
        return history(series())
    monkeypatch.setattr(stress, 'load_history', load)
    import asyncio
    report = asyncio.run(stress.HistoricalStressService().build(db))
    assert report['portfolio'][1]['status'] == 'SIN_DATOS'
    assert 'AAA' in report['portfolio'][1]['missing_tickers']
