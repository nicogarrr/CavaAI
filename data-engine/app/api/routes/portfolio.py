from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import CashBalance, Company, FXRate, Position, Transaction
from app.services.connectors.ibkr import IBKRFlexClient
from app.services.ibkr_import_service import IBKRImportService
from app.services.risk_service import RiskService
from app.services.portfolio_ledger_service import PortfolioLedgerService
from app.services.portfolio_fx_service import PortfolioFXService

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


class PortfolioConfigurationInput(BaseModel):
    base_currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")


class FXRateInput(BaseModel):
    base_currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    quote_currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    rate: Decimal = Field(gt=0)
    rate_date: date
    source: str = Field(default="manual", min_length=1, max_length=80)


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
        "status": risk["status"],
        "base_currency": risk["base_currency"],
        "cash_native": risk["cash_native"],
        "missing_fx": risk["missing_fx"],
    }


@router.get("/configuration")
def portfolio_configuration(db: Session = Depends(get_db)) -> dict:
    portfolio = PortfolioFXService().portfolio(db)
    return {
        "id": portfolio.id if portfolio else None,
        "name": portfolio.name if portfolio else "Main",
        "base_currency": portfolio.base_currency if portfolio else "EUR",
        "is_default": portfolio.is_default if portfolio else True,
    }


@router.put("/configuration")
def update_portfolio_configuration(
    payload: PortfolioConfigurationInput,
    db: Session = Depends(get_db),
) -> dict:
    service = PortfolioFXService()
    ledger = PortfolioLedgerService()
    try:
        portfolio = service.set_base_currency(db, payload.base_currency)
        company_ids = list(db.scalars(select(Position.company_id)).all())
        for company_id in company_ids:
            ledger.rebuild_position(db, company_id)
        db.commit()
        return {
            "id": portfolio.id,
            "name": portfolio.name,
            "base_currency": portfolio.base_currency,
            "is_default": portfolio.is_default,
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/fx-rates")
def list_fx_rates(db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "id": row.id,
            "base_currency": row.base_currency,
            "quote_currency": row.quote_currency,
            "rate": float(row.rate),
            "rate_date": row.rate_date.isoformat(),
            "source": row.source,
        }
        for row in db.scalars(
            select(FXRate).order_by(
                desc(FXRate.rate_date), FXRate.base_currency, FXRate.quote_currency
            )
        ).all()
    ]


@router.post("/fx-rates", status_code=201)
def upsert_fx_rate(payload: FXRateInput, db: Session = Depends(get_db)) -> dict:
    service = PortfolioFXService()
    ledger = PortfolioLedgerService()
    try:
        row = service.upsert_rate(
            db,
            base_currency=payload.base_currency,
            quote_currency=payload.quote_currency,
            rate=payload.rate,
            rate_date=payload.rate_date,
            source=payload.source,
        )
        company_ids = list(db.scalars(select(Position.company_id)).all())
        for company_id in company_ids:
            ledger.rebuild_position(db, company_id)
        db.commit()
        db.refresh(row)
        return {
            "id": row.id,
            "base_currency": row.base_currency,
            "quote_currency": row.quote_currency,
            "rate": float(row.rate),
            "rate_date": row.rate_date.isoformat(),
            "source": row.source,
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/positions")
def positions(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(Position, Company).join(Company, Position.company_id == Company.id)).all()
    return [
        {
            "ticker": company.ticker,
            "name": company.name,
            "sector": company.sector,
            "quantity": float(position.quantity),
            "average_cost": float(position.average_cost),
            "market_price": float(position.market_price),
            "market_value": float(position.market_value),
            "unrealized_pnl": float(position.unrealized_pnl),
            "realized_pnl": float(position.realized_pnl),
            "cost_basis": float(
                position.cost_basis_native
                if position.cost_basis_native is not None
                else position.quantity * position.average_cost
            ),
            "as_of": position.as_of.isoformat(),
            "currency": position.currency,
            "native_currency": position.currency,
            "base_currency": position.base_currency,
            "market_value_native": (
                float(position.market_value_native)
                if position.market_value_native is not None
                else float(position.market_value)
            ),
            "market_value_base": (
                float(position.market_value_base)
                if position.market_value_base is not None
                else None
            ),
            "cost_basis_native": (
                float(position.cost_basis_native)
                if position.cost_basis_native is not None
                else float(position.quantity * position.average_cost)
            ),
            "cost_basis_base": (
                float(position.cost_basis_base)
                if position.cost_basis_base is not None
                else None
            ),
            "unrealized_pnl_native": float(position.unrealized_pnl),
            "unrealized_pnl_base": (
                float(position.unrealized_pnl_base)
                if position.unrealized_pnl_base is not None
                else None
            ),
            "realized_pnl_base": (
                float(position.realized_pnl_base)
                if position.realized_pnl_base is not None
                else None
            ),
            "fx_rate": float(position.fx_rate) if position.fx_rate is not None else None,
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
