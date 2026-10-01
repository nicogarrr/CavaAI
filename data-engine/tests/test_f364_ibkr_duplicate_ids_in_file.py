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
