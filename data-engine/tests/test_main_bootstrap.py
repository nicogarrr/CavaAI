import re
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

import main
from app.core.database import SessionLocal
from app.models import (
    CalculatedMetric,
    FundamentalModelVersion,
    MoatAssessment,
    ThesisNode,
    ValuationModel,
)
from app.seed import seed


DATA_ENGINE_ROOT = Path(__file__).resolve().parents[1]


def test_main_only_declares_root_and_health_routes():
    source = (DATA_ENGINE_ROOT / "main.py").read_text(encoding="utf-8")
    app_routes = re.findall(r"@app\.(?:get|post|put|patch|delete)\(\"([^\"]+)\"", source)

    assert "/" in app_routes
    assert "/health" in app_routes
    assert "/health/live" in app_routes
    assert "/health/ready" in app_routes
    assert "include_router(fundamentals_router, dependencies=private_dependencies)" in source
    assert "include_router(market_router, dependencies=private_dependencies)" in source
    assert "knowledge_router" not in source
    assert "include_router(analytics_router, dependencies=private_dependencies)" in source
    assert "research_api_router," in source
    assert "dependencies=private_dependencies" in source


def test_public_routes_are_registered_once():
    routes = list(main.app.openapi()["paths"].keys())

    expected_routes = {
        "/",
        "/health",
        "/health/live",
        "/health/ready",
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
        "/analytics/portfolio",
        "/analytics/portfolio/returns",
        "/analytics/holding/{symbol}",
        "/analytics/montecarlo",
        "/analytics/correlation",
        "/analytics/regime/{symbol}",
        "/api/companies",
        "/api/companies/{ticker}",
        "/api/portfolio/summary",
        "/api/companies/{ticker}/metrics/calculated",
        "/api/companies/{ticker}/snapshot",
        "/api/companies/{ticker}/peers/comparison",
        "/api/portfolio/positions",
        "/api/portfolio/cash",
        "/api/portfolio/import/ibkr",
        "/api/portfolio/import/ibkr/xml",
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

    assert not any(route.startswith("/knowledge/") for route in routes)

    duplicates = {route for route in routes if routes.count(route) > 1}
    assert duplicates == set()


def test_root_and_health():
    client = TestClient(main.app)

    assert client.get("/").json() == {"status": "ok", "service": "CavaAI Research Engine"}
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/live").json() == {"status": "ok"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert "checks" in ready.json()
    assert "database" in ready.json()["checks"]


def test_company_workspace_uses_small_read_only_typed_snapshot_contract():
    seed()

    def mutable_row_counts() -> tuple[int, ...]:
        with SessionLocal() as db:
            return tuple(
                int(db.scalar(select(func.count()).select_from(model)) or 0)
                for model in (
                    CalculatedMetric,
                    FundamentalModelVersion,
                    MoatAssessment,
                    ThesisNode,
                    ValuationModel,
                )
            )

    before = mutable_row_counts()
    response = TestClient(main.app).get("/api/companies/MSFT/snapshot")
    after = mutable_row_counts()

    assert response.status_code == 200
    assert after == before
    payload = response.json()
    assert payload["company"]["ticker"] == "MSFT"
    assert {
        "latest_thesis",
        "valuation_summary",
        "model_summary",
        "research_health",
        "counts",
        "recent_changes",
    }.issubset(payload)
    assert "facts" not in payload
    assert "sourceDocuments" not in payload
    operation = main.app.openapi()["paths"]["/api/companies/{ticker}/snapshot"]["get"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/CompanySnapshotOut")
