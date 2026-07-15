from decimal import Decimal

from sqlalchemy import delete, select

from app.core.database import SessionLocal, init_db
from app.models import Company, FinancialFact
from app.services.valuation_service import ValuationService


def test_sotp_requires_sourced_segment_metrics_multiples_and_discount():
    init_db()
    db = SessionLocal()
    company_id: int | None = None
    ticker = "SOTPE"
    try:
        existing = db.scalar(select(Company).where(Company.ticker == ticker))
        if existing:
            db.execute(delete(FinancialFact).where(FinancialFact.company_id == existing.id))
            db.delete(existing)
            db.commit()

        company = Company(
            ticker=ticker,
            name="SOTP evidence test",
            exchange="TEST",
            currency="USD",
            sector="Industrials",
            industry="Conglomerate",
            company_type="multi_segment",
            valuation_model="sotp",
            special_sources=[],
            special_risks=[],
            factor_tags=["sotp"],
        )
        db.add(company)
        db.flush()
        company_id = company.id
        facts = {
            "shares_diluted": 100,
            "net_debt": 250,
            "holding_company_discount": 0.12,
            "segment_services_operating_metric": 80,
            "segment_services_valuation_multiple": 12,
            "segment_assets_operating_metric": 500,
            "segment_assets_valuation_multiple": 1.1,
        }
        for metric, value in facts.items():
            db.add(
                FinancialFact(
                    company_id=company.id,
                    metric=metric,
                    value=Decimal(str(value)),
                    unit="decimal",
                    period="FY2025",
                    fiscal_year=2025,
                    fiscal_quarter="FY",
                    source_type="sotp_engine_test",
                    confidence=Decimal("0.91"),
                )
            )
        db.commit()

        result = ValuationService().value_company(db, company)
        probabilities = [
            result["trace"]["scenarios"][name]["definition"]["probability"]
            for name in ("bear", "base", "bull")
        ]

        assert result["status"] == "ok"
        assert result["publishable"] is True
        assert result["trace"]["holding_discount_source"] == "financial_facts"
        assert "segment_services_valuation_multiple" in result["trace"]["fact_ids"]
        assert probabilities != [0.25, 0.50, 0.25]
        assert abs(sum(probabilities) - 1.0) < 1e-9
    finally:
        if company_id is not None:
            db.execute(delete(FinancialFact).where(FinancialFact.company_id == company_id))
            db.execute(delete(Company).where(Company.id == company_id))
            db.commit()
        db.close()
