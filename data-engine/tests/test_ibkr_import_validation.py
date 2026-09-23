"""Validación robusta del import IBKR: errores en español accionables.

Run from data-engine/:
    pytest tests/test_ibkr_import_validation.py -v
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Position, Tenant, Transaction
from app.services.ibkr_import_service import (
    IBKRImportError,
    IBKRImportService,
    validate_flex_xml,
    validate_ibkr_csv,
)

BROKEN_XML = "<?xml version='1.0'?><FlexQueryResponse><FlexStatements><OpenPosition symbol='AAPL'"

WRONG_ROOT_XML = "<?xml version='1.0'?><html><body>no es un flex</body></html>"

XML_WITH_BAD_ROWS = """<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse queryName="test">
  <FlexStatements>
    <FlexStatement accountId="U123456">
      <OpenPosition symbol="AAPL" position="10" markPrice="180.5" positionValue="1805" costBasisPrice="150" currency="USD" reportDate="2026-08-20"/>
      <OpenPosition position="5" markPrice="400" positionValue="2000" costBasisPrice="350" currency="USD" reportDate="2026-08-20"/>
      <OpenPosition symbol="MSFT" position="cinco" markPrice="400" positionValue="2000" costBasisPrice="350" currency="USD" reportDate="2026-08-20"/>
      <Trade symbol="AAPL" tradeID="T-bad" buySell="BUY" quantity="diez" tradePrice="150" ibCommission="1" tradeDate="2026-06-01" currency="USD"/>
      <Trade symbol="AAPL" tradeID="T-ok" buySell="BUY" quantity="10" tradePrice="150" ibCommission="1" tradeDate="2026-06-01" currency="USD"/>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>"""

BROKEN_CSV = """symbol,action,quantity,price,date
AAPL,buy,diez,150,2026-06-01
,buy,10,150,2026-06-01
MSFT,buy,5,400,32/13/2026
"""

VALID_CSV = """symbol,action,quantity,price,date,fees,currency
AAPL,buy,10,150,2026-06-01,1,USD
MSFT,buy,5,400,2026-06-02,1,USD
"""


def _tenant_session(engine) -> Session:
    db = Session(engine)
    tenant = db.query(Tenant).filter_by(external_id="ibkr-validation-test").first()
    if tenant is None:
        tenant = Tenant(external_id="ibkr-validation-test", name="IBKR validation test")
        db.add(tenant)
        db.flush()
    db.info["tenant_id"] = tenant.id
    return db


def test_validate_flex_xml_detects_unreadable_file():
    errors = validate_flex_xml(BROKEN_XML)
    assert len(errors) == 1
    assert "no se puede leer" in errors[0]
    assert "IBKR" in errors[0]


def test_validate_flex_xml_detects_wrong_root():
    errors = validate_flex_xml(WRONG_ROOT_XML)
    assert len(errors) == 1
    assert "no parece un Flex Query" in errors[0]


def test_validate_flex_xml_reports_row_and_cause_in_spanish():
    errors = validate_flex_xml(XML_WITH_BAD_ROWS)
    assert len(errors) == 3
    assert any("falta el símbolo" in error and "Fila" in error for error in errors)
    assert any("cinco" in error and "no es un número" in error for error in errors)
    assert any("diez" in error and "no es un número" in error for error in errors)


def test_import_flex_xml_raises_actionable_spanish_error_on_broken_file():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with _tenant_session(engine) as db:
        try:
            IBKRImportService().import_flex_xml(db, BROKEN_XML)
        except IBKRImportError as exc:
            assert "no se puede leer" in str(exc)
        else:
            raise AssertionError("debió lanzar IBKRImportError con el fichero roto")


def test_import_flex_xml_skips_bad_rows_and_reports_them():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with _tenant_session(engine) as db:
        result = IBKRImportService().import_flex_xml(db, XML_WITH_BAD_ROWS)
        assert result["status"] == "imported"
        # Solo AAPL válida + 1 trade válido; el resto se omite con motivo.
        assert result["positions_imported"] == 1
        assert result["trades_imported"] == 1
        assert result["rows_skipped"] == 3
        assert len(result["row_errors"]) == 3
        assert db.query(Position).count() == 1
        assert db.query(Transaction).filter_by(external_id="T-ok").count() == 1
        assert db.query(Transaction).filter_by(external_id="T-bad").count() == 0


def test_validate_ibkr_csv_reports_row_and_cause_in_spanish():
    errors = validate_ibkr_csv(BROKEN_CSV)
    assert len(errors) == 3
    assert any("Fila 2" in error and "diez" in error for error in errors)
    assert any("Fila 3" in error and "falta el símbolo" in error for error in errors)
    assert any("Fila 4" in error and "fecha" in error for error in errors)


def test_validate_ibkr_csv_rejects_missing_action():
    csv_text = "symbol,action,quantity,price,date\nAAPL,,10,150,2026-06-01\n"
    errors = validate_ibkr_csv(csv_text)
    assert len(errors) == 1
    assert "Fila 2" in errors[0]
    assert "falta la acción" in errors[0]


def test_validate_ibkr_csv_rejects_actionless_header_as_fatal():
    csv_text = "symbol,quantity,price,date\nAAPL,10,150,2026-06-01\n"
    errors = validate_ibkr_csv(csv_text)
    assert len(errors) == 1
    assert "cabecera" in errors[0]
    assert "action" in errors[0]

def test_validate_ibkr_csv_rejects_unknown_action():
    csv_text = "symbol,action,quantity,price,date\nAAPL,TRANSFER,10,150,2026-06-01\n"
    errors = validate_ibkr_csv(csv_text)
    assert len(errors) == 1
    assert "Fila 2" in errors[0]
    assert "acción 'TRANSFER' no es buy ni sell" in errors[0]


def test_validate_ibkr_csv_rejects_missing_header():
    errors = validate_ibkr_csv("foo,bar\n1,2\n")
    assert len(errors) == 1
    assert "cabecera" in errors[0]
    assert "symbol" in errors[0]


def test_import_ibkr_csv_skips_missing_and_unknown_actions():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    csv_text = """symbol,action,quantity,price,date,fees,currency
AAPL,,10,150,2026-06-01,1,USD
MSFT,TRANSFER,5,400,2026-06-02,1,USD
NVDA,buy,2,100,2026-06-03,1,USD
"""
    with _tenant_session(engine) as db:
        result = IBKRImportService().import_ibkr_csv(db, csv_text)
        assert result["trades_imported"] == 1
        assert result["rows_skipped"] == 2
        assert len(result["row_errors"]) == 2
        assert any(
            "Fila 2" in error and "falta la acción" in error
            for error in result["row_errors"]
        )
        assert any(
            "Fila 3" in error and "TRANSFER" in error
            for error in result["row_errors"]
        )
        assert db.query(Transaction).count() == 1
        assert db.query(Transaction).one().action == "buy"


def test_import_ibkr_csv_imports_valid_rows_and_reports_bad_ones():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with _tenant_session(engine) as db:
        result = IBKRImportService().import_ibkr_csv(db, VALID_CSV + "ZZZ,buy,xx,10,2026-06-03\n")
        assert result["status"] == "imported"
        assert result["trades_imported"] == 2
        assert result["rows_skipped"] == 1
        assert any("Fila 4" in error for error in result["row_errors"])
        assert db.query(Transaction).count() == 2


def test_import_ibkr_csv_raises_on_empty_file():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with _tenant_session(engine) as db:
        try:
            IBKRImportService().import_ibkr_csv(db, "   ")
        except IBKRImportError as exc:
            assert "vacío" in str(exc)
        else:
            raise AssertionError("debió lanzar IBKRImportError con el fichero vacío")
