from fastapi.testclient import TestClient

import main
from routers import fundamentals, market


def test_fundamentals_endpoint_uses_router_dependency(monkeypatch):
    monkeypatch.setattr(fundamentals, "fetch_income_statement", lambda symbol, period: [{"symbol": symbol, "period": period}])
    monkeypatch.setattr(fundamentals, "fetch_balance_sheet", lambda symbol, period: [{"balance": True}])
    monkeypatch.setattr(fundamentals, "fetch_cash_flow", lambda symbol, period: [{"cashflow": True}])

    response = TestClient(main.app).get("/fundamentals/aapl?period=quarter")

    assert response.status_code == 200
    assert response.json()["symbol"] == "AAPL"
    assert response.json()["period"] == "quarter"


def test_fundamentals_errors_propagate(monkeypatch):
    monkeypatch.setattr(fundamentals, "fetch_ratios_ttm", lambda symbol: {"error": "restricted"})

    response = TestClient(main.app).get("/ratios-ttm/AAPL")

    assert response.status_code == 500
    assert response.json()["detail"] == "restricted"


def test_quote_and_batch_quotes_are_yfinance_backed(monkeypatch):
    monkeypatch.setattr(market, "fetch_yf_single_quote", lambda symbol: {"c": 123, "d": 1, "dp": 0.8, "h": 125, "l": 120, "o": 121, "pc": 122})
    monkeypatch.setattr(market, "fetch_yf_batch_quotes", lambda symbols: {symbol: {"price": 10} for symbol in symbols})
    client = TestClient(main.app)

    assert client.get("/quote/aapl").json()["c"] == 123
    assert client.post("/batch-quotes", json=["aapl", "msft"]).json() == {"AAPL": {"price": 10}, "MSFT": {"price": 10}}


def test_stock_peers_enriches_with_prices(monkeypatch):
    monkeypatch.setattr(market, "fetch_stock_peers", lambda symbol: ["MSFT", "GOOGL"])
    monkeypatch.setattr(market, "fetch_yf_batch_quotes", lambda symbols: {
        "MSFT": {"companyName": "Microsoft", "price": 1, "marketCap": 2, "change": 3, "changePercent": 4},
        "GOOGL": {"companyName": "Alphabet", "price": 5, "marketCap": 6, "change": 7, "changePercent": 8},
    })

    response = TestClient(main.app).get("/stock-peers/aapl?with_prices=true")

    assert response.status_code == 200
    assert response.json()[0] == {
        "symbol": "MSFT",
        "companyName": "Microsoft",
        "price": 1,
        "mktCap": 2,
        "change": 3,
        "changePercent": 4,
    }


def test_legacy_direct_vector_knowledge_routes_are_retired():
    response = TestClient(main.app).post(
        "/knowledge/upload",
        json={"collection": "analyses", "content": "must not bypass canonical ingestion"},
    )

    assert response.status_code == 404
