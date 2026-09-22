"""S2: per-manager 13F ingestion tests (no network; injectable httpx client)."""

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.entities import Base, FundManager, ManagerHolding
from app.services.connectors import form13f
from app.services.manager_holding_ingestion_service import (
    REVIEWED_MANAGERS,
    ManagerHoldingIngestionService,
)

CIK = "0001067983"

SUBMISSIONS = {
    "filings": {
        "recent": {
            "accessionNumber": ["0000950123-26-000001", "0000950123-26-000002", "0000950123-25-000999"],
            "form": ["13F-HR", "13F-HR/A", "10-K"],
            "reportDate": ["2026-06-30", "2026-06-30", "2025-12-31"],
            "filingDate": ["2026-08-14", "2026-08-20", "2026-02-01"],
            "primaryDocument": ["primary_doc.xml", "primary_doc.xml", "k.htm"],
        }
    }
}

INDEX = {"directory": {"item": [{"name": "primary_doc.xml"}, {"name": "form13fInfoTable.xml"}, {"name": "readme.htm"}]}}

INFO_TABLE = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>75000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>300000000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority>
      <Sole>300000000</Sole>
      <Shared>0</Shared>
      <None>0</None>
    </votingAuthority>
  </infoTable>
  <infoTable>
    <nameOfIssuer>BANK OF AMERICA CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>060505104</cusip>
    <value>40000000</value>
    <shrsOrPrnAmt>
      <sshPrnamt>1000000000</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority>
      <Sole>1000000000</Sole>
      <Shared>0</Shared>
      <None>0</None>
    </votingAuthority>
  </infoTable>
</informationTable>
"""


def _sec_client(fail: bool = False) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if fail:
            return httpx.Response(503, text="down")
        url = str(request.url)
        if url.startswith("https://data.sec.gov/submissions/"):
            return httpx.Response(200, json=SUBMISSIONS)
        if url.endswith("index.json"):
            return httpx.Response(200, json=INDEX)
        if url.endswith("form13fInfoTable.xml"):
            return httpx.Response(200, text=INFO_TABLE)
        return httpx.Response(404, text="not found")

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_parse_information_table_rows():
    rows = form13f.parse_information_table(INFO_TABLE)
    assert len(rows) == 2
    apple = rows[0]
    assert apple["name_of_issuer"] == "APPLE INC"
    assert apple["cusip"] == "037833100"
    assert apple["value_usd_thousands"] == "75000000"
    assert apple["ssh_prnamt"] == "300000000"
    assert apple["voting_sole"] == "300000000"


def test_recent_filings_filters_forms():
    filings = form13f.recent_13f_filings(CIK, client=_sec_client())
    assert [f["form"] for f in filings] == ["13F-HR", "13F-HR/A"]
    assert filings[1]["is_amendment"] is True


def test_information_table_url_skips_primary_document():
    url = form13f.information_table_url(
        CIK, "0000950123-26-000001", "primary_doc.xml", client=_sec_client()
    )
    assert url is not None and url.endswith("form13fInfoTable.xml")


def test_sync_ingests_latest_report_and_is_idempotent(db):
    service = ManagerHoldingIngestionService(client=_sec_client())
    result = service.sync_manager(db, cik=CIK)
    assert result["status"] == "ok"
    assert result["report_date"] == "2026-06-30"
    assert result["ingested_rows"] == 4  # 2 rows x (base + amendment, immutable each)
    assert result["provenance"]["source_kind"] == "official"

    manager = db.scalar(select(FundManager).where(FundManager.cik == CIK))
    assert manager.name == REVIEWED_MANAGERS[CIK]
    assert manager.coverage == "ok"
    rows = db.scalars(select(ManagerHolding)).all()
    assert len(rows) == 4
    accessions = {row.accession_number for row in rows}
    assert accessions == {"0000950123-26-000001", "0000950123-26-000002"}
    assert all(row.cusip and row.filing_url for row in rows)
    assert rows[0].name_of_issuer  # as filed, no ticker inference

    again = service.sync_manager(db, cik=CIK)
    assert again["ingested_rows"] == 0  # idempotent re-sync
    assert len(db.scalars(select(ManagerHolding)).all()) == 4


def test_sync_refuses_unreviewed_manager(db):
    result = ManagerHoldingIngestionService(client=_sec_client()).sync_manager(db, cik="0000000001")
    assert result["status"] == "unreviewed_manager"
    assert db.scalar(select(FundManager)) is None


def test_sync_marks_unavailable_on_http_error(db):
    result = ManagerHoldingIngestionService(client=_sec_client(fail=True)).sync_manager(db, cik=CIK)
    assert result["status"] == "unavailable"
    assert result["provenance"]["coverage"] == "unavailable"
    manager = db.scalar(select(FundManager).where(FundManager.cik == CIK))
    assert manager.coverage == "unavailable"


def test_latest_holdings_serves_latest_report(db):
    service = ManagerHoldingIngestionService(client=_sec_client())
    assert service.latest_holdings(db, cik=CIK)["status"] == "unavailable"
    service.sync_manager(db, cik=CIK)
    result = service.latest_holdings(db, cik=CIK)
    assert result["status"] == "ok"
    assert result["report_date"] == "2026-06-30"
    assert len(result["holdings"]) == 4
    assert result["holdings"][0]["value_usd_thousands"] == 75000000.0
    assert any(h["is_amendment"] for h in result["holdings"])
    assert result["limitations"]
