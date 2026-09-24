"""Contratos de GET /api/market/quote/{symbol}: shape Finnhub vía Yahoo.

El endpoint revive el fallback del frontend para mercados no-US. Nunca
inventa datos: payload incompleto -> None -> 404 honesto.
"""

import httpx
import pytest
from fastapi import HTTPException

from app.api.routes import market


def _payload(closes=(100.0, 101.0, 102.5), opens=(99.0, 100.5, 101.0),
             highs=(101.0, 102.0, 103.0), lows=(98.0, 100.0, 101.0),
             previous_close=100.0):
    return {
        "chart": {
            "result": [
                {
                    "meta": {"chartPreviousClose": previous_close},
                    "indicators": {
                        "quote": [
                            {
                                "close": list(closes),
                                "open": list(opens),
                                "high": list(highs),
                                "low": list(lows),
                            }
                        ]
                    },
                }
            ]
        }
    }


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _Client:
    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc

    def get(self, *args, **kwargs):
        if self._exc:
            raise self._exc
        return self._resp


def test_fetch_yahoo_quote_builds_finnhub_shape():
    client = _Client(resp=_Resp(200, _payload()))
    out = market._fetch_yahoo_quote(client, "SAN.MC")
    assert out == {
        "c": 102.5,
        "d": pytest.approx(1.5),
        "dp": pytest.approx(1.5 / 101.0 * 100),
        "h": 103.0,
        "l": 101.0,
        "o": 101.0,
        "pc": 101.0,
    }


def test_fetch_yahoo_quote_single_close_uses_meta_previous():
    client = _Client(resp=_Resp(200, _payload(closes=(105.0,), previous_close=100.0)))
    out = market._fetch_yahoo_quote(client, "ITX.MC")
    assert out is not None
    assert out["c"] == 105.0
    assert out["pc"] == 100.0


def test_fetch_yahoo_quote_empty_closes_returns_none():
    client = _Client(resp=_Resp(200, _payload(closes=(None, None))))
    assert market._fetch_yahoo_quote(client, "FAKE") is None


def test_fetch_yahoo_quote_http_error_returns_none():
    client = _Client(exc=httpx.ConnectError("down"))
    assert market._fetch_yahoo_quote(client, "AAPL") is None


def test_fetch_yahoo_quote_non_200_returns_none():
    client = _Client(resp=_Resp(429, {}))
    assert market._fetch_yahoo_quote(client, "AAPL") is None


def test_market_quote_404_when_no_data(monkeypatch):
    monkeypatch.setattr(market, "_fetch_yahoo_quote", lambda client, symbol: None)
    with pytest.raises(HTTPException) as exc:
        market.market_quote("NOEXISTE")
    assert exc.value.status_code == 404


def test_market_quote_caches_result(monkeypatch):
    calls = []

    def fake_fetch(client, symbol):
        calls.append(symbol)
        return {"c": 1.0, "d": 0.0, "dp": 0.0, "h": 1.0, "l": 1.0, "o": 1.0, "pc": 1.0}

    monkeypatch.setattr(market, "_fetch_yahoo_quote", fake_fetch)
    ticker = "CACHE-TEST-XYZ"
    market._quote_cache.pop(ticker, None)
    first = market.market_quote(ticker)
    second = market.market_quote(ticker)
    assert first == second
    assert calls == [ticker]
