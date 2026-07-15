from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import CashBalance, Company, Position, Transaction
from app.services.connectors.ibkr import IBKRFlexClient
from app.services.ibkr_import_service import IBKRImportService
from app.services.risk_service import RiskService
from app.services.portfolio_ledger_service import PortfolioLedgerService

router = APIRouter()


class IBKRXmlImportRequest(BaseModel):
    xml: str = Field(min_length=20)


class PortfolioTransactionInput(BaseModel):
    ticker: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9.\-]+$")
    action: Literal["buy", "sell"]
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(ge=0)
    trade_date: date
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=10)
    notes: str | None = Field(default=None, max_length=2000)


class PortfolioPriceInput(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    price: Decimal = Field(gt=0)
    as_of: date | None = None


def _transaction_payload(transaction: Transaction, company: Company) -> dict:
    return {
        "id": transaction.id,
        "ticker": company.ticker,
        "action": transaction.action,
        "quantity": float(transaction.quantity),
        "price": float(transaction.price),
        "fees": float(transaction.fees),
        "currency": transaction.currency,
        "trade_date": transaction.trade_date.isoformat(),
        "notes": (transaction.raw_payload or {}).get("notes"),
        "created_at": transaction.created_at.isoformat(),
        "updated_at": transaction.updated_at.isoformat(),
    }


@router.get("/summary")
def portfolio_summary(db: Session = Depends(get_db)) -> dict:
    risk = RiskService().dashboard(db)
    return {
        "total_value": risk["total_value"],
        "equity_value": risk["equity_value"],
        "cash": risk["cash"],
        "top_1_weight": risk["top_1_weight"],
        "top_5_weight": risk["top_5_weight"],
        "alerts": risk["alerts"],
    }


@router.get("/positions")
def positions(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(Position, Company).join(Company, Position.company_id == Company.id)).all()
    return [
        {
            "ticker": company.ticker,
            "name": company.name,
            "sector": company.sector,
            "quantity": float(position.quantity),
            "market_price": float(position.market_price),
            "market_value": float(position.market_value),
            "unrealized_pnl": float(position.unrealized_pnl),
            "currency": position.currency,
            "source": position.source,
        }
        for position, company in rows
    ]


@router.get("/transactions")
def transactions(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Transaction, Company)
        .join(Company, Transaction.company_id == Company.id)
        .where(Transaction.action.in_(["buy", "sell"]))
        .order_by(desc(Transaction.trade_date), desc(Transaction.created_at))
    ).all()
    return [_transaction_payload(transaction, company) for transaction, company in rows]


@router.post("/transactions", status_code=201)
def create_transaction(
    payload: PortfolioTransactionInput, db: Session = Depends(get_db)
) -> dict:
    service = PortfolioLedgerService()
    try:
        transaction = service.create_transaction(
            db,
            ticker=payload.ticker,
            action=payload.action,
            quantity=payload.quantity,
            price=payload.price,
            trade_date=payload.trade_date,
            fees=payload.fees,
            currency=payload.currency,
            notes=payload.notes,
        )
        db.commit()
        db.refresh(transaction)
        company = db.get(Company, transaction.company_id)
        assert company is not None
        return _transaction_payload(transaction, company)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/transactions/{transaction_id}")
def update_transaction(
    transaction_id: int,
    payload: PortfolioTransactionInput,
    db: Session = Depends(get_db),
) -> dict:
    transaction = db.get(Transaction, transaction_id)
    if not transaction or transaction.action not in {"buy", "sell"}:
        raise HTTPException(status_code=404, detail="Transaction not found")
    service = PortfolioLedgerService()
    original_company_id = transaction.company_id
    company = service.ensure_company(db, payload.ticker)
    transaction.company_id = company.id
    transaction.action = payload.action
    transaction.quantity = payload.quantity
    transaction.price = payload.price
    transaction.trade_date = payload.trade_date
    transaction.fees = payload.fees
    transaction.currency = payload.currency.upper()
    transaction.raw_payload = {"notes": payload.notes} if payload.notes else {}
    try:
        if original_company_id is not None:
            service.rebuild_position(db, original_company_id)
        if company.id != original_company_id:
            service.rebuild_position(db, company.id)
        db.commit()
        db.refresh(transaction)
        return _transaction_payload(transaction, company)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/transactions/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)) -> None:
    transaction = db.get(Transaction, transaction_id)
    if not transaction or transaction.action not in {"buy", "sell"}:
        raise HTTPException(status_code=404, detail="Transaction not found")
    company_id = transaction.company_id
    db.delete(transaction)
    db.flush()
    if company_id is not None:
        PortfolioLedgerService().rebuild_position(db, company_id)
    db.commit()


@router.delete("/holdings/{ticker}", status_code=204)
def delete_holding(ticker: str, db: Session = Depends(get_db)) -> None:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Holding not found")
    deleted = PortfolioLedgerService().delete_holding(db, company.id)
    if not deleted:
        db.rollback()
        raise HTTPException(status_code=404, detail="Holding not found")
    db.commit()


@router.patch("/prices")
def update_price(payload: PortfolioPriceInput, db: Session = Depends(get_db)) -> dict:
    company = db.scalar(select(Company).where(Company.ticker == payload.ticker.upper()))
    if not company:
        raise HTTPException(status_code=404, detail="Holding not found")
    try:
        position = PortfolioLedgerService().update_market_price(
            db, company_id=company.id, price=payload.price, as_of=payload.as_of
        )
        db.commit()
        return {"ticker": company.ticker, "market_price": float(position.market_price)}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/cash")
def cash(db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "currency": row.currency,
            "balance": float(row.balance),
            "settled_cash": float(row.settled_cash),
            "interest_rate": float(row.interest_rate),
            "source": row.source,
        }
        for row in db.scalars(select(CashBalance)).all()
    ]


@router.post("/import/ibkr")
async def import_ibkr(db: Session = Depends(get_db)) -> dict:
    client = IBKRFlexClient()
    if not client.configured():
        return {
            "status": "not_configured",
            "message": "Set IBKR_FLEX_TOKEN and IBKR_FLEX_QUERY_ID, then run the IBKR Flex connector.",
        }
    xml_text = await client.fetch_latest_xml()
    return IBKRImportService().import_flex_xml(db, xml_text)


@router.post("/import/ibkr/xml")
def import_ibkr_xml(payload: IBKRXmlImportRequest, db: Session = Depends(get_db)) -> dict:
    return IBKRImportService().import_flex_xml(db, payload.xml)
