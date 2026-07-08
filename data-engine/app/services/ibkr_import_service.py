from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CashBalance, Company, Position, Transaction


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
        companies: dict[str, Company] = {}
        positions_imported = 0
        cash_imported = 0
        trades_imported = 0

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
                    position = Position(company_id=company.id)
                    db.add(position)
                position.quantity = quantity
                position.average_cost = average_cost
                position.market_price = market_price
                position.market_value = market_value
                position.unrealized_pnl = _decimal(_attr(element, "fifoPnlUnrealized", "unrealizedPnl"))
                position.currency = _attr(element, "currency") or company.currency
                position.source = "ibkr_flex"
                position.as_of = _date(_attr(element, "reportDate", "asOfDate"))
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

        db.commit()
        return {
            "status": "imported",
            "positions_imported": positions_imported,
            "cash_imported": cash_imported,
            "trades_imported": trades_imported,
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
