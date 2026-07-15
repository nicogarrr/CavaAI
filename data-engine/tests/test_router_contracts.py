import io

from fastapi.testclient import TestClient
from openpyxl import Workbook

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


def test_knowledge_upload_files_supports_excel(monkeypatch):
    class FakeKnowledgeBase:
        def add_document(self, content, tenant_id, metadata=None):
            assert tenant_id == 1
            assert "=== Hoja: Sheet ===" in content
            assert "ticker | value" in content
            return {"document_id": "doc-1", "chunks_added": 1}

    import modules.knowledge_base as knowledge_base
    from routers import knowledge

    monkeypatch.setattr(knowledge_base, "get_knowledge_base", lambda: FakeKnowledgeBase())
    monkeypatch.setattr(knowledge, "_tenant_id", lambda _db: 1)

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["ticker", "value"])
    sheet.append(["AAPL", 10])
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    response = TestClient(main.app).post(
        "/knowledge/upload-files",
        files={"files": ("sample.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["document_id"] == "doc-1"
