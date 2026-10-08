"""Carril de noticias por ticker sin GDELT: URLs, fuente real y filtro de evidencia."""

import asyncio
from types import SimpleNamespace

from app.services.connectors.base import ConnectorItem, ConnectorResult
from app.services.connectors.rss import RSSConnector
from app.services.news_service import _ticker_evidence_level
from app.services.ticker_news_lane import (
    PRIORITY_TICKERS,
    Deadline,
    finalize_status,
    google_feed_url,
    is_us_listed,
    label_google,
    label_yahoo,
    yahoo_feed_url,
)

SPCX = SimpleNamespace(ticker="SPCX", name="Space Exploration Technologies Corp", exchange="NASDAQ")
ASTS = SimpleNamespace(ticker="ASTS", name="AST SpaceMobile Inc", exchange="NASDAQ NMS - GLOBAL MARKET")
AENA = SimpleNamespace(ticker="AENA", name="AENA S.M.E. SA", exchange="BME")

YAHOO_XML = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Yahoo! Finance: SPCX News</title>
<item><title>SpaceX Buys Wireless Spectrum For Starlink</title><link>https://example.com/a</link>
<guid>a-1</guid><pubDate>Thu, 08 Oct 2026 21:00:00 +0000</pubDate><description>SPCX news</description></item>
</channel></rss>"""


def _item(title: str, summary: str = "") -> ConnectorItem:
    return ConnectorItem(source="Google News", title=title, summary=summary, ticker="SPCX")


def test_priority_tickers_include_asts_and_spcx():
    assert {"ASTS", "SPCX"} <= PRIORITY_TICKERS


def test_only_us_listed_get_a_yahoo_symbol():
    assert is_us_listed(SPCX) and is_us_listed(ASTS)
    assert not is_us_listed(AENA)


def test_feed_urls_are_free_rss_endpoints():
    assert yahoo_feed_url("spcx") == (
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPCX&region=US&lang=en-US"
    )
    url = google_feed_url(SPCX, lang="es")
    assert url.startswith("https://news.google.com/rss/search?q=")
    assert "hl=es&gl=ES&ceid=ES:es" in url
    assert "Space+Exploration+Technologies" in url


def test_yahoo_items_keep_real_date_and_a_stable_source_label():
    class _Fake(RSSConnector):
        async def _fetch(self, url):
            return SimpleNamespace(content=YAHOO_XML)

    result = asyncio.run(_Fake().poll(yahoo_feed_url("SPCX"), ticker="SPCX"))
    result = label_yahoo(result)
    item = result.items[0]
    assert item.source == "Yahoo Finance"
    assert item.published_at is not None and item.published_at.isoformat().startswith("2026-10-08T21:00")


def test_google_keeps_publisher_and_drops_items_without_company_evidence():
    result = ConnectorResult(
        source="rss",
        items=[
            _item("SpaceX adquirira el espectro para Starlink Mobile - TradingView", "SPCX"),
            _item("Receta de tortilla de patatas - Cocina Facil", "nada que ver"),
        ],
    )
    out = label_google(result, SPCX, _ticker_evidence_level)
    assert [i.source for i in out.items] == ["TradingView"]
    assert out.items[0].title == "SpaceX adquirira el espectro para Starlink Mobile"


def test_spacex_headline_without_ticker_is_accepted_for_spcx():
    result = ConnectorResult(source="rss", items=[
        _item("SpaceX Buys Wireless Spectrum For Starlink Mobile - TradingView"),
        _item("SpaceX busca 40.000 millones de dolares de deuda - La Vanguardia"),
    ])
    out = label_google(result, SPCX, _ticker_evidence_level)
    assert [i.source for i in out.items] == ["TradingView", "La Vanguardia"]


def test_ast_spacemobile_name_only_is_accepted_for_asts_but_not_for_spcx():
    headline = "AST SpaceMobile launches BlueBird 7 satellite - Reuters"
    kept = label_google(ConnectorResult(source="rss", items=[_item(headline)]), ASTS, _ticker_evidence_level)
    assert len(kept.items) == 1
    other = label_google(ConnectorResult(source="rss", items=[_item(headline)]), SPCX, _ticker_evidence_level)
    assert other.items == []


def test_competitor_and_generic_terms_are_rejected():
    items = [
        _item("Rocket Lab drops 4% as Planet Labs falls 5% - 247WallSt"),
        _item("Satellite broadband market grows - Telecom Weekly"),
        _item("Apple pie recipe - Cocina"),
    ]
    apple = SimpleNamespace(ticker="AAPL", name="Apple Inc", exchange="NASDAQ")
    assert label_google(ConnectorResult(source="rss", items=list(items)), ASTS, _ticker_evidence_level).items == []
    assert label_google(ConnectorResult(source="rss", items=list(items)), SPCX, _ticker_evidence_level).items == []
    # Una sola palabra generica de nombre no basta ("Apple" sin ticker).
    assert label_google(ConnectorResult(source="rss", items=list(items)), apple, _ticker_evidence_level).items == []


def test_deadline_is_checked_before_and_after_each_unit_and_marks_truncated():
    now = [0.0]
    deadline = Deadline(100, clock=lambda: now[0])
    assert deadline.expired() is False and deadline.truncated is False
    now[0] = 99.0
    assert deadline.expired() is False
    now[0] = 101.0  # la unidad en curso paso el limite
    assert deadline.expired() is True
    now[0] = 0.0  # una vez truncado no se "des-trunca"
    assert deadline.expired() is True and deadline.truncated is True


def test_truncated_sweep_is_never_ok_so_the_coalescer_does_not_mark_it_fresh():
    assert finalize_status("ok", True) == "partial"
    assert finalize_status("ok", False) == "ok"
    assert finalize_status("error", True) == "error"
    assert finalize_status("partial", True) == "partial"
