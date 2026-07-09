from fastapi.testclient import TestClient

import main
from app.core.database import SessionLocal, init_db
from app.seed import seed
from app.services.quartr_import_service import QuartrImportService
from app.services.source_auditor import SourceAuditor
from app.valuation import DCFInputs, ReverseDCFInputs, run_dcf, solve_required_growth


class FakeFMPClient:
    async def company_profile(self, ticker: str):
        return [{"symbol": ticker, "price": 20.0}]

    async def income_statement(self, ticker: str, limit: int = 10):
        return [
            {
                "date": "2025-12-31",
                "calendarYear": "2025",
                "period": "FY",
                "revenue": 1000,
                "grossProfit": 650,
                "operatingIncome": 250,
                "netIncome": 180,
                "ebitda": 300,
                "epsdiluted": 1.8,
                "weightedAverageShsOutDil": 100,
            },
            {
                "date": "2024-12-31",
                "calendarYear": "2024",
                "period": "FY",
                "revenue": 800,
                "grossProfit": 500,
                "operatingIncome": 190,
                "netIncome": 140,
                "ebitda": 230,
                "epsdiluted": 1.4,
                "weightedAverageShsOutDil": 100,
            },
        ]

    async def balance_sheet(self, ticker: str, limit: int = 10):
        return [
            {
                "date": "2025-12-31",
                "calendarYear": "2025",
                "period": "FY",
                "cashAndCashEquivalents": 100,
                "totalDebt": 200,
                "totalAssets": 1500,
                "totalLiabilities": 700,
                "totalStockholdersEquity": 800,
            }
        ]

    async def cash_flow(self, ticker: str, limit: int = 10):
        return [
            {
                "date": "2025-12-31",
                "calendarYear": "2025",
                "period": "FY",
                "operatingCashFlow": 300,
                "capitalExpenditure": -50,
                "freeCashFlow": 250,
                "commonStockRepurchased": -25,
                "dividendsPaid": -10,
            }
        ]

    async def ratios(self, ticker: str, limit: int = 10):
        return [
            {
                "date": "2025-12-31",
                "calendarYear": "2025",
                "period": "FY",
                "grossProfitMargin": 0.65,
                "operatingProfitMargin": 0.25,
                "netProfitMargin": 0.18,
                "debtEquityRatio": 0.25,
            }
        ]


def test_research_api_core_flow():
    seed()
    client = TestClient(main.app)

    companies = client.get("/api/companies")
    assert companies.status_code == 200
    assert len(companies.json()) >= 24

    portfolio = client.get("/api/portfolio/summary")
    assert portfolio.status_code == 200
    assert portfolio.json()["total_value"] > 0

    valuation = client.get("/api/valuation/ASTS")
    assert valuation.status_code == 200
    assert valuation.json()["ticker"] == "ASTS"
    assert valuation.json()["status"] == "insufficient_data"
    assert valuation.json()["publishable"] is False
    assert valuation.json()["expected_value"] is None
    assert valuation.json()["trace"]["engine"] == "pre_revenue"

    thesis = client.post("/api/thesis/generate", json={"ticker": "ASTS", "force_new_version": True})
    assert thesis.status_code == 200
    assert thesis.json()["status"] in {"final", "draft_failed_audit", "insufficient_data", "draft"}
    assert f"Thesis v{thesis.json()['version']}" in thesis.json()["thesis_markdown"]

    chat = client.post("/api/chat", json={"question": "Que pasa con ASTS?", "ticker": "ASTS"})
    assert chat.status_code == 200
    assert "ASTS" in chat.json()["answer"]


def test_source_auditor_blocks_unsourced_material_claims():
    audit = SourceAuditor().audit(
        claims=[{"claim": "Revenue grew 18% YoY", "material": True, "source_id": None}],
        calculation_trace={"method": "test"},
    )

    assert not audit.passed
    assert audit.unsupported_claims == ["Revenue grew 18% YoY"]


def test_dcf_and_reverse_dcf_are_deterministic():
    result = run_dcf(
        DCFInputs(
            revenue=1000,
            revenue_growth=0.10,
            fcf_margin=0.20,
            wacc=0.09,
            terminal_growth=0.03,
            net_debt=100,
            shares_outstanding=100,
        )
    )

    assert result.value_per_share > 0
    assert result.trace["method"] == "fcff_dcf"
    assert len(result.forecast) == 5

    solved = solve_required_growth(
        ReverseDCFInputs(
            market_price=50,
            revenue=1000,
            fcf_margin=0.18,
            wacc=0.10,
            terminal_growth=0.03,
            net_debt=100,
            shares_outstanding=100,
        )
    )

    assert abs(solved["solved_value_per_share"] - 50) < 0.01


def test_quartr_manual_import_creates_document_chunks_and_transcript():
    init_db()
    seed()
    db = SessionLocal()
    try:
        result = QuartrImportService().import_text(
            db=db,
            ticker="MSFT",
            title="MSFT Q1 call from Quartr",
            text="Management discussed Azure AI demand and capex discipline. " * 20,
            source_url="https://quartr.com",
            period="Q1",
        )

        assert result["ticker"] == "MSFT"
        assert result["document_id"] > 0
        assert result["transcript_id"] > 0
        assert result["chunks"] >= 1
    finally:
        db.close()


def test_ibkr_xml_import_endpoint_ingests_positions_cash_and_trades():
    init_db()
    client = TestClient(main.app)
    xml = """
    <FlexQueryResponse>
      <OpenPositions>
        <OpenPosition symbol="AAPL" position="2" markPrice="200" positionValue="400" costBasisPrice="150" currency="USD" fifoPnlUnrealized="100" />
      </OpenPositions>
      <CashReports>
        <CashReport currency="USD" endingCash="1234.56" settledCash="1200" />
      </CashReports>
      <Trades>
        <Trade tradeID="test-trade-1" symbol="AAPL" buySell="BUY" quantity="2" tradePrice="150" ibCommission="-1" currency="USD" tradeDate="2026-01-02" />
      </Trades>
    </FlexQueryResponse>
    """

    response = client.post("/api/portfolio/import/ibkr/xml", json={"xml": xml})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "imported"
    assert payload["positions_imported"] == 1
    assert payload["cash_imported"] == 1
    assert payload["trades_imported"] in {0, 1}


def test_fmp_refresh_normalizes_facts_and_valuation_uses_them(monkeypatch):
    from app.api.routes import companies as companies_route

    init_db()
    seed()
    monkeypatch.setattr(companies_route, "FMPClient", FakeFMPClient)
    client = TestClient(main.app)

    refresh = client.post("/api/companies/MSFT/refresh/fmp")
    assert refresh.status_code == 200
    payload = refresh.json()
    assert payload["status"] == "ingested"
    assert payload["facts_imported"] >= 20
    assert payload["valuation_input_ready"] is True

    facts = client.get("/api/companies/MSFT/facts?metric=revenue")
    assert facts.status_code == 200
    revenue_facts = facts.json()
    assert revenue_facts[0]["metric"] == "revenue"
    assert revenue_facts[0]["source_type"] == "FMP"

    valuation = client.get("/api/valuation/MSFT")
    assert valuation.status_code == 200
    payload = valuation.json()
    trace = payload["trace"]
    assert payload["status"] == "ok"
    assert payload["publishable"] is True
    assert payload["expected_value"] is not None
    assert trace["input_source"] == "financial_facts"
    assert trace["fact_ids"]["revenue"] == revenue_facts[0]["id"]
    assert "bootstrap_notice" not in trace
    assert trace["engine"] == "standard_dcf"
    assert "snapshot" in trace

    thesis = client.post("/api/thesis/generate", json={"ticker": "MSFT", "force_new_version": True})
    assert thesis.status_code == 200
    thesis_payload = thesis.json()
    assert "Valuation input source: `financial_facts`" in thesis_payload["thesis_markdown"]
    assert "| revenue |" in thesis_payload["thesis_markdown"]
    assert f"Thesis v{thesis_payload['version']}" in thesis_payload["thesis_markdown"]
    assert thesis_payload["data_confidence_score"] >= 80
