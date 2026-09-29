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
        "ct": None,  # sin timestamps en el payload: null honesto, no inventado
        "cd": None,
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


class _RecordingClient:
    def __init__(self, resp):
        self._resp = resp
        self.urls: list[str] = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return self._resp


def test_yahoo_chart_symbol_maps_us_share_class_dot_to_dash():
    # Yahoo nombra las clases US con guion: BRK.B -> BRK-B (verificado contra
    # la chart API: BRK-B devuelve datos, BRK.B 404).
    assert market._yahoo_chart_symbol("BRK.B") == "BRK-B"
    assert market._yahoo_chart_symbol("BF.A") == "BF-A"


def test_yahoo_chart_symbol_keeps_exchange_suffixes_and_plain_tickers():
    # Sufijos de bolsa (dos letras) y tickers pelados no se tocan.
    assert market._yahoo_chart_symbol("TEF.MC") == "TEF.MC"
    assert market._yahoo_chart_symbol("ASML.AS") == "ASML.AS"
    assert market._yahoo_chart_symbol("AAPL") == "AAPL"


def test_quote_requests_dashed_symbol_for_share_class():
    client = _RecordingClient(_Resp(200, _payload()))
    out = market._fetch_yahoo_quote(client, "BRK.B")
    assert out is not None
    assert client.urls == [f"{market._YAHOO_CHART_URL}/BRK-B"]


def _payload_con_velas(closes, timestamps, tz="Europe/Madrid"):
    payload = _payload(closes=closes)
    result = payload["chart"]["result"][0]
    result["timestamp"] = list(timestamps)
    result["meta"]["exchangeTimezoneName"] = tz
    return payload


def test_fetch_yahoo_quote_devuelve_fecha_de_la_vela_del_cierre():
    # 2026-09-28 09:00 UTC y 2026-09-29 09:00 UTC: la fecha publicada es la
    # de la vela del ultimo cierre NO NULO, no la del ultimo timestamp.
    payload = _payload_con_velas(
        closes=(100.0, 102.5, None),
        timestamps=(1790586000, 1790672400, 1790758800),
    )
    out = market._fetch_yahoo_quote(_Client(resp=_Resp(200, payload)), "SAN.MC")
    assert out["c"] == 102.5
    assert out["ct"] == 1790672400
    assert out["cd"] == "2026-09-29"  # Europe/Madrid


def test_fetch_yahoo_quote_fecha_en_zona_del_mercado():
    # 2026-09-29 22:30 UTC = 2026-09-30 00:30 en Europe/Madrid, pero
    # 2026-09-29 en America/New_York: la fecha sigue al mercado.
    payload = _payload_con_velas(
        closes=(200.0,),
        timestamps=(1790721000,),
        tz="America/New_York",
    )
    out = market._fetch_yahoo_quote(_Client(resp=_Resp(200, payload)), "AAPL")
    assert out["cd"] == "2026-09-29"


def test_fetch_yahoo_quote_timestamps_cortos_no_rompen():
    payload = _payload_con_velas(closes=(100.0, 102.5), timestamps=(1790586000,))
    out = market._fetch_yahoo_quote(_Client(resp=_Resp(200, payload)), "SAN.MC")
    assert out["c"] == 102.5
    assert out["ct"] is None
    assert out["cd"] is None


def test_fetch_yahoo_quote_cd_fail_closed_sin_zona_valida():
    # 2026-09-29 23:30 UTC: en America/New_York seria 29, en Asia/Tokyo 30.
    # Sin zona valida NO se publica fecha (ct si, cd None): mejor sin fecha
    # que con la fecha del dia equivocado.
    for tz in (None, "Zona/Inventada"):
        payload = _payload_con_velas(closes=(200.0,), timestamps=(1790724600,), tz=tz)
        result = payload["chart"]["result"][0]
        if tz is None:
            result["meta"].pop("exchangeTimezoneName", None)
        out = market._fetch_yahoo_quote(_Client(resp=_Resp(200, payload)), "AAPL")
        assert out["c"] == 200.0
        assert out["ct"] == 1790724600
        assert out["cd"] is None
