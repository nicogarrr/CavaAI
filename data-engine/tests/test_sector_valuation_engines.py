from decimal import Decimal

from sqlalchemy import delete, select

from app.core.database import SessionLocal, init_db
from app.models import Company, FinancialFact
from app.services.valuation_service import ValuationService


CASES = {
    "BKNTE": (
        "bank",
        "bank_residual_income",
        {
            "tangible_book_value": 1000,
            "shares_diluted": 100,
            "roe": 0.14,
            "cost_of_equity": 0.10,
            "book_value_growth": 0.03,
        },
    ),
    "INSRE": (
        "insurer",
        "insurance_book_value",
        {
            "book_value": 1200,
            "shares_diluted": 100,
            "roe": 0.13,
            "cost_of_equity": 0.10,
            "combined_ratio": 0.95,
            "book_value_growth": 0.03,
        },
    ),
    "REITE": (
        "reit",
        "reit_nav",
        {
            "net_operating_income": 100,
            "cap_rate": 0.05,
            "net_debt": 600,
            "shares_diluted": 100,
        },
    ),
}


def test_bank_insurer_and_reit_use_dedicated_fact_driven_engines():
    init_db()
    db = SessionLocal()
    company_ids: list[int] = []
    try:
        for ticker, (company_type, model, facts) in CASES.items():
            existing = db.scalar(select(Company).where(Company.ticker == ticker))
            if existing:
                db.execute(delete(FinancialFact).where(FinancialFact.company_id == existing.id))
                db.delete(existing)
                db.commit()
            company = Company(
                ticker=ticker,
                name=f"{company_type} test",
                exchange="TEST",
                currency="USD",
                sector="Financials" if company_type != "reit" else "Real Estate",
                industry="Test",
                company_type=company_type,
                valuation_model=model,
                special_sources=[],
                special_risks=[],
                factor_tags=[],
            )
            db.add(company)
            db.flush()
            company_ids.append(company.id)
            for metric, value in facts.items():
                db.add(
                    FinancialFact(
                        company_id=company.id,
                        metric=metric,
                        value=Decimal(str(value)),
                        unit="decimal" if abs(value) < 1 else "USD",
                        period="FY2025",
                        fiscal_year=2025,
                        fiscal_quarter="FY",
                        source_type="sector_engine_test",
                        is_reported=True,
                        confidence=Decimal("0.92"),
                    )
                )
        db.commit()

        for ticker, (expected_engine, _, _) in CASES.items():
            company = db.scalar(select(Company).where(Company.ticker == ticker))
            result = ValuationService().value_company(db, company)
            assert result["status"] == "ok"
            assert result["publishable"] is True
            assert result["trace"]["engine"] == expected_engine
            assert result["base_value"] > 0
            assert result["trace"]["fact_ids"]
            assert result["trace"]["probability_method"] == "source_confidence_plus_company_quality"
    finally:
        if company_ids:
            db.execute(delete(FinancialFact).where(FinancialFact.company_id.in_(company_ids)))
            db.execute(delete(Company).where(Company.id.in_(company_ids)))
            db.commit()
        db.close()
