import re
from pathlib import Path

from fastapi.testclient import TestClient

import main


DATA_ENGINE_ROOT = Path(__file__).resolve().parents[1]


def test_main_only_declares_root_and_health_routes():
    source = (DATA_ENGINE_ROOT / "main.py").read_text(encoding="utf-8")
    app_routes = re.findall(r"@app\.(?:get|post|put|patch|delete)\(\"([^\"]+)\"", source)

    assert app_routes == ["/", "/health"]
    assert "include_router(fundamentals_router)" in source
    assert "include_router(market_router)" in source
    assert "include_router(knowledge_router)" in source
    assert "include_router(analytics_router)" in source
    assert "include_router(research_api_router, prefix=\"/api\")" in source


def test_public_routes_are_registered_once():
    routes = list(main.app.openapi()["paths"].keys())

    expected_routes = {
        "/",
        "/health",
        "/test",
        "/fundamentals/{symbol}",
        "/financial-growth/{symbol}",
        "/ratios-ttm/{symbol}",
        "/dcf/{symbol}",
        "/enterprise-value/{symbol}",
        "/key-metrics-ttm/{symbol}",
        "/financial-scores/{symbol}",
        "/owner-earnings/{symbol}",
        "/price-target/{symbol}",
        "/grades/{symbol}",
        "/peers/{symbol}",
        "/earnings-transcript/{symbol}",
        "/earnings-transcript-list/{symbol}",
        "/treasury-rates",
        "/analyst-estimates/{symbol}",
        "/press-releases/{symbol}",
        "/market-movers/gainers",
        "/market-movers/losers",
        "/market-movers/active",
        "/screener",
        "/news/fmp-articles",
        "/news/general",
        "/dividends/{symbol}",
        "/stock-peers/{symbol}",
        "/quote/{symbol}",
        "/batch-quotes",
        "/insider-trading/{symbol}",
        "/strategies/garp",
        "/company-news/{symbol}",
        "/knowledge/stats",
        "/knowledge/upload",
        "/knowledge/search",
        "/knowledge/context",
        "/knowledge/list/{collection}",
        "/knowledge/delete/{collection}/{document_id}",
        "/knowledge/upload-files",
        "/analytics/portfolio",
        "/analytics/portfolio/returns",
        "/analytics/holding/{symbol}",
        "/analytics/montecarlo",
        "/analytics/correlation",
        "/analytics/regime/{symbol}",
        "/api/companies",
        "/api/companies/{ticker}",
        "/api/portfolio/summary",
        "/api/portfolio/positions",
        "/api/portfolio/cash",
        "/api/portfolio/import/ibkr",
        "/api/thesis/generate",
        "/api/thesis/{ticker}/latest",
        "/api/thesis/{ticker}/versions",
        "/api/valuation/{ticker}",
        "/api/news/manual",
        "/api/news",
        "/api/risk/dashboard",
        "/api/chat",
        "/api/sources/documents",
        "/api/sources/audits",
        "/api/sources/quartr/status",
        "/api/sources/quartr/import-text",
        "/api/settings",
        "/api/workflows",
    }

    for route in expected_routes:
        assert route in routes

    duplicates = {route for route in routes if routes.count(route) > 1}
    assert duplicates == set()


def test_root_and_health():
    client = TestClient(main.app)

    assert client.get("/").json() == {"status": "ok", "service": "FMP Data Engine"}
    assert client.get("/health").json() == {"status": "healthy"}
