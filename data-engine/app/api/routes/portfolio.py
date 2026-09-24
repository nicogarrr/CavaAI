from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import CashBalance, Company, FXRate, Position, Transaction
from app.services.connectors.ibkr import IBKRFlexClient
from app.services.ibkr_import_service import IBKRImportError, IBKRImportService
from app.services.risk_service import RiskService
from app.services.portfolio_ledger_service import (
    PortfolioLedgerService,
    PortfolioMixedCurrencyError,
    PortfolioOversellError,
)
from app.services.portfolio_fx_service import PortfolioFXService
from app.services.market_refresh_service import MarketRefreshService
from app.services.portfolio_intelligence_service import PortfolioIntelligenceService
from app.services.portfolio_snapshot_service import PortfolioSnapshotService
from app.services.dividend_ingestion_service import DividendIngestionService
from app.services.tearsheet_service import TearsheetService
from app.services.company_resolver import resolve_company

router = APIRouter()


class IBKRXmlImportRequest(BaseModel):
    xml: str = Field(min_length=20)


class IBKRCsvImportRequest(BaseModel):
    csv: str = Field(min_length=10)


# Umbral fiscal: más de 365 días en cartera = largo plazo.
LONG_TERM_HOLDING_DAYS = 365


def _fiscal_info(db: Session, company_id: int, as_of: date) -> dict:
    """Antigüedad de la posición y bucket fiscal (corto/largo plazo).

    La antigüedad se mide desde la primera compra registrada en el ledger;
    sin compras registradas no hay bucket (None).
    """
    first_buy = db.scalar(
        select(func.min(Transaction.trade_date)).where(
            Transaction.company_id == company_id,
            Transaction.action == "buy",
        )
    )
    if first_buy is None:
        return {"first_buy_date": None, "holding_days": None, "fiscal_bucket": None}
    holding_days = (as_of - first_buy).days
    return {
        "first_buy_date": first_buy.isoformat(),
        "holding_days": holding_days,
        "fiscal_bucket": "largo_plazo" if holding_days > LONG_TERM_HOLDING_DAYS else "corto_plazo",
    }


def _fiscal_info_batch(
    db: Session, as_of_by_company: dict[int, date]
) -> dict[int, dict]:
    """Primera compra por compañía en UNA query (anti N+1 de /positions).

    Respeta el ``as_of`` propio de cada posición para el cálculo de
    holding_days, igual que :func:`_fiscal_info` fila a fila.
    """
    if not as_of_by_company:
        return {}
    first_buys = dict(
        db.execute(
            select(Transaction.company_id, func.min(Transaction.trade_date))
            .where(
                Transaction.company_id.in_(set(as_of_by_company)),
                Transaction.action == "buy",
            )
            .group_by(Transaction.company_id)
        ).all()
    )
    result: dict[int, dict] = {}
    for company_id, as_of in as_of_by_company.items():
        first_buy = first_buys.get(company_id)
        if first_buy is None:
            result[company_id] = {
                "first_buy_date": None,
                "holding_days": None,
                "fiscal_bucket": None,
            }
            continue
        holding_days = (as_of - first_buy).days
        result[company_id] = {
            "first_buy_date": first_buy.isoformat(),
            "holding_days": holding_days,
            "fiscal_bucket": (
                "largo_plazo" if holding_days > LONG_TERM_HOLDING_DAYS else "corto_plazo"
            ),
        }
    return result


class PortfolioTransactionInput(BaseModel):
    ticker: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9.\-]+$")
    action: Literal["buy", "sell", "dividend", "interest", "fee", "cash_misc"]
    quantity: Decimal = Field(ge=0)
    price: Decimal = Field(ge=0)
    trade_date: date
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=10)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("trade_date")
    @classmethod
    def _no_future_trade_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("trade_date cannot be in the future")
        return value


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
        "data_as_of": risk.get("data_as_of"),
        "provenance": risk.get("provenance"),
    }


@router.get("/intelligence")
def portfolio_intelligence(
    years: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
) -> dict:
    return PortfolioIntelligenceService().build(db, years=years)


@router.get("/snapshots")
def portfolio_snapshots(
    start: date | None = None,
    limit: int = Query(default=1000, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {
            "id": snapshot.id,
            "portfolio_id": snapshot.portfolio_id,
            "snapshot_date": snapshot.snapshot_date,
            "base_currency": snapshot.base_currency,
            "positions_value_base": snapshot.positions_value_base,
            "cash_value_base": snapshot.cash_value_base,
            "total_value_base": snapshot.total_value_base,
            "net_external_flow_base": snapshot.net_external_flow_base,
            "daily_return": snapshot.daily_return,
            "cumulative_twr": snapshot.cumulative_twr,
            "pricing_coverage": snapshot.pricing_coverage,
            "source": snapshot.source,
            "metadata": snapshot.metadata_,
        }
        for snapshot in PortfolioSnapshotService().history(db, start=start, limit=limit)
    ]


@router.post("/snapshots/capture")
def capture_portfolio_snapshot(
    as_of: date | None = None,
    db: Session = Depends(get_db),
) -> dict:
    snapshot = PortfolioSnapshotService().capture(
        db,
        as_of=as_of,
        source="manual_capture",
    )
    db.commit()
    db.refresh(snapshot)
    return {
        "id": snapshot.id,
        "snapshot_date": snapshot.snapshot_date,
        "total_value_base": snapshot.total_value_base,
        "pricing_coverage": snapshot.pricing_coverage,
        "daily_return": snapshot.daily_return,
        "cumulative_twr": snapshot.cumulative_twr,
        "metadata": snapshot.metadata_,
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
def list_fx_rates(
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> list[dict]:
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
            select(FXRate)
            .order_by(desc(FXRate.rate_date), FXRate.base_currency, FXRate.quote_currency)
            .limit(limit)
            .offset(offset)
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


@router.post("/dividends/sync")
async def sync_portfolio_dividends(db: Session = Depends(get_db)) -> dict:
    """Ingest declared dividends for every held company from the data provider.

    Deduped per (company, ex_date, amount). Provider failures mark the symbol
    unavailable; nothing is fabricated. Dividend cash stays a manual ledger
    entry.
    """
    return await DividendIngestionService().sync_portfolio(db)


@router.get("/dividends")
def portfolio_dividends(db: Session = Depends(get_db)) -> dict:
    """Trailing-12-month declared dividend yield per position and portfolio.

    Coverage is explicit: positions without ingested dividend records show
    null yields instead of zeros.
    """
    return DividendIngestionService().portfolio_yields(db)


@router.get("/tearsheet")
def portfolio_tearsheet(db: Session = Depends(get_db)) -> dict:
    """Tearsheet del portfolio: Sharpe, Sortino, drawdown, win rate y exposición.

    Lee la serie de retornos de los snapshots persistidos (ver
    ``TearsheetService``); sin portfolio o sin historial suficiente las
    métricas llegan a None en lugar de fallar.
    """
    return TearsheetService().build(db)


@router.get("/positions")
def positions(
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.execute(
        select(Position, Company)
        .join(Company, Position.company_id == Company.id)
        .order_by(Company.ticker)
        .limit(limit)
        .offset(offset)
    ).all()
    fiscal = _fiscal_info_batch(
        db, {company.id: position.as_of for position, company in rows}
    )
    payloads = []
    for position, company in rows:
        fiscal_info = fiscal.get(company.id) or _fiscal_info(db, company.id, position.as_of)
        payloads.append(
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
            "first_buy_date": fiscal_info["first_buy_date"],
            "holding_days": fiscal_info["holding_days"],
            "fiscal_bucket": fiscal_info["fiscal_bucket"],
            }
        )
    return payloads


@router.get("/transactions")
def transactions(
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.execute(
        select(Transaction, Company)
        .join(Company, Transaction.company_id == Company.id)
        .where(Transaction.action.in_(["buy", "sell"]))
        .order_by(desc(Transaction.trade_date), desc(Transaction.created_at))
        .limit(limit)
        .offset(offset)
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
    except PortfolioOversellError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Insufficient shares for sale"
        ) from exc
    except PortfolioMixedCurrencyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=422, detail="Position cannot mix transaction currencies"
        ) from exc
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
    company = resolve_company(db, ticker)
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


@router.post("/refresh-market")
async def refresh_portfolio_market_data(
    as_of: date | None = None,
    db: Session = Depends(get_db),
) -> dict:
    try:
        return await MarketRefreshService().refresh(db, as_of=as_of)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    try:
        return IBKRImportService().import_flex_xml(db, payload.xml)
    except IBKRImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import/ibkr/csv")
def import_ibkr_csv(payload: IBKRCsvImportRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return IBKRImportService().import_ibkr_csv(db, payload.csv)
    except IBKRImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
