"""F364: external ids repetidos dentro del mismo XML no abortan la importación."""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Transaction
from app.services.ibkr_import_service import IBKRImportService
from tests.test_ibkr_import import _tenant_session

TRADE = '<Trade symbol="AAPL" tradeID="T1" quantity="5" tradePrice="100" tradeDate="2026-08-20" buySell="BUY" currency="USD"/>'
OTHER = '<Trade symbol="MSFT" tradeID="T2" quantity="2" tradePrice="300" tradeDate="2026-08-20" buySell="BUY" currency="USD"/>'


def test_duplicate_trade_id_in_same_file_imports_once():
    xml = (
        '<?xml version="1.0"?><FlexQueryResponse><FlexStatements><FlexStatement accountId="U1">'
        + TRADE + TRADE + OTHER
        + "</FlexStatement></FlexStatements></FlexQueryResponse>"
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db: Session = _tenant_session(engine)
    IBKRImportService().import_flex_xml(db, xml)
    ids = sorted(t.external_id for t in db.query(Transaction).all())
    db.close()
    assert ids == ["T1", "T2"]


def _run(*rows):
    xml = (
        '<?xml version="1.0"?><FlexQueryResponse><FlexStatements><FlexStatement accountId="U1">'
        + "".join(rows)
        + "</FlexStatement></FlexStatements></FlexQueryResponse>"
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db: Session = _tenant_session(engine)
    result = IBKRImportService().import_flex_xml(db, xml)
    ids = sorted(t.external_id for t in db.query(Transaction).all())
    db.close()
    return result, ids


BAD_DIV = '<CorporateAction transactionID="D1" type="DIV" amount="10" currency="USD" symbol="AAPL"/>'
GOOD_DIV = '<CorporateAction transactionID="D1" type="DIV" amount="10" date="2026-08-20" currency="USD" symbol="AAPL"/>'
CASH = '<CashTransaction transactionID="C1" type="Dividends" amount="5" date="2026-08-20" currency="USD" symbol="AAPL"/>'


def test_invalid_then_valid_corporate_action_same_id_keeps_the_valid_one():
    result, ids = _run(BAD_DIV, GOOD_DIV)
    assert ids == ["D1"]
    assert result["dividends_imported"] == 1


def test_valid_duplicates_in_cash_and_corporate_import_once():
    result, ids = _run(CASH, CASH, GOOD_DIV, GOOD_DIV)
    assert ids == ["C1", "D1"]
