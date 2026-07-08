"""Portfolio return engine: transactions to daily NAV and TWR."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf


def _period_start(period: str) -> pd.Timestamp:
    today = pd.Timestamp.utcnow().normalize().tz_localize(None)
    mapping = {
        "1mo": pd.DateOffset(months=1),
        "3mo": pd.DateOffset(months=3),
        "6mo": pd.DateOffset(months=6),
        "1y": pd.DateOffset(years=1),
        "2y": pd.DateOffset(years=2),
        "3y": pd.DateOffset(years=3),
        "5y": pd.DateOffset(years=5),
    }
    return today - mapping.get(period, pd.DateOffset(years=2))


def _parse_date(value) -> pd.Timestamp:
    if isinstance(value, datetime):
        return pd.Timestamp(value).tz_localize(None)
    return pd.Timestamp(value).tz_localize(None)


def _fetch_prices(symbols: list[str], start: pd.Timestamp, end: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    end = end or pd.Timestamp.utcnow().normalize().tz_localize(None) + pd.Timedelta(days=1)
    data = yf.download(
        tickers=" ".join(symbols),
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=False,
    )
    if data.empty:
        return pd.DataFrame()
    if len(symbols) == 1:
        close = data["Close"].to_frame(symbols[0]) if "Close" in data else pd.DataFrame()
    else:
        close = pd.DataFrame({sym: data[sym]["Close"] for sym in symbols if sym in data and "Close" in data[sym]})
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.dropna(how="all").ffill()


def compute_portfolio_returns(
    transactions: Optional[list[dict]] = None,
    symbols: Optional[list[str]] = None,
    period: str = "2y",
) -> dict:
    transactions = transactions or []
    symbols = [s.upper().strip() for s in (symbols or []) if s.strip()]
    if transactions:
        tx_symbols = [str(t.get("symbol", "")).upper().strip() for t in transactions]
        symbols = sorted({*symbols, *[s for s in tx_symbols if s]})
    if not symbols:
        return {"error": "No symbols or transactions supplied"}

    requested_start = _period_start(period)
    tx_dates = [_parse_date(t["date"]) for t in transactions if t.get("date")]
    price_start = min([requested_start, *tx_dates]) if tx_dates else requested_start
    prices = _fetch_prices(symbols, price_start)
    if prices.empty:
        return {"error": "Insufficient price history for portfolio returns"}

    dates = prices.index[prices.index >= requested_start]
    if len(dates) < 2:
        return {"error": "Insufficient price history for portfolio returns"}

    tx_frame = pd.DataFrame(transactions)
    if not tx_frame.empty:
        tx_frame["symbol"] = tx_frame["symbol"].str.upper().str.strip()
        tx_frame["date"] = pd.to_datetime(tx_frame["date"]).dt.tz_localize(None)
        tx_frame["quantity"] = pd.to_numeric(tx_frame["quantity"], errors="coerce").fillna(0.0)
        tx_frame["price"] = pd.to_numeric(tx_frame["price"], errors="coerce").fillna(0.0)

    cash = 0.0
    shares = {symbol: 0.0 for symbol in symbols}
    nav_values: list[float] = []
    flow_values: list[float] = []

    all_dates = prices.index
    for date in all_dates:
        day_flow = 0.0
        if not tx_frame.empty:
            day_txs = tx_frame[tx_frame["date"].dt.normalize() == date.normalize()]
            for _, tx in day_txs.iterrows():
                symbol = tx["symbol"]
                qty = float(tx["quantity"])
                price = float(tx["price"])
                amount = qty * price
                if tx["type"] == "buy":
                    shares[symbol] = shares.get(symbol, 0.0) + qty
                    day_flow += amount
                elif tx["type"] == "sell":
                    shares[symbol] = shares.get(symbol, 0.0) - qty
                    cash += amount

        market_value = 0.0
        for symbol, qty in shares.items():
            if symbol in prices.columns and np.isfinite(prices.loc[date, symbol]):
                market_value += qty * float(prices.loc[date, symbol])
        nav_values.append(max(0.0, market_value + cash))
        flow_values.append(day_flow)

    nav = pd.Series(nav_values, index=all_dates, dtype=float).loc[dates]
    flows = pd.Series(flow_values, index=all_dates, dtype=float).loc[dates]
    if transactions and nav.max() <= 0:
        return {"error": "Portfolio NAV is zero for the selected period"}

    if not transactions:
        norm_prices = prices.loc[dates, symbols].dropna(how="all").ffill()
        equal_returns = norm_prices.pct_change().dropna().mean(axis=1)
        nav = (1.0 + equal_returns).cumprod() * 100.0
        flows = pd.Series(0.0, index=nav.index)

    previous_nav = nav.shift(1)
    daily_returns = ((nav - flows) / previous_nav.replace(0, np.nan) - 1.0).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    twr = float((1.0 + daily_returns).prod() - 1.0)

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in nav.index],
        "nav": [round(float(v), 6) for v in nav.values],
        "daily_returns": [round(float(v), 8) for v in daily_returns.values],
        "twr": round(twr, 8),
        "start_date": nav.index[0].strftime("%Y-%m-%d"),
        "end_date": nav.index[-1].strftime("%Y-%m-%d"),
    }
