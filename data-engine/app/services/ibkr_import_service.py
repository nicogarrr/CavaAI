from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CashBalance, Company, Position, Transaction
from app.services.portfolio_fx_service import PortfolioFXService


def _tag_name(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _decimal(value: str | None, default: str = "0") -> Decimal:
    if value in (None, ""):
        value = default
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _date(value: str | None) -> date:
    if not value:
        return date.today()
    normalized = value.split(";", 1)[0].split(" ", 1)[0]
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    return date.today()


def _attr(element: ElementTree.Element, *names: str) -> str | None:
    lowered = {key.lower(): value for key, value in element.attrib.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return value
    return None


class IBKRImportService:
    def import_flex_xml(self, db: Session, xml_text: str) -> dict:
        root = ElementTree.fromstring(xml_text)
        fx_service = PortfolioFXService()
        portfolio = fx_service.ensure_portfolio(db)
        companies: dict[str, Company] = {}
        positions_imported = 0
        cash_imported = 0
        trades_imported = 0
        dividends_imported = 0
        fees_imported = 0
        cash_transactions_imported = 0

        for element in root.iter():
            tag = _tag_name(element)
            if tag == "OpenPosition":
                symbol = _attr(element, "symbol", "underlyingSymbol")
                if not symbol:
                    continue
                company = self._company(db, companies, symbol)
                quantity = _decimal(_attr(element, "position", "quantity"))
                market_price = _decimal(_attr(element, "markPrice", "marketPrice", "price"))
                market_value = _decimal(_attr(element, "positionValue", "marketValue"))
                if market_value == 0 and market_price and quantity:
                    market_value = quantity * market_price
                average_cost = _decimal(_attr(element, "costBasisPrice", "costPrice", "avgPrice"))
                position = db.scalar(select(Position).where(Position.company_id == company.id))
                if position is None:
                    position = Position(company_id=company.id, portfolio_id=portfolio.id)
                    db.add(position)
                position.quantity = quantity
                position.average_cost = average_cost
                position.market_price = market_price
                position.market_value = market_value
                position.unrealized_pnl = _decimal(_attr(element, "fifoPnlUnrealized", "unrealizedPnl"))
                position.currency = _attr(element, "currency") or company.currency
                position.portfolio_id = portfolio.id
                position.base_currency = portfolio.base_currency
                position.as_of = _date(_attr(element, "reportDate", "asOfDate"))
                position.market_value_native = market_value
                position.cost_basis_native = quantity * average_cost
                rate = fx_service.rate(
                    db,
                    quote_currency=position.currency,
                    base_currency=portfolio.base_currency,
                    as_of=position.as_of,
                )
                position.fx_rate = rate
                position.market_value_base = market_value * rate if rate is not None else None
                position.cost_basis_base = (
                    position.cost_basis_native * rate if rate is not None else None
                )
                position.unrealized_pnl_base = (
                    position.market_value_base - position.cost_basis_base
                    if position.market_value_base is not None
                    and position.cost_basis_base is not None
                    else None
                )
                position.source = "ibkr_flex"
                positions_imported += 1

            elif tag == "CashReport":
                currency = _attr(element, "currency")
                if not currency:
                    continue
                cash = db.scalar(select(CashBalance).where(CashBalance.currency == currency))
                if cash is None:
                    cash = CashBalance(currency=currency)
                    db.add(cash)
                cash.balance = _decimal(_attr(element, "endingCash", "cash", "balance"))
                cash.settled_cash = _decimal(_attr(element, "settledCash", "endingSettledCash"), str(cash.balance))
                cash.interest_rate = _decimal(_attr(element, "interestRate"))
                cash.source = "ibkr_flex"
                cash.as_of = _date(_attr(element, "reportDate", "asOfDate"))
                cash_imported += 1

            elif tag == "Trade":
                symbol = _attr(element, "symbol", "underlyingSymbol")
                if not symbol:
                    continue
                external_id = _attr(element, "tradeID", "transactionID", "ibExecID")
                if external_id and db.scalar(select(Transaction).where(Transaction.external_id == external_id)):
                    continue
                company = self._company(db, companies, symbol)
                action = self._action(_attr(element, "buySell", "transactionType", "tradeType"))
                quantity = abs(_decimal(_attr(element, "quantity", "shares")))
                transaction = Transaction(
                    portfolio_id=portfolio.id,
                    company_id=company.id,
                    trade_date=_date(_attr(element, "tradeDate", "dateTime", "date")),
                    action=action,
                    quantity=quantity,
                    price=_decimal(_attr(element, "tradePrice", "price")),
                    fees=abs(_decimal(_attr(element, "ibCommission", "commission", "fees"))),
                    currency=_attr(element, "currency") or company.currency,
                    external_id=external_id,
                    raw_payload=dict(element.attrib),
                )
                db.add(transaction)
                trades_imported += 1

            elif tag == "CashTransaction":
                type_attr = (_attr(element, "type", "transactionType", "activityType") or "").lower()
                if "dividend" in type_attr:
                    action = "dividend"
                elif "interest" in type_attr:
                    action = "interest"
                elif "fee" in type_attr or "commission" in type_attr:
                    action = "fee"
                else:
                    action = "cash_misc"
                external_id = _attr(element, "trxID", "transactionID", "id")
                if external_id and db.scalar(select(Transaction).where(Transaction.external_id == external_id)):
                    continue
                amount = _decimal(_attr(element, "amount", "netCash", "proceeds"))
                transaction = Transaction(
                    portfolio_id=portfolio.id,
                    company_id=None,
                    trade_date=_date(_attr(element, "dateTime", "date", "tradeDate")),
                    action=action,
                    quantity=Decimal("1"),
                    price=amount,
                    fees=Decimal("0"),
                    currency=_attr(element, "currency") or "USD",
                    external_id=external_id,
                    raw_payload=dict(element.attrib),
                )
                db.add(transaction)
                if action == "dividend":
                    dividends_imported += 1
                elif action == "fee":
                    fees_imported += 1
                else:
                    cash_transactions_imported += 1

            elif tag == "CorporateAction":
                ca_type = (_attr(element, "type", "activityType") or "").upper()
                if ca_type not in {"DIV", "DIVIDEND", "PD", "PI"}:
                    continue
                action = "dividend"
                external_id = _attr(element, "transactionID", "id")
                if external_id and db.scalar(select(Transaction).where(Transaction.external_id == external_id)):
                    continue
                symbol = _attr(element, "symbol", "underlyingSymbol")
                company_id = None
                if symbol:
                    corp_company = self._company(db, companies, symbol)
                    company_id = corp_company.id
                amount = _decimal(_attr(element, "amount", "proceeds", "netCash"))
                transaction = Transaction(
                    portfolio_id=portfolio.id,
                    company_id=company_id,
                    trade_date=_date(_attr(element, "dateTime", "date", "tradeDate")),
                    action=action,
                    quantity=Decimal("1"),
                    price=amount,
                    fees=Decimal("0"),
                    currency=_attr(element, "currency") or "USD",
                    external_id=external_id,
                    raw_payload=dict(element.attrib),
                )
                db.add(transaction)
                dividends_imported += 1

        db.commit()
        return {
            "status": "imported",
            "positions_imported": positions_imported,
            "cash_imported": cash_imported,
            "trades_imported": trades_imported,
            "dividends_imported": dividends_imported,
            "fees_imported": fees_imported,
            "cash_transactions_imported": cash_transactions_imported,
        }

    def _company(self, db: Session, cache: dict[str, Company], symbol: str) -> Company:
        ticker = symbol.upper().strip()
        if ticker in cache:
            return cache[ticker]
        company = db.scalar(select(Company).where(Company.ticker == ticker))
        if company is None:
            company = Company(
                ticker=ticker,
                name=ticker,
                exchange="UNKNOWN",
                currency="USD",
                sector="Unknown",
                industry="Unknown",
                company_type="imported_holding",
                valuation_model="unassigned",
                special_sources=["IBKR"],
                special_risks=[],
                factor_tags=[],
            )
            db.add(company)
            db.flush()
        cache[ticker] = company
        return company

    def _action(self, value: str | None) -> str:
        normalized = (value or "").strip().lower()
        if normalized in {"buy", "bot", "b"}:
            return "buy"
        if normalized in {"sell", "sold", "s"}:
            return "sell"
        return normalized or "trade"
