"""Tests for the IBKR Flex import pipeline (IBKRImportService)."""
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import CashBalance, Company, Position, Tenant, Transaction
from app.services.ibkr_import_service import IBKRImportService

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse queryName="test">
  <FlexStatements>
    <FlexStatement accountId="U123456">
      <OpenPosition symbol="AAPL" position="10" markPrice="180.5" positionValue="1805" costBasisPrice="150" currency="USD" reportDate="2026-08-20"/>
      <OpenPosition symbol="MSFT" position="5" markPrice="400" positionValue="2000" costBasisPrice="350" currency="USD" reportDate="2026-08-20"/>
      <CashReport currency="USD" endingCash="1234.56" settledCash="1000" reportDate="2026-08-20"/>
      <Trade symbol="AAPL" tradeID="T1" buySell="BUY" quantity="10" tradePrice="150" ibCommission="1" tradeDate="2026-06-01" currency="USD"/>
      <CashTransaction type="Dividends" trxID="D1" amount="15.5" dateTime="2026-07-01" currency="USD"/>
      <CashTransaction type="Other Fees" trxID="F1" amount="-3.2" dateTime="2026-07-02" currency="USD"/>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>"""


def _tenant_session(engine) -> Session:
    db = Session(engine)
    tenant = db.query(Tenant).filter_by(external_id="ibkr-test").first()
    if tenant is None:
        tenant = Tenant(external_id="ibkr-test", name="IBKR test")
        db.add(tenant)
        db.flush()
    db.info["tenant_id"] = tenant.id
    return db


def test_import_flex_xml_creates_positions_cash_and_transactions():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with _tenant_session(engine) as db:
        result = IBKRImportService().import_flex_xml(db, SAMPLE_XML)

        assert result["status"] == "imported"
        assert result["positions_imported"] == 2
        assert result["cash_imported"] == 1
        assert result["trades_imported"] == 1
        assert result["dividends_imported"] == 1
        assert result["fees_imported"] == 1
        assert result["portfolio_snapshot_id"] is not None

        assert db.query(Position).count() == 2
        assert db.query(CashBalance).count() == 1
        assert db.query(Transaction).count() == 3
        assert db.query(Company).count() == 2

        aapl = db.query(Company).filter_by(ticker="AAPL").one()
        position = db.query(Position).filter_by(company_id=aapl.id).one()
        assert position.quantity == Decimal("10")
        assert position.average_cost == Decimal("150")
        assert position.market_value == Decimal("1805")
        assert position.source == "ibkr_flex"

        trade = db.query(Transaction).filter_by(external_id="T1").one()
        assert trade.action == "buy"
        assert trade.price == Decimal("150")
        assert trade.fees == Decimal("1")

        dividend = db.query(Transaction).filter_by(external_id="D1").one()
        assert dividend.action == "dividend"
        assert dividend.company_id is None


def test_reimport_is_idempotent_by_external_id():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with _tenant_session(engine) as db:
        first = IBKRImportService().import_flex_xml(db, SAMPLE_XML)
        second = IBKRImportService().import_flex_xml(db, SAMPLE_XML)

        assert first["trades_imported"] == 1
        assert second["trades_imported"] == 0
        assert second["dividends_imported"] == 0
        assert second["fees_imported"] == 0
        assert db.query(Transaction).count() == 3
        assert db.query(Position).count() == 2


def test_import_creates_unknown_companies_as_placeholders():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    xml = SAMPLE_XML.replace("symbol=\"AAPL\"", "symbol=\"ZZZZ\"")
    with _tenant_session(engine) as db:
        IBKRImportService().import_flex_xml(db, xml)
        company = db.query(Company).filter_by(ticker="ZZZZ").one()
        assert company.company_type == "imported_holding"
        assert "IBKR" in company.special_sources
        assert company.currency == "USD"