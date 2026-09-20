"""Hermetic tests: interchangeable screener quote/profile vendors (Finnhub ↔ Yahoo).

No network: all HTTP is faked. Covers the vendor Protocol registry, the
per-vendor normalization, the Finnhub default (unchanged behaviour) and the
unknown-vendor fallback.
"""

from __future__ import annotations

import pytest

from app.api.routes import screeners
from app.api.routes.screeners import (
    DEFAULT_SCREENER_VENDOR,
    SCREEN_VENDORS,
    FinnhubScreenVendor,
    YahooScreenVendor,
    _fetch_profile,
    _fetch_quote,
    resolve_screener_vendor,
)


class _FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _FakeClient:
    """Minimal httpx.Client stub: routes by URL substring."""

    def __init__(self, routes: dict[str, _FakeResponse]) -> None:
        self._routes = routes
        self.calls: list[str] = []

    def get(self, url: str, **kwargs):
        self.calls.append(url)
        for marker, response in self._routes.items():
            if marker in url:
                return response
        return _FakeResponse({}, status_code=404)


@pytest.fixture(autouse=True)
def _clean_caches():
    screeners._real_quote_cache.clear()
    screeners._real_profile_cache.clear()
    yield
    screeners._real_quote_cache.clear()
    screeners._real_profile_cache.clear()


def test_registry_has_both_vendors_and_finnhub_default():
    assert set(SCREEN_VENDORS) == {"finnhub", "yahoo"}
    assert DEFAULT_SCREENER_VENDOR == "finnhub"
    assert isinstance(SCREEN_VENDORS["finnhub"], FinnhubScreenVendor)
    assert isinstance(SCREEN_VENDORS["yahoo"], YahooScreenVendor)
    assert SCREEN_VENDORS["finnhub"].source_label == "finnhub_free"
    assert SCREEN_VENDORS["yahoo"].source_label == "yahoo_finance"


def test_resolve_vendor_falls_back_to_finnhub():
    assert resolve_screener_vendor(None).name == "finnhub"
    assert resolve_screener_vendor("").name == "finnhub"
    assert resolve_screener_vendor("no-such-vendor").name == "finnhub"
    assert resolve_screener_vendor("YAHOO").name == "yahoo"
    assert resolve_screener_vendor(" Finnhub ").name == "finnhub"


def test_finnhub_quote_normalization():
    client = _FakeClient(
        {"/quote": _FakeResponse({"c": 150.0, "d": 2.0, "dp": 1.35, "pc": 148.0, "v": 1000, "t": 123})}
    )
    quote = FinnhubScreenVendor().fetch_quote(client, "AAPL")
    assert quote == {
        "price": 150.0,
        "change": 2.0,
        "changePercent": 1.35,
        "volume": 1000.0,
        "prevClose": 148.0,
        "asOf": 123,
    }


def test_finnhub_quote_rejects_zero_price():
    client = _FakeClient({"/quote": _FakeResponse({"c": 0})})
    assert FinnhubScreenVendor().fetch_quote(client, "AAA") is None


def test_finnhub_profile_normalization():
    client = _FakeClient(
        {
            "/stock/profile2": _FakeResponse(
                {
                    "ticker": "AAPL",
                    "name": "Apple Inc",
                    "marketCapitalization": 3000.5,
                    "finnhubIndustry": "Technology",
                    "exchange": "NASDAQ",
                }
            )
        }
    )
    profile = FinnhubScreenVendor().fetch_profile(client, "AAPL")
    assert profile == {
        "name": "Apple Inc",
        "marketCap": pytest.approx(3000.5 * 1_000_000.0),
        "sector": "Technology",
        "exchange": "NASDAQ",
    }


def test_yahoo_quote_normalization():
    client = _FakeClient(
        {
            "chart": _FakeResponse(
                {
                    "chart": {
                        "result": [
                            {
                                "timestamp": [10, 20],
                                "meta": {"chartPreviousClose": 148.0},
                                "indicators": {
                                    "quote": [
                                        {"close": [148.0, 150.0], "volume": [900, 1000]}
                                    ]
                                },
                            }
                        ]
                    }
                }
            )
        }
    )
    quote = YahooScreenVendor().fetch_quote(client, "AAPL")
    assert quote["price"] == pytest.approx(150.0)
    assert quote["change"] == pytest.approx(2.0)
    assert quote["changePercent"] == pytest.approx(2.0 / 148.0 * 100)
    assert quote["volume"] == pytest.approx(1000.0)
    assert quote["prevClose"] == pytest.approx(148.0)
    assert quote["asOf"] == 20


def test_yahoo_quote_rejects_garbage():
    client = _FakeClient({"chart": _FakeResponse({"chart": {}})})
    assert YahooScreenVendor().fetch_quote(client, "AAPL") is None


def test_yahoo_has_no_profile():
    client = _FakeClient({})
    assert YahooScreenVendor().fetch_profile(client, "AAPL") is None


def test_fetch_wrappers_dispatch_per_vendor_with_isolated_caches():
    finnhub = _FakeClient(
        {"/quote": _FakeResponse({"c": 150.0, "d": 1.0, "dp": 0.5, "pc": 149.0, "v": 5, "t": 1})}
    )
    yahoo = _FakeClient(
        {
            "chart": _FakeResponse(
                {
                    "chart": {
                        "result": [
                            {
                                "timestamp": [7],
                                "meta": {},
                                "indicators": {"quote": [{"close": [99.0], "volume": [3]}]},
                            }
                        ]
                    }
                }
            )
        }
    )
    assert _fetch_quote(finnhub, "AAPL")["price"] == pytest.approx(150.0)  # default
    assert _fetch_quote(finnhub, "AAPL", vendor="finnhub")["price"] == pytest.approx(150.0)
    assert _fetch_quote(yahoo, "AAPL", vendor="yahoo")["price"] == pytest.approx(99.0)
    # Caches are namespaced per vendor, not shared.
    assert set(screeners._real_quote_cache) == {"finnhub:AAPL", "yahoo:AAPL"}
    # Profile: finnhub caches, yahoo (None) never caches.
    finnhub_profile = _FakeClient(
        {
            "/stock/profile2": _FakeResponse(
                {"ticker": "AAPL", "name": "Apple", "marketCapitalization": 1.0}
            )
        }
    )
    assert _fetch_profile(finnhub_profile, "AAPL")["name"] == "Apple"
    assert _fetch_profile(finnhub_profile, "AAPL", vendor="yahoo") is None
    assert set(screeners._real_profile_cache) == {"finnhub:AAPL"}
