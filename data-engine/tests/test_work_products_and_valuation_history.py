from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Company, Document, FinancialFact, MarketPrice, Tenant
from app.services.historical_valuation_service import HistoricalValuationService
from app.services.work_product_service import WorkProductService


def test_work_product_manifest_and_historical_valuation_series():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(external_id="work-product", name="Work product")
        db.add(tenant)
        db.flush()
        db.info["tenant_id"] = tenant.id
        company = Company(
            ticker="MEMO",
            name="Memo Co",
            exchange="TEST",
            currency="USD",
            sector="Industrials",
            industry="Equipment",
            company_type="standard",
            valuation_model="standard_dcf",
            special_sources=[],
            special_risks=[],
            factor_tags=[],
        )
        db.add(company)
        db.flush()
        filing = Document(
            company_id=company.id,
            title="FY2025 filing",
            source_type="sec_filing",
            source_url="https://sec.gov/example",
            published_at=datetime(2025, 12, 31, tzinfo=UTC),
        )
        db.add(filing)
        db.flush()
        for year, price, eps, fcf, revenue, shares in (
            (2024, "20", "2", "12", "100", "10"),
            (2025, "30", "3", "20", "130", "10"),
        ):
            db.add(
                MarketPrice(
                    company_id=company.id,
                    date=date(year, 12, 31),
                    close=Decimal(price),
                    adj_close=Decimal(price),
                    source="test",
                )
            )
            for metric, value, unit in (
                ("eps", eps, "USD/share"),
                ("free_cash_flow", fcf, "USD"),
                ("revenue", revenue, "USD"),
                ("shares_diluted", shares, "shares"),
                ("total_debt", "5", "USD"),
                ("cash_and_equivalents", "2", "USD"),
            ):
                db.add(
                    FinancialFact(
                        company_id=company.id,
                        metric=metric,
                        value=Decimal(value),
                        unit=unit,
                        period=f"FY{year}",
                        fiscal_year=year,
                        fiscal_quarter="FY",
                        source_id=filing.id,
                        source_type="sec_filing",
                        confidence=Decimal("0.95"),
                    )
                )
        db.commit()

        memo = WorkProductService().generate(
            db, product_type="one_page_memo", company=company
        )
        assert memo["manifest"]["source_count"] > 0
        assert memo["manifest"]["data_as_of"] is not None
        assert "financial_fact:" in memo["markdown"]
        assert memo["sections"]["company"]["ticker"] == "MEMO"

        history = HistoricalValuationService().build(db, company, years=10)
        assert [row["year"] for row in history["series"]] == [2024, 2025]
        assert history["series"][0]["pe"] == Decimal("10")
        assert history["series"][1]["fcf_per_share"] == Decimal("2")
        assert history["series"][1]["revenue_per_share"] == Decimal("13")
        assert history["statistics"]["pe"]["median"] == Decimal("10")
        assert history["coverage"]["complete_valuation_points"] == 2
