"""Punto 5/6: backend macro del BCE via SDW (gratuito, sin clave)."""

import asyncio
from decimal import Decimal

from app.services.connectors.ecb import ECBSDWClient, parse_sdw_csv

CSV_TWO = (
    "KEY,FREQ,TIME_PERIOD,OBS_VALUE,UNIT\n"
    "FM.B.U2.EUR.4F.KR.MRR_FR.LEV,B,2026-06-17,2.4,PCPA\n"
    "FM.B.U2.EUR.4F.KR.MRR_FR.LEV,B,2026-09-16,2.65,PCPA\n"
)

CSV_GAPS = (
    "KEY,FREQ,TIME_PERIOD,OBS_VALUE,UNIT\n"
    "X.Y,A,2024,1.5,PCPA\n"
    "X.Y,A,,2.0,PCPA\n"
    "X.Y,A,2025,,PCPA\n"
    "X.Y,A,2026,not-a-number,PCPA\n"
    "X.Y,A,2027,NaN,PCPA\n"
    "X.Y,A,2028,Infinity,PCPA\n"
)


def test_parse_sdw_csv_two_points():
    points = parse_sdw_csv(CSV_TWO, "ecb_mrr", "Tipo principal", "%")
    assert len(points) == 2
    assert points[0].date == "2026-06-17" and points[0].value == Decimal("2.4")
    assert points[1].date == "2026-09-16" and points[1].value == Decimal("2.65")
    assert points[1].indicator == "ecb_mrr" and points[1].unit == "%"


def test_parse_sdw_csv_skips_garbage_rows():
    points = parse_sdw_csv(CSV_GAPS, "x", "X", "%")
    assert [p.date for p in points] == ["2024"]


class _FakeClient:
    def __init__(self, text_by_key):
        self.text_by_key = text_by_key
        self.calls = []

    async def get(self, url, params=None):
        self.calls.append(url)
        key = url.rsplit("/", 1)[-1]
        text = self.text_by_key.get(key)
        if text is None:
            raise RuntimeError("SDW down")

        class _Resp:
            def raise_for_status(self):
                pass

            @property
            def text(self):
                return text

        return _Resp()


def test_macro_points_skips_failed_series():
    from app.services.connectors.ecb import ECB_MACRO_SERIES

    dfr_key = ECB_MACRO_SERIES["ecb_dfr"][0].rsplit("/", 1)[-1]
    fake = _FakeClient({dfr_key: CSV_TWO})
    client = ECBSDWClient(client=fake)
    points = asyncio.run(client.macro_points(last=2))
    # Solo la serie DFR respondio; el resto se degrada en silencio:
    assert points and all(p.indicator == "ecb_dfr" for p in points)
    assert len(fake.calls) == len(ECB_MACRO_SERIES)


def test_route_shape_and_change():
    from app.api.routes import macro

    class _StubSDW:
        async def macro_points(self, *, last=2):
            return parse_sdw_csv(CSV_TWO, "ecb_mrr", "Tipo principal", "%")

    macro._cache.clear()
    macro.ECBSDWClient = _StubSDW
    out = asyncio.run(macro.ecb_macro())
    assert out["cached"] is False
    assert len(out["items"]) == 1
    item = out["items"][0]
    assert item["source"] == "ecb" and item["indicator"] == "ecb_mrr"
    assert item["value"] == 2.65
    assert item["previousValue"] == 2.4
    assert item["change"] == 0.25
    # Segunda llamada: cache
    out2 = asyncio.run(macro.ecb_macro())
    assert out2["cached"] is True
