"""F403: bank engine must not divide by zero when CoE is barely above growth."""

from decimal import Decimal

from sqlalchemy import delete, select

from app.core.database import SessionLocal, init_db
from app.models import Company, FinancialFact
from app.services.valuation_service import ValuationService

FACTS = {
    "tangible_book_value": 1000,
    "shares_diluted": 100,
    "roe": 0.14,
    "cost_of_equity": 0.055,
    "book_value_growth": 0.05,
}


def test_bank_bull_scenario_with_thin_coe_growth_spread_does_not_crash():
    init_db()
    db = SessionLocal()
    try:
        existing = db.scalar(select(Company).where(Company.ticker == "BKTHIN"))
        if existing:
            db.execute(delete(FinancialFact).where(FinancialFact.company_id == existing.id))
            db.delete(existing)
            db.commit()
        company = Company(
            ticker="BKTHIN", name="bank thin spread", exchange="TEST", currency="USD",
            sector="Financials", industry="Test", company_type="bank",
            valuation_model="bank_residual_income", special_sources=[],
            special_risks=[], factor_tags=[],
        )
        db.add(company)
        db.flush()
        for metric, value in FACTS.items():
            db.add(FinancialFact(
                company_id=company.id, metric=metric, value=Decimal(str(value)),
                unit="decimal" if abs(value) < 1 else "USD", period="FY2025",
                fiscal_year=2025, fiscal_quarter="FY", source_type="sector_engine_test",
                is_reported=True, confidence=Decimal("0.92"),
            ))
        db.commit()
        result = ValuationService().value_company(db, company)
        assert result["status"] == "ok"
        assert result["bull_value"] > 0
        assert result["bull_value"] >= result["base_value"] >= result["bear_value"]
    finally:
        existing = db.scalar(select(Company).where(Company.ticker == "BKTHIN"))
        if existing:
            db.execute(delete(FinancialFact).where(FinancialFact.company_id == existing.id))
            db.delete(existing)
            db.commit()
        db.close()
