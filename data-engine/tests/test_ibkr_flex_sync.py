"""IBKR Flex: efectivo por divisa (CashReportCurrency) y cliente sin fugas de token."""
import asyncio
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import Base
from app.models import CashBalance, Position
from app.services.connectors.ibkr import IBKRFlexClient, IBKRFlexError
from app.services.ibkr_import_service import IBKRImportService
from tests.test_ibkr_import import _tenant_session

CASH = (
    '<CashReport>'
    '<CashReportCurrency currency="BASE_SUMMARY" levelOfDetail="BaseCurrency" fromDate="20261008" toDate="20261008" endingCash="-7969.27" endingSettledCash="-7144.80"/>'
    '<CashReportCurrency currency="AED" levelOfDetail="Currency" fromDate="20261008" toDate="20261008" endingCash="0.000013535" endingSettledCash="0.000013535"/>'
    '<CashReportCurrency currency="EUR" levelOfDetail="Currency" fromDate="20261008" toDate="20261008" endingCash="7433.60" endingSettledCash="7433.60"/>'
    '<CashReportCurrency currency="USD" levelOfDetail="Currency" fromDate="20261008" toDate="20261008" endingCash="-17267.98" endingSettledCash="-16343.68"/>'
    '</CashReport>'
)
POSITION = '<OpenPosition symbol="ASTS" position="190" markPrice="56.93" positionValue="10816.7" costBasisPrice="60.24" currency="USD" reportDate="20261008"/>'


def _xml(body: str) -> str:
    return (
        '<?xml version="1.0"?><FlexQueryResponse><FlexStatements><FlexStatement accountId="U1">'
        + body
        + "</FlexStatement></FlexStatements></FlexQueryResponse>"
    )


def _run_import(body: str):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db: Session = _tenant_session(engine)
    result = IBKRImportService().import_flex_xml(db, _xml(body))
    cash = {c.currency: c for c in db.query(CashBalance).all()}
    positions = db.query(Position).count()
    db.close()
    return result, cash, positions


def test_cash_report_currency_imports_real_currencies_only():
    result, cash, positions = _run_import(CASH + POSITION)
    assert set(cash) == {"EUR", "USD"}  # sin BASE_SUMMARY ni polvo de AED
    assert cash["EUR"].balance == Decimal("7433.60")
    assert cash["USD"].balance == Decimal("-17267.98")  # margen: saldo negativo real
    assert cash["USD"].settled_cash == Decimal("-16343.68")
    assert cash["EUR"].as_of.isoformat() == "2026-10-08"  # toDate, no hoy
    assert result["cash_imported"] == 2
    assert result["rows_skipped"] == 0
    assert positions == 1


def test_reimport_updates_cash_without_duplicates():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db: Session = _tenant_session(engine)
    service = IBKRImportService()
    service.import_flex_xml(db, _xml(CASH))
    service.import_flex_xml(db, _xml(CASH.replace("7433.60", "7500.00")))
    rows = db.query(CashBalance).filter(CashBalance.currency == "EUR").all()
    db.close()
    assert len(rows) == 1 and rows[0].balance == Decimal("7500.00")


def test_blank_flex_tenant_env_is_none():
    assert Settings(ibkr_flex_tenant_id="").ibkr_flex_tenant_id is None
    assert Settings(ibkr_flex_tenant_id="1").ibkr_flex_tenant_id == 1


def _client(monkeypatch, responses):
    client = IBKRFlexClient()
    client.settings = Settings(ibkr_flex_token="SECRET-TOKEN", ibkr_flex_query_id="1614243")
    client.poll_delay_seconds = 0
    calls = []

    async def fake_get(url, params, timeout):
        calls.append(url)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(client, "_get", fake_get)
    return client, calls


def test_statement_retries_while_generating(monkeypatch):
    pending = '<FlexStatementResponse><Status>Warn</Status><ErrorCode>1019</ErrorCode><ErrorMessage>Statement generation in progress</ErrorMessage></FlexStatementResponse>'
    client, calls = _client(monkeypatch, [pending, pending, "<FlexQueryResponse/>"])
    assert asyncio.run(client.fetch_statement("REF")) == "<FlexQueryResponse/>"
    assert len(calls) == 3


def test_statement_permanent_error_does_not_retry(monkeypatch):
    bad = '<FlexStatementResponse><Status>Fail</Status><ErrorCode>1012</ErrorCode><ErrorMessage>Token has expired</ErrorMessage></FlexStatementResponse>'
    client, calls = _client(monkeypatch, [bad])
    with pytest.raises(IBKRFlexError, match="1012"):
        asyncio.run(client.fetch_statement("REF"))
    assert len(calls) == 1


def test_http_error_message_never_contains_token():
    client = IBKRFlexClient()
    client.settings = Settings(ibkr_flex_token="SECRET-TOKEN", ibkr_flex_query_id="1614243")

    class Boom:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None):
            request = httpx.Request("GET", url, params=params)
            raise httpx.HTTPStatusError("boom", request=request, response=httpx.Response(500, request=request))

    import app.services.connectors.ibkr as module
    original = module.httpx.AsyncClient
    module.httpx.AsyncClient = Boom
    try:
        with pytest.raises(IBKRFlexError) as info:
            asyncio.run(client.request_statement())
    finally:
        module.httpx.AsyncClient = original
    assert "SECRET-TOKEN" not in str(info.value)
    assert info.value.__cause__ is None
