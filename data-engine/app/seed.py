from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionLocal, init_db
from app.data.company_master import COMPANY_MASTER, DEMO_POSITIONS
from app.models import CashBalance, Company, Document, DocumentChunk, Position


def upsert_company(db, payload: dict) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == payload["ticker"]))
    if company is None:
        company = Company(**payload)
        db.add(company)
        db.flush()
    else:
        for key, value in payload.items():
            setattr(company, key, value)
    return company


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        companies = {payload["ticker"]: upsert_company(db, payload) for payload in COMPANY_MASTER}
        db.flush()

        for item in DEMO_POSITIONS:
            company = companies[item["ticker"]]
            position = db.scalar(select(Position).where(Position.company_id == company.id))
            market_value = Decimal(str(item["quantity"] * item["market_price"]))
            cost_basis = Decimal(str(item["quantity"] * item["average_cost"]))
            if position is None:
                position = Position(company_id=company.id)
                db.add(position)
            position.quantity = Decimal(str(item["quantity"]))
            position.average_cost = Decimal(str(item["average_cost"]))
            position.market_price = Decimal(str(item["market_price"]))
            position.market_value = market_value
            position.unrealized_pnl = market_value - cost_basis
            position.realized_pnl = Decimal("0")
            position.currency = "USD"
            position.source = "demo_seed"

        for currency, balance in [("USD", -1250), ("EUR", 4200)]:
            cash = db.scalar(select(CashBalance).where(CashBalance.currency == currency))
            if cash is None:
                cash = CashBalance(currency=currency)
                db.add(cash)
            cash.balance = Decimal(str(balance))
            cash.settled_cash = Decimal(str(balance))
            cash.interest_rate = Decimal("0.0525") if balance < 0 else Decimal("0")
            cash.source = "demo_seed"

        for company in companies.values():
            existing_doc = db.scalar(
                select(Document).where(
                    Document.company_id == company.id,
                    Document.source_type == "company_master_seed",
                )
            )
            if existing_doc is None:
                existing_doc = Document(
                    company_id=company.id,
                    title=f"{company.ticker} company master seed",
                    source_type="company_master_seed",
                    source_url=company.ir_url,
                    published_at=datetime.now(UTC),
                    metadata_={
                        "purpose": "bootstrap evidence for local setup",
                        "not_official_financials": True,
                    },
                )
                db.add(existing_doc)
                db.flush()
                db.add(
                    DocumentChunk(
                        document_id=existing_doc.id,
                        chunk_index=0,
                        text=(
                            f"{company.ticker} is configured as {company.company_type}. "
                            f"Valuation model: {company.valuation_model}. "
                            f"Special sources: {', '.join(company.special_sources)}. "
                            f"Special risks: {', '.join(company.special_risks)}."
                        ),
                        token_count=80,
                        metadata_={"bootstrap": True},
                    )
                )

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
    print("Seed complete: companies, demo positions, cash balances and bootstrap sources loaded.")

