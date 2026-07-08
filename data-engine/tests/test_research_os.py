from fastapi.testclient import TestClient

import main
from app.core.database import SessionLocal, init_db
from app.seed import seed
from app.services.quartr_import_service import QuartrImportService
from app.services.source_auditor import SourceAuditor
from app.valuation import DCFInputs, ReverseDCFInputs, run_dcf, solve_required_growth


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
    assert valuation.json()["trace"]["method"]

    thesis = client.post("/api/thesis/generate", json={"ticker": "ASTS", "force_new_version": True})
    assert thesis.status_code == 200
    assert thesis.json()["status"] in {"final", "draft_failed_audit"}

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
