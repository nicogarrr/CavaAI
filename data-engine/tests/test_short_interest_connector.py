"""Tests hermeticos del conector `short_interest` (FINRA corto + VIX Yahoo).

Sin red: `httpx.MockTransport` devuelve respuestas fijas. Cubre parseo,
bordes (vacío, cero, extremos), la busqueda binaria acotada del short interest
FINRA y el enganche minimo en senales (`/risk/signals`).
"""

from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest

from app.api.routes import risk
from app.services.connectors import short_interest as si


def run_async(coroutine):
    return asyncio.run(coroutine)


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


_REGSHO_TEXT = (
    "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\r\n"
    "20240906|A|154791|0|346351|B,Q,N\r\n"
    "20240906|AAPL|30000000|1000|60000000|B,Q,N\r\n"
    "20240906|AA|928063|809|2136276|B,Q,N\r\n"
)


# ---------------- parse_regsho_daily ----------------


def test_parse_regsho_extrae_fila_y_ratio():
    row = si.parse_regsho_daily(_REGSHO_TEXT, "AAPL")
    assert row["symbol"] == "AAPL"
    assert row["date"] == "2024-09-06"
    assert row["short_volume"] == 30_000_000
    assert row["short_exempt_volume"] == 1000
    assert row["total_volume"] == 60_000_000
    assert row["short_volume_ratio"] == pytest.approx(0.5)
    assert row["source"] == "finra_regsho"
    assert row["source_url"].endswith("CNMSshvol20240906.txt")


def test_parse_regsho_case_insensitive():
    assert si.parse_regsho_daily(_REGSHO_TEXT, "aapl")["symbol"] == "AAPL"


def test_parse_regsho_simbolo_ausente_devuelve_none():
    assert si.parse_regsho_daily(_REGSHO_TEXT, "TSLA") is None


def test_parse_regsho_vacio_o_sin_contenido():
    assert si.parse_regsho_daily("", "AAPL") is None
    assert si.parse_regsho_daily("Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market", "AAPL") is None


def test_parse_regsho_lineas_malformadas_se_ignoran():
    text = (
        "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n"
        "basura sin barras\n"
        "20240906|AAPL|no-numerico|0|100|Q\n"
        "20240906|AAPL|5|1|10|Q\n"
    )
    row = si.parse_regsho_daily(text, "AAPL")
    assert row["short_volume"] == 5


def test_parse_regsho_volumen_cero_no_divide_entre_cero():
    text = "20240906|AAPL|0|0|0|Q\n"
    row = si.parse_regsho_daily(text, "AAPL")
    assert row["short_volume_ratio"] is None
    assert row["total_volume"] == 0


def test_parse_regsho_ratio_alto_posible():
    text = "20240906|GME|95|0|100|Q\n"
    assert si.parse_regsho_daily(text, "GME")["short_volume_ratio"] == pytest.approx(0.95)


# ---------------- fetch_short_volume ----------------


def test_fetch_short_volume_mira_hasta_encontrar_el_ultimo_fichero():
    pedidos = []

    def handler(request: httpx.Request) -> httpx.Response:
        pedidos.append(request.url.path)
        if request.url.path.endswith("CNMSshvol20240906.txt"):
            return httpx.Response(200, text=_REGSHO_TEXT, request=request)
        return httpx.Response(404, text="", request=request)

    async def probe():
        async with _client(handler) as client:
            return await si.fetch_short_volume(
                "AAPL", date(2024, 9, 8), client=client, lookback_days=7
            )

    row = run_async(probe())
    assert row["date"] == "2024-09-06"
    # Se probaron 20240908 y 20240907 antes de dar con el fichero del viernes.
    assert len(pedidos) == 3


def test_fetch_short_volume_sin_datos_devuelve_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="", request=request)

    async def probe():
        async with _client(handler) as client:
            return await si.fetch_short_volume(
                "AAPL", date(2024, 9, 8), client=client, lookback_days=2
            )

    assert run_async(probe()) is None


def test_fetch_short_volume_error_de_red_no_lanza():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    async def probe():
        async with _client(handler) as client:
            return await si.fetch_short_volume("AAPL", date(2024, 9, 8), client=client)

    assert run_async(probe()) is None


# ---------------- short interest FINRA (busqueda binaria) ----------------


def _record(code: str, current=1000.0, previous=800.0, avg=200.0, days=None):
    return {
        "symbolCode": code,
        "issueName": f"{code} Inc.",
        "settlementDate": "2026-09-15",
        "currentShortPositionQuantity": current,
        "previousShortPositionQuantity": previous,
        "averageDailyVolumeQuantity": avg,
        "daysToCoverQuantity": days,
        "marketClassCode": "NYSE",
    }


def test_parse_short_interest_normaliza_y_deriva_days_to_cover():
    parsed = si.parse_short_interest_record(_record("GME", current=1000, avg=200, days=None), "GME")
    assert parsed["short_interest"] == 1000
    assert parsed["previous_short_interest"] == 800
    assert parsed["change_pct"] == pytest.approx(0.25)
    assert parsed["days_to_cover"] == pytest.approx(5.0)  # derivado 1000/200
    assert parsed["settlement_date"] == "2026-09-15"
    assert parsed["source"] == "finra_short_interest"


def test_parse_short_interest_simbolo_distinto_devuelve_none():
    assert si.parse_short_interest_record(_record("GME"), "AAPL") is None
    assert si.parse_short_interest_record("no-dict", "GME") is None


def test_parse_short_interest_sin_previo_no_divide_entre_cero():
    parsed = si.parse_short_interest_record(
        _record("GME", current=1000, previous=None, avg=None, days=None), "GME"
    )
    assert parsed["change_pct"] is None
    assert parsed["days_to_cover"] is None
    assert parsed["average_daily_volume"] is None


def test_fetch_short_interest_encuentra_el_ticker_en_pagina():
    dataset = [_record("AAA"), _record("BBB"), _record("GME", current=47), _record("MSFT"), _record("ZZZ")]
    pedidos = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        limit = int(request.url.params.get("limit", "200"))
        pedidos.append(offset)
        return httpx.Response(200, json=dataset[offset : offset + limit], request=request)

    async def probe():
        async with _client(handler) as client:
            return await si.fetch_short_interest("GME", client=client, page_size=2, max_requests=12)

    parsed = run_async(probe())
    assert parsed["symbol"] == "GME"
    assert parsed["short_interest"] == 47
    assert len(pedidos) <= 12


def test_fetch_short_interest_acotado_en_peticiones_con_dataset_grande():
    codes = [f"T{i:05d}" for i in range(2000)]
    dataset = [_record(code) for code in codes]
    pedidos = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        limit = int(request.url.params.get("limit", "200"))
        pedidos.append(offset)
        return httpx.Response(200, json=dataset[offset : offset + limit], request=request)

    async def probe():
        async with _client(handler) as client:
            return await si.fetch_short_interest("T01500", client=client, page_size=100, max_requests=12)

    parsed = run_async(probe())
    assert parsed is not None
    assert parsed["symbol"] == "T01500"
    assert len(pedidos) <= 12  # nunca mas de max_requests peticiones


def test_fetch_short_interest_simbolo_inexistente_devuelve_none():
    dataset = [_record("AAA"), _record("BBB")]

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        limit = int(request.url.params.get("limit", "200"))
        return httpx.Response(200, json=dataset[offset : offset + limit], request=request)

    async def probe():
        async with _client(handler) as client:
            return await si.fetch_short_interest("QQQ", client=client, page_size=1, max_requests=6)

    assert run_async(probe()) is None


def test_fetch_short_interest_error_de_red_no_lanza():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    async def probe():
        async with _client(handler) as client:
            return await si.fetch_short_interest("GME", client=client, page_size=2, max_requests=3)

    assert run_async(probe()) is None


# ---------------- VIX ----------------


def _chart(payload_closes):
    return {
        "chart": {
            "result": [
                {"indicators": {"quote": [{"close": payload_closes}]}}
            ]
        }
    }


def test_parse_vix_extrae_precio_cambio_y_regimen():
    parsed = si.parse_vix_chart(_chart([28.0, 30.0]))
    assert parsed["symbol"] == "^VIX"
    assert parsed["price"] == 30.0
    assert parsed["change"] == 2.0
    assert parsed["change_percent"] == pytest.approx(7.14, rel=1e-4)  # redondeado a 2 decimales
    assert parsed["regime"] == "stress"
    assert parsed["source"] == "yahoo_finance"


def test_parse_vix_payload_malformado_devuelve_none():
    assert si.parse_vix_chart({}) is None
    assert si.parse_vix_chart({"chart": {"result": []}}) is None
    assert si.parse_vix_chart(_chart([15.0])) is None  # sin vela previa
    assert si.parse_vix_chart(_chart([None, None])) is None


def test_fetch_vix_usa_yahoo_y_no_lanza():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "query1.finance.yahoo.com" in request.url.host
        assert "VIX" in str(request.url)
        return httpx.Response(200, json=_chart([12.0, 18.0]), request=request)

    async def probe():
        async with _client(handler) as client:
            return await si.fetch_vix(client=client)

    parsed = run_async(probe())
    assert parsed["price"] == 18.0
    assert parsed["regime"] == "calm"


def test_fetch_vix_http_500_devuelve_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={}, request=request)

    async def probe():
        async with _client(handler) as client:
            return await si.fetch_vix(client=client)

    assert run_async(probe()) is None


def test_vix_regime_bordes():
    assert si.vix_regime(None) == "unknown"
    assert si.vix_regime(-5.0) == "calm"
    assert si.vix_regime(19.99) == "calm"
    assert si.vix_regime(20.0) == "elevated"
    assert si.vix_regime(29.99) == "elevated"
    assert si.vix_regime(30.0) == "stress"
    assert si.vix_regime(80.0) == "stress"


# ---------------- Senales ----------------


def test_stress_signals_sin_datos_no_fabrica_senales():
    assert si.stress_signals() == []
    assert si.stress_signals(vix={"price": 12.0}) == []  # regimen calmado


def test_stress_signals_vix_elevado_y_stress():
    elevado = si.stress_signals(vix={"price": 25.0, "source_url": "u"})
    assert [s["signal"] for s in elevado] == ["vix_elevated"]
    assert elevado[0]["severity"] == "medium"
    assert elevado[0]["threshold"] == si.VIX_ELEVATED

    stress = si.stress_signals(vix={"price": 35.0, "source_url": "u"})
    assert [s["signal"] for s in stress] == ["vix_stress"]
    assert stress[0]["severity"] == "high"


def test_stress_signals_corto_alto_y_days_to_cover():
    senales = si.stress_signals(
        short_volume={"symbol": "GME", "date": "2026-09-15", "short_volume_ratio": 0.62, "source_url": "u"},
        short_interest={
            "symbol": "GME",
            "days_to_cover": 8.5,
            "change_pct": 0.25,
            "settlement_date": "2026-09-15",
            "source_url": "u",
        },
    )
    assert [s["signal"] for s in senales] == [
        "high_short_volume",
        "high_days_to_cover",
        "short_interest_buildup",
    ]
    assert all(s["ticker"] == "GME" for s in senales)
    assert all("detail" in s and "metric_value" in s for s in senales)


def test_stress_signals_por_debajo_del_umbral_no_alerta():
    assert si.stress_signals(
        short_volume={"symbol": "AAPL", "short_volume_ratio": 0.40},
    ) == []
    assert si.stress_signals(
        short_interest={"symbol": "AAPL", "days_to_cover": 1.5, "change_pct": 0.02},
    ) == []


def test_stress_signals_ratio_en_el_umbral_exacto_si_alerta():
    senales = si.stress_signals(
        short_volume={"symbol": "X", "short_volume_ratio": si.SHORT_VOLUME_RATIO_ALERT}
    )
    assert [s["signal"] for s in senales] == ["high_short_volume"]


# ---------------- market_stress_report + enganche en /risk/signals ----------------


def _todo_handler(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    if "cdn.finra.org" in host:
        return httpx.Response(200, text=_REGSHO_TEXT, request=request)
    if "api.finra.org" in host:
        offset = int(request.url.params.get("offset", "0"))
        dataset = [_record("AAPL", current=900, previous=100, avg=50, days=18.0)]
        return httpx.Response(200, json=dataset[offset : offset + 1], request=request)
    return httpx.Response(200, json=_chart([20.0, 33.0]), request=request)


def test_market_stress_report_agrega_vix_y_corto():
    async def probe():
        async with _client(_todo_handler) as client:
            return await si.market_stress_report("AAPL", client=client)

    report = run_async(probe())
    assert report["status"] == "ok"
    assert report["ticker"] == "AAPL"
    assert report["vix"]["regime"] == "stress"
    assert report["short_volume"]["symbol"] == "AAPL"
    assert report["short_interest"]["days_to_cover"] == 18.0
    signals = [s["signal"] for s in report["signals"]]
    assert "vix_stress" in signals
    assert "high_days_to_cover" in signals
    assert "short_interest_buildup" in signals  # +800% de crecimiento


def test_market_stress_report_sin_ticker_solo_mide_vix():
    async def probe():
        async with _client(_todo_handler) as client:
            return await si.market_stress_report(None, client=client)

    report = run_async(probe())
    assert report["ticker"] is None
    assert report["short_volume"] is None
    assert report["short_interest"] is None
    assert report["status"] == "ok"


def test_market_stress_report_degrada_a_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    async def probe():
        async with _client(handler) as client:
            return await si.market_stress_report("AAPL", client=client)

    report = run_async(probe())
    assert report["status"] == "unavailable"
    assert report["signals"] == []


def test_risk_signals_engancha_al_conector(monkeypatch):
    async def fake_report(ticker=None, *, client=None):
        return {"status": "ok", "ticker": ticker, "signals": [{"signal": "vix_stress"}]}

    monkeypatch.setattr(risk.short_interest, "market_stress_report", fake_report)
    result = asyncio.run(risk.market_stress_signals("AAPL"))
    assert result["status"] == "ok"
    assert result["ticker"] == "AAPL"
    assert result["signals"][0]["signal"] == "vix_stress"
