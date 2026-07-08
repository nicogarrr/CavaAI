import pandas as pd
import pytest

from modules import return_engine


@pytest.fixture
def prices():
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    return pd.DataFrame({"AAA": [100, 110, 121, 121, 133.1]}, index=dates)


def test_buy_only_twr_matches_price_return(monkeypatch, prices):
    monkeypatch.setattr(return_engine, "_fetch_prices", lambda symbols, start, end=None: prices)
    monkeypatch.setattr(return_engine, "_period_start", lambda period: prices.index[0])

    result = return_engine.compute_portfolio_returns(
        transactions=[{"symbol": "AAA", "type": "buy", "quantity": 1, "price": 100, "date": "2024-01-01"}],
        period="1y",
    )

    assert "error" not in result
    assert result["twr"] == pytest.approx(0.331, abs=1e-6)


def test_sell_partial_keeps_time_weighted_return(monkeypatch, prices):
    monkeypatch.setattr(return_engine, "_fetch_prices", lambda symbols, start, end=None: prices)
    monkeypatch.setattr(return_engine, "_period_start", lambda period: prices.index[0])

    result = return_engine.compute_portfolio_returns(
        transactions=[
            {"symbol": "AAA", "type": "buy", "quantity": 2, "price": 100, "date": "2024-01-01"},
            {"symbol": "AAA", "type": "sell", "quantity": 1, "price": 121, "date": "2024-01-03"},
        ],
        period="1y",
    )

    assert "error" not in result
    assert result["nav"][-1] > 0
    assert result["twr"] > 0


def test_symbol_only_returns_equal_weight_history(monkeypatch, prices):
    monkeypatch.setattr(return_engine, "_fetch_prices", lambda symbols, start, end=None: prices)
    monkeypatch.setattr(return_engine, "_period_start", lambda period: prices.index[0])

    result = return_engine.compute_portfolio_returns(symbols=["AAA"], period="1y")

    assert "error" not in result
    assert result["nav"][0] > 100
    assert result["twr"] > 0
