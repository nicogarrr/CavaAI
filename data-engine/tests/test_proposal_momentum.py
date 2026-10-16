from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models.entities import Company, MarketPrice
from app.services.proposal_momentum import load_momentum

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Company(id=1, ticker='AAPL', name='Synthetic', exchange='NASDAQ', currency='USD', company_type='large_cap', valuation_model='dcf'))
        session.commit()
        yield session
    engine.dispose()


def bar(db, ago, price, source='yfinance'):
    db.add(MarketPrice(company_id=1, date=NOW.date()-timedelta(days=ago), adj_close=price, source=source))
    db.commit()


def test_returns_dated_adjusted_return_without_writes(db):
    bar(db, 31, Decimal(100))
    bar(db, 1, Decimal(120))
    result = load_momentum(db, 'AAPL', NOW)
    window = result['ventanas'][0]
    assert window['retorno'] == '0.2'
    assert window['fecha_inicio'] == (NOW.date()-timedelta(days=31)).isoformat()
    assert window['fecha_fin'] == (NOW.date()-timedelta(days=1)).isoformat()
    assert window['fuente'] == 'yfinance'
    assert all(w['retorno'] is None for w in result['ventanas'][1:])
    assert not db.new and not db.dirty


@pytest.mark.parametrize('source,ago,price', [('seed',1,120),('spot',1,120),('yfinance',8,120),('yfinance',1,None),('yfinance',1,0)])
def test_missing_stale_seed_or_nonadjusted_is_never_momentum(db,source,ago,price):
    bar(db,31,100)
    bar(db,ago,price,source)
    result=load_momentum(db,'AAPL',NOW)
    assert result['ventanas']==[]
    assert result['aviso']=='sin_serie_ajustada_reciente'


def test_future_bar_never_enters_context(db):
    bar(db,31,100);bar(db,1,120);bar(db,-1,999)
    assert load_momentum(db,'AAPL',NOW)['ventanas'][0]['retorno']=='0.2'


def test_far_anchor_not_mislabeled_as_30_days(db):
    bar(db,41,100);bar(db,1,120)
    assert load_momentum(db,'AAPL',NOW)['ventanas'][0]['retorno'] is None
