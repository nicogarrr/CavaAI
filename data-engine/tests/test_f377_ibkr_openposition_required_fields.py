"""F377: an OpenPosition missing quantity/price/date must not write zeros or today's date."""
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Position
from app.services.ibkr_import_service import IBKRImportService, validate_flex_xml
from tests.test_ibkr_import import _tenant_session

GOOD = '<OpenPosition symbol="AAPL" position="10" markPrice="180.5" positionValue="1805" costBasisPrice="150" currency="USD" reportDate="2026-08-20"/>'


def _xml(*rows):
    return (
        '<?xml version="1.0"?><FlexQueryResponse><FlexStatements><FlexStatement accountId="U1">'
        + "".join(rows)
        + "</FlexStatement></FlexStatements></FlexQueryResponse>"
    )


def _import(xml):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db: Session = _tenant_session(engine)
    service = IBKRImportService()
    service.import_flex_xml(db, _xml(GOOD))
    result = service.import_flex_xml(db, xml)
    positions = {p.quantity for p in db.query(Position).all()}
    db.close()
    return result, positions


def test_missing_quantity_does_not_overwrite_real_position_with_zero():
    row = '<OpenPosition symbol="AAPL" markPrice="190" positionValue="1900" currency="USD" reportDate="2026-08-21"/>'
    result, positions = _import(_xml(row))
    assert positions == {Decimal("10")}
    assert result["positions_imported"] == 0


def test_missing_price_and_value_is_skipped():
    row = '<OpenPosition symbol="AAPL" position="99" currency="USD" reportDate="2026-08-21"/>'
    _, positions = _import(_xml(row))
    assert positions == {Decimal("10")}


def test_missing_report_date_is_skipped_not_today():
    row = '<OpenPosition symbol="AAPL" position="99" markPrice="190" currency="USD"/>'
    _, positions = _import(_xml(row))
    assert positions == {Decimal("10")}


def test_validation_reports_missing_fields_in_spanish():
    errors = validate_flex_xml(_xml('<OpenPosition symbol="AAPL" markPrice="190"/>'))
    assert any("faltan" in e and "cantidad" in e and "fecha" in e for e in errors)


def test_complete_row_still_imports():
    result, positions = _import(_xml(GOOD.replace('position="10"', 'position="12"')))
    assert positions == {Decimal("12")}
    assert result["positions_imported"] == 1
