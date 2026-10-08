"""Cartera de inversores: etiquetas, fechas y SIN_DATOS sin inventar nada."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.entities import Base, FundManager, InvestorMovement, InvestorPosition, ManagerHolding
from app.services import investor_portfolio as ip
from app.services.investor_portfolio import LABELS, datum, investor_portfolio, sync_form4

FORM4 = """<?xml version="1.0"?><ownershipDocument><documentType>4</documentType>
<periodOfReport>2024-12-17</periodOfReport>
<issuer><issuerCik>0001849635</issuerCik><issuerName>Trump Media &amp; Technology Group Corp.</issuerName>
<issuerTradingSymbol>DJT</issuerTradingSymbol></issuer>
<reportingOwner><reportingOwnerId><rptOwnerCik>0000947033</rptOwnerCik><rptOwnerName>TRUMP DONALD J</rptOwnerName></reportingOwnerId>
<reportingOwnerRelationship><isTenPercentOwner>1</isTenPercentOwner></reportingOwnerRelationship></reportingOwner>
<nonDerivativeTable><nonDerivativeTransaction><securityTitle><value>Common Stock</value></securityTitle>
<transactionDate><value>2024-12-17</value></transactionDate>
<transactionCoding><transactionCode>G</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>114750000</value></transactionShares>
<transactionPricePerShare><value>0</value></transactionPricePerShare>
<transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode></transactionAmounts>
</nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>"""

FILING = {
    "form": "4",
    "accession_number": "0009999999-24-000001",
    "filing_date": "2024-12-19",
    "index_url": "https://www.sec.gov/Archives/edgar/data/947033/000999999924000001/",
    "document_url": "https://www.sec.gov/Archives/edgar/data/947033/000999999924000001/x.xml",
}


def _db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_datum_without_value_is_sin_datos():
    d = datum(None, "OFICIAL", date(2025, 1, 1), "http://x")
    assert d == {"value": None, "label": "SIN_DATOS", "as_of": None, "source_url": None}


def test_datum_rejects_bad_label_and_valued_sin_datos():
    with pytest.raises(ValueError):
        datum(1, "ESTIMADO", None)
    with pytest.raises(ValueError):
        datum(1, "SIN_DATOS", None)
    assert set(LABELS) == {"OFICIAL", "INFERIDO", "SIN_DATOS"}


def test_unknown_investor_is_none():
    assert investor_portfolio(_db(), "nadie") is None


def test_trump_portfolio_is_official_shares_and_no_invented_value():
    out = investor_portfolio(_db(), "trump")
    assert out is not None and out["status"] == "ok" and out["has_13f"] is False
    (pos,) = out["positions"]
    assert pos["ticker"] == "DJT"
    assert pos["shares"]["value"] == 114_750_000.0
    assert pos["shares"]["label"] == "OFICIAL"
    assert pos["shares"]["as_of"] == "2025-12-18"
    assert pos["shares"]["source_url"].startswith("https://www.sec.gov/")
    assert pos["ownership_pct"]["value"] == 41.5
    # sin precio con fuente: ni valor ni peso
    assert pos["value_usd"] == {"value": None, "label": "SIN_DATOS", "as_of": None, "source_url": None}
    assert pos["weight_pct"]["label"] == "SIN_DATOS"
    assert out["total_value_usd"]["label"] == "SIN_DATOS"


def test_trump_movements_latest_first_and_gift_is_not_a_sale():
    out = investor_portfolio(_db(), "trump")
    assert out is not None
    dates = [m["date"] for m in out["movements"]]
    assert dates == sorted(dates, reverse=True)
    latest = out["movements"][0]
    assert latest["action"] == "donacion" and latest["transaction_code"] == "G"
    assert "No es una venta" in latest["note"]
    assert all(m["shares"]["label"] == "OFICIAL" for m in out["movements"])
    assert all(m["shares"]["as_of"] for m in out["movements"])


def test_investor_without_any_source_is_sin_datos():
    out = investor_portfolio(_db(), "barron-trump")
    assert out is not None
    assert out["status"] == "sin_datos" and out["positions"] == [] and out["movements"] == []
    assert out["note"].startswith("Sin datos")


def test_db_position_overrides_curated_and_weights_need_every_value():
    db = _db()
    db.add(
        InvestorPosition(
            investor_slug="trump",
            issuer_name="Trump Media & Technology Group Corp.",
            issuer_cik="0001849635",
            ticker="DJT",
            security_title="Common Stock, par value $0.0001 per share",
            shares=Decimal("1"),
            as_of=date(2025, 12, 18),
            label="OFICIAL",
            source_form="X",
        )
    )
    db.add(
        InvestorPosition(
            investor_slug="trump",
            issuer_name="Otra SA",
            issuer_cik="0000000001",
            ticker="OTR",
            security_title="Common",
            shares=Decimal("5"),
            value_usd=Decimal("100"),
            value_label="INFERIDO",
            as_of=date(2026, 1, 1),
            label="OFICIAL",
        )
    )
    db.commit()
    out = investor_portfolio(db, "trump")
    assert out is not None
    by = {p["ticker"]: p for p in out["positions"]}
    assert by["DJT"]["shares"]["value"] == 1.0  # la BD gana
    assert by["OTR"]["value_usd"]["label"] == "INFERIDO"
    # DJT no tiene valor => ningun peso se inventa
    assert all(p["weight_pct"]["value"] is None for p in out["positions"])
    assert out["as_of"] == "2026-01-01"


def test_sync_form4_idempotent_and_labels_official():
    db = _db()
    kwargs = {"fetch": lambda url: FORM4, "filings": [FILING]}
    assert sync_form4(db, "trump", **kwargs) == 1
    assert sync_form4(db, "trump", **kwargs) == 0
    row = db.scalars(select(InvestorMovement)).one()
    assert (row.action, row.transaction_code, row.label) == ("donacion", "G", "OFICIAL")
    assert row.shares == Decimal("114750000") and row.movement_date == date(2024, 12, 17)
    out = investor_portfolio(db, "trump")
    assert out is not None
    assert any(m["shares"]["source_url"] == FILING["index_url"] for m in out["movements"])


def test_sync_form4_rejects_unreviewed_investor():
    with pytest.raises(ValueError):
        sync_form4(_db(), "buffett", filings=[], fetch=lambda u: "")


def _seed_13f(db: Session) -> None:
    mgr = FundManager(
        cik="0001067983", name="BERKSHIRE HATHAWAY INC", last_report_date=date(2026, 6, 30), coverage="ok"
    )
    db.add(mgr)
    db.flush()
    for cusip, name, value, shares in (("AAA", "ALFA", 300, 30), ("BBB", "BETA", 100, 10)):
        db.add(
            ManagerHolding(
                manager_id=mgr.id,
                accession_number="0000000000-26-000001",
                report_date=date(2026, 6, 30),
                filing_date=date(2026, 8, 14),
                name_of_issuer=name,
                title_of_class="COM",
                cusip=cusip,
                value_usd_thousands=Decimal(value),
                shares=Decimal(shares),
                filing_url="https://www.sec.gov/f",
            )
        )
    db.commit()


def test_13f_investor_weights_are_official_and_sum_to_100():
    db = _db()
    _seed_13f(db)
    out = investor_portfolio(db, "buffett")
    assert out is not None and out["has_13f"] and out["status"] == "ok"
    assert [p["issuer"] for p in out["positions"]] == ["ALFA", "BETA"]
    assert [p["weight_pct"]["value"] for p in out["positions"]] == [75.0, 25.0]
    assert all(
        p["weight_pct"]["label"] == "OFICIAL" and p["weight_pct"]["as_of"] == "2026-06-30"
        for p in out["positions"]
    )
    assert out["movements"] == []  # un solo trimestre: no se inventan movimientos


def test_13f_investor_without_ingested_data_is_sin_datos():
    out = investor_portfolio(_db(), "buffett")
    assert out is not None and out["status"] == "sin_datos" and out["positions"] == []


def test_curated_data_has_source_and_date():
    for p in ip.CURATED_POSITIONS:
        assert p.source_url.startswith("https://www.sec.gov/") and p.accession_number and p.as_of
    for m in ip.CURATED_MOVEMENTS:
        assert m.source_url.startswith("https://www.sec.gov/") and m.accession_number and m.movement_date
