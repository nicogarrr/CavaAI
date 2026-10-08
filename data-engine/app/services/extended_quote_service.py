"""Read-only, timestamped Yahoo quotes. No database or stale-on-error fallback."""
from __future__ import annotations

import math
import time
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.services.connectors.yahoo import YahooFinanceClient

SessionName = Literal["pre", "regular", "post", "cerrado"]
SOURCE = "Yahoo Finance (no oficial), retraso posible"


class ExtendedQuote(BaseModel):
    ticker: str
    status: Literal["available", "retrasado", "unavailable"] = "unavailable"
    session: SessionName = "cerrado"
    price_session: SessionName | None = None
    price: float | None = None
    timestamp: int | None = None
    currency: str | None = None
    source: str = SOURCE
    fetched_at: int
    trading_date: str | None = None
    previous_close: float | None = None
    previous_close_timestamp: int | None = None
    change: float | None = None
    change_percent: float | None = None
    regular_close: float | None = None
    regular_close_timestamp: int | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    metrics_timestamp: int | None = None
    metrics_session: str | None = None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value > 0 else None


def _epoch(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def parse_extended_chart(ticker: str, node: dict[str, Any], now: int) -> ExtendedQuote:
    meta = node.get("meta") or {}
    periods = meta.get("currentTradingPeriod") or {}
    bounds: dict[str, tuple[int, int]] = {}
    for name in ("pre", "regular", "post"):
        period = periods.get(name) or {}
        start, end = _epoch(period.get("start")), _epoch(period.get("end"))
        if start is not None and end is not None and end > start:
            bounds[name] = (start, end)
    # Without the exchange's real session bounds, do not guess market hours.
    if "regular" not in bounds:
        return ExtendedQuote(ticker=ticker, fetched_at=now)

    historical: dict[str, list[tuple[int, int]]] = {}
    # On weekends Yahoo may give currentTradingPeriod for the next session,
    # while tradingPeriods dates the returned Friday candles.
    for name in ("pre", "regular", "post"):
        groups = (node.get("meta", {}).get("tradingPeriods") or {}).get(name, [])
        historical[name] = []
        for group in groups:
            for period in group:
                start, end = _epoch(period.get("start")), _epoch(period.get("end"))
                if start is not None and end is not None and end > start:
                    historical[name].append((start, end))

    def session_at(ts: int) -> SessionName:
        for name in ("pre", "regular", "post"):
            intervals = ([bounds[name]] if name in bounds else []) + historical[name]
            if any(start <= ts < end for start, end in intervals):
                return name
        return "cerrado"

    session = session_at(now)
    result = ExtendedQuote(ticker=ticker, fetched_at=now, session=session, currency=meta.get("currency"))
    quotes = (node.get("indicators") or {}).get("quote") or []
    candles = quotes[0] if quotes else {}
    timestamps = node.get("timestamp") or []
    closes = candles.get("close") or []
    points: list[tuple[int, float, int]] = []
    for i, raw in enumerate(timestamps):
        ts = _epoch(raw)
        price = _number(closes[i]) if i < len(closes) else None
        if ts is not None and ts <= now and price is not None:
            points.append((ts, price, i))
    points.sort()
    regular = [p for p in points if session_at(p[0]) == "regular"]
    regular_indices = [
        (ts, i) for i, raw in enumerate(timestamps)
        if (ts := _epoch(raw)) is not None and ts <= now and session_at(ts) == "regular"
    ]
    regular_intervals = [bounds["regular"]] + historical["regular"]

    def is_regular_close(ts: int) -> bool:
        # The last 1m candle or the timestamped closing print, never an
        # arbitrary intraday meta price presented as a session close.
        return any(now >= end and end - 60 <= ts <= end + 60 for _, end in regular_intervals)

    close_candidates = [(ts, price) for ts, price, _ in regular if is_regular_close(ts)]
    regular_time = _epoch(meta.get("regularMarketTime"))
    regular_price = _number(meta.get("regularMarketPrice"))
    if regular_time and regular_time <= now and regular_price is not None and is_regular_close(regular_time):
        close_candidates.append((regular_time, regular_price))
    if close_candidates:
        result.regular_close_timestamp, result.regular_close = max(close_candidates)
    if session != "cerrado":
        selected = points[-1] if points else None
    else:
        closed_points = [p for p in points if session_at(p[0]) == "post" or (session_at(p[0]) == "regular" and is_regular_close(p[0]))]
        selected = closed_points[-1] if closed_points else None
        if result.regular_close_timestamp and (
            selected is None or result.regular_close_timestamp > selected[0]
        ):
            if result.regular_close is not None:
                selected = (result.regular_close_timestamp, result.regular_close, -1)
    if session == "regular":
        result.regular_close = None
        result.regular_close_timestamp = None
    if selected is None:
        return result
    result.timestamp, result.price = selected[0], selected[1]
    result.price_session = session_at(selected[0])
    if selected[2] == -1 and selected[0] == result.regular_close_timestamp:
        result.price_session = "regular"
    timezone = meta.get("exchangeTimezoneName")
    if not timezone:
        return ExtendedQuote(ticker=ticker, fetched_at=now, session=session)
    tz = ZoneInfo(timezone)
    result.trading_date = datetime.fromtimestamp(selected[0], tz).date().isoformat()
    result.status = "retrasado" if session != "cerrado" and now - selected[0] > 1200 else "available"
    result.previous_close = _number(meta.get("previousClose"))
    # Yahoo normally omits the previous close's date. Do not invent it from
    # yesterday (holidays) or assign the current candle's date to it.
    prev_ts = _epoch(meta.get("previousCloseTime"))
    if prev_ts and prev_ts < bounds["regular"][0]:
        result.previous_close_timestamp = prev_ts
    if session != "cerrado" and result.previous_close is not None:
        result.change = result.price - result.previous_close
        result.change_percent = result.change / result.previous_close * 100
    if regular_indices:
        regular_indices.sort()
        last_ts = regular_indices[-1][0]
        covered_period = next((
            (start, end) for start, end in regular_intervals if start <= last_ts < end
        ), None)
        # A complete list of the bars that happen to exist is not complete
        # session coverage. Reject missing opening minutes, internal gaps,
        # and missing tail minutes rather than claim daily extrema.
        covered = False
        if covered_period:
            start, end = covered_period
            expected_last = min(end - 60, max(start, (now // 60) * 60 - 60))
            covered = (
                regular_indices[0][0] == start
                and last_ts >= expected_last
                and all(b[0] - a[0] == 60 for a, b in zip(regular_indices, regular_indices[1:], strict=False))
            )

        def values(key: str) -> list[float]:
            series = candles.get(key) or []
            return [v for _, i in regular_indices if i < len(series) and (v := _number(series[i])) is not None]

        highs, lows = values("high"), values("low")
        # Incomplete OHLC series cannot establish a daily max/min/open.
        first_i = regular_indices[0][1]
        open_series = candles.get("open") or []
        result.open = (
            _number(open_series[first_i])
            if first_i < len(open_series) and any(regular_indices[0][0] == start for start, _ in [bounds["regular"]] + historical["regular"])
            else None
        )
        result.high = max(highs) if covered and len(highs) == len(regular_indices) else None
        result.low = min(lows) if covered and len(lows) == len(regular_indices) else None
        result.metrics_timestamp = regular_indices[-1][0]
        result.metrics_session = datetime.fromtimestamp(regular_indices[-1][0], tz).date().isoformat()
    return result


class ExtendedQuoteService:
    def __init__(self) -> None:
        self.client = YahooFinanceClient()
        self.cache: dict[str, tuple[float, dict[str, Any], int]] = {}

    async def get(self, ticker: str) -> ExtendedQuote:
        ticker = ticker.strip().upper()
        now = int(time.time())
        try:
            cached = self.cache.get(ticker)
            if cached and time.monotonic() - cached[0] < 60:
                node = cached[1]
            else:
                node = await self.client.extended_chart(ticker)
                self.cache = {k: v for k, v in self.cache.items() if time.monotonic() - v[0] < 60}
                self.cache[ticker] = (time.monotonic(), node, int(time.time()))
            # Reclassify each read: cached candles can cross sessions/stale limit.
            return parse_extended_chart(ticker, node, int(time.time())).model_copy(
                update={"fetched_at": self.cache[ticker][2]}
            )
        except Exception:
            self.cache.pop(ticker, None)
            return ExtendedQuote(ticker=ticker, fetched_at=now)


extended_quote_service = ExtendedQuoteService()
