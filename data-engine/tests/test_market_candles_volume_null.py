"""F318: /api/market/candles conserva volumen desconocido como None.

Yahoo puede devolver cierre sin volumen; fabricar 0.0 presentaba un dato
inexistente como conocido y arrastraba las medias del análisis técnico a 0/0.
"""

from unittest.mock import Mock

from app.api.routes.market import _fetch_yahoo_candles


def _response(volumes):
    resp = Mock()
    resp.status_code = 200
    resp.json.return_value = {
        "chart": {
            "result": [{
                "timestamp": [1000, 2000, 3000],
                "indicators": {
                    "quote": [{
                        "close": [10.0, 11.0, 12.0],
                        "open": [10.0, 11.0, 12.0],
                        "high": [10.5, 11.5, 12.5],
                        "low": [9.5, 10.5, 11.5],
                        "volume": volumes,
                    }]
                },
            }]
        }
    }
    return resp


def test_candles_unknown_volume_stays_null():
    client = Mock()
    client.get.return_value = _response([1500, None, 1700])
    data = _fetch_yahoo_candles(client, "SAN.MC", 0, 4000, "1d")
    assert data is not None
    assert data["v"] == [1500.0, None, 1700.0]
    assert data["c"] == [10.0, 11.0, 12.0]


def test_candles_all_volumes_unknown_still_serves_prices():
    client = Mock()
    client.get.return_value = _response([None, None, None])
    data = _fetch_yahoo_candles(client, "SAN.MC", 0, 4000, "1d")
    assert data is not None
    assert data["v"] == [None, None, None]
