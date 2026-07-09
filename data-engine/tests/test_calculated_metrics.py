from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import main
from app.core.database import SessionLocal, init_db
from app.models import CalculatedMetric, Company, FinancialFact


TEST_TICKER = "TCALC"


def cleanup_metric_test_artifacts() -> None:
    init_db()
    db = SessionLocal()
    try:
        company = db.scalar(select(Company).where(Company.ticker == TEST_TICKER))
        if company:
            db.execute(delete(CalculatedMetric).where(CalculatedMetric.company_id == company.id))
            db.execute(delete(FinancialFact).where(FinancialFact.company_id == company.id))
            db.delete(company)
            db.commit()
    finally:
        db.close()


def create_test_company(db) -> Company:
    company = Company(
        ticker=TEST_TICKER,
        name="Traceable Metrics Test Co",
        exchange="TEST",
        currency="USD",
        sector="Software",
        industry="Application Software",
        company_type="standard",
        valuation_model="standard_dcf",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.flush()
    return company


def add_fact(db, company: Company, metric: str, value: str, period: str = "FY2025") -> FinancialFact:
    fact = FinancialFact(
        company_id=company.id,
        metric=metric,
        value=Decimal(value),
        unit="USD" if metric != "shares_diluted" else "shares",
        period=period,
        fiscal_year=2025,
        fiscal_quarter="FY",
        source_type="test_metric",
        confidence=Decimal("0.90"),
    )
    db.add(fact)
    return fact


def test_calculated_metrics_are_persisted_with_trace():
    cleanup_metric_test_artifacts()
    db = SessionLocal()
    try:
        company = create_test_company(db)
        add_fact(db, company, "revenue", "1000")
        add_fact(db, company, "free_cash_flow", "250")
        add_fact(db, company, "net_income", "180")
        add_fact(db, company, "operating_income", "250")
        add_fact(db, company, "gross_profit", "650")
        add_fact(db, company, "total_equity", "800")
        add_fact(db, company, "total_assets", "1500")
        add_fact(db, company, "total_debt", "200")
        add_fact(db, company, "cash_and_equivalents", "100")
        add_fact(db, company, "ebitda", "300")
        db.commit()
    finally:
        db.close()

    client = TestClient(main.app)
    response = client.get(f"/api/companies/{TEST_TICKER}/metrics/calculated")
    assert response.status_code == 200
    payload = response.json()
    metrics = {item["metric"]: item for item in payload["metrics"]}

    assert metrics["fcf_margin"]["status"] == "ok"
    assert Decimal(metrics["fcf_margin"]["value"]) == Decimal("0.25000000")
    assert metrics["fcf_margin"]["formula"] == "free_cash_flow / revenue"
    assert metrics["fcf_margin"]["numerator"] == "250.00000000"
    assert metrics["fcf_margin"]["denominator"] == "1000.00000000"
    assert len(metrics["fcf_margin"]["source_fact_ids"]) == 2
    assert metrics["fcf_margin"]["calculation_trace"]["method"] == "simple_ratio"

    assert metrics["roic"]["status"] == "ok"
    assert Decimal(metrics["roic"]["value"]) == Decimal("0.21944444")
    assert metrics["roic"]["calculation_trace"]["method"] == "standard_roic"

    db = SessionLocal()
    try:
        stored = db.scalar(
            select(CalculatedMetric).where(
                CalculatedMetric.metric == "fcf_margin",
                CalculatedMetric.period == "FY2025",
            )
        )
        assert stored is not None
        assert stored.definition_version == "FCF_MARGIN_V1"
        assert stored.source_fact_ids
    finally:
        db.close()
        cleanup_metric_test_artifacts()


def test_calculated_metrics_report_unavailable_when_inputs_are_missing():
    cleanup_metric_test_artifacts()
    db = SessionLocal()
    try:
        company = create_test_company(db)
        add_fact(db, company, "revenue", "1000")
        db.commit()
    finally:
        db.close()

    client = TestClient(main.app)
    response = client.get(f"/api/companies/{TEST_TICKER}/metrics/calculated?refresh=false")
    assert response.status_code == 200
    metrics = {item["metric"]: item for item in response.json()["metrics"]}

    assert metrics["fcf_margin"]["status"] == "unavailable"
    assert metrics["fcf_margin"]["value"] is None
    assert "free_cash_flow" in metrics["fcf_margin"]["calculation_trace"]["missing_inputs"]

    cleanup_metric_test_artifacts()
