from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Company, FundManager, ManagerHolding, Position
from app.models.entities import Base, InstrumentReference
from app.services.investor_overlap import _cusip, portfolio_overlap


def setup_portfolio():
    db = Session(create_engine("sqlite://"))
    Base.metadata.create_all(db.get_bind())
    company = Company(ticker="AAPL", name="Apple", exchange="NASDAQ", company_type="mature", valuation_model="dcf", isin="US0378331005")
    private = Company(ticker="PRIVATE", name="Private", exchange="NASDAQ", company_type="mature", valuation_model="dcf")
    db.add_all([company, private])
    db.flush()
    db.add_all([Position(tenant_id=1, company_id=company.id, quantity=2),
                Position(tenant_id=2, company_id=private.id, quantity=2)])
    manager = FundManager(cik="0001067983", name="Berkshire", last_report_date=date(2026, 6, 30), coverage="partial")
    db.add(manager)
    db.flush()
    for accession, filing, cusip, put_call in [("A-1", date(2026, 8, 14), "037833100", ""),
                                               ("A-2", date(2026, 8, 20), "037833100", ""),
                                               ("A-2", date(2026, 8, 20), "037833100", "CALL")]:
        db.add(ManagerHolding(manager_id=manager.id, accession_number=accession, report_date=date(2026, 6, 30),
                              filing_date=filing, name_of_issuer="Apple", title_of_class="COM", cusip=cusip,
                              put_call=put_call, value_usd_thousands=Decimal(100), shares=Decimal(10),
                              filing_url="https://www.sec.gov/Archives/example"))
    db.commit()
    db.info["tenant_id"] = 1
    return db


def test_exact_isin_derivation_and_invalid_checksum():
    company = Company(isin="US0378331005")
    assert _cusip(company, None)[0] == "037833100"
    company.isin = "US0378331006"
    assert _cusip(company, None) == (None, None)
    company.isin = "GB0378331005"
    assert _cusip(company, None) == (None, None)


def test_overlap_latest_filing_no_options_no_other_tenant():
    result = portfolio_overlap(setup_portfolio())
    assert result["status"] == "ok" and result["kind"] == "derivado"
    assert len(result["positions"]) == 1
    position = result["positions"][0]
    assert position["status"] == "coincidencia" and len(position["holders"]) == 1
    assert position["holders"][0]["filing_date"] == "2026-08-20"
    assert position["holders"][0]["report_date"] == "2026-06-30"
    assert position["holders"][0]["coverage"] == "partial"


def test_unknown_identity_never_claims_not_owned(monkeypatch):
    db = setup_portfolio()
    company = db.query(Company).filter_by(ticker="AAPL").one()
    company.isin = None
    db.commit()
    import app.services.investor_overlap as overlap
    monkeypatch.setattr(overlap, "most_bought", lambda db: {"items": [{"cusip": "123456789", "buyers_count": 3}], "report_dates": []})
    result = portfolio_overlap(db)
    assert result["unresolved_positions"] == 1
    assert result["not_owned"] == []
    assert result["positions"][0]["status"] == "sin_identificador"


def test_reference_exact_ticker_can_match_without_isin():
    db = setup_portfolio()
    company = db.query(Company).filter_by(ticker="AAPL").one()
    company.isin = None
    db.add(InstrumentReference(ticker_normalized="AAPL", cusip="037833100", source="openfigi", as_of=date(2026, 10, 1)))
    db.commit()
    assert portfolio_overlap(db)["positions"][0]["status"] == "coincidencia"


def test_empty_and_missing_tenant():
    db = setup_portfolio()
    db.info.clear()
    assert portfolio_overlap(db)["status"] == "sin_datos"
    db.info["tenant_id"] = 9
    assert portfolio_overlap(db)["positions"] == []


def test_joint_buys_exclude_owned_and_single_buyers(monkeypatch):
    db = setup_portfolio()
    import app.services.investor_overlap as overlap
    monkeypatch.setattr(overlap, "most_bought", lambda db: {"items": [
        {"cusip": "037833100", "buyers_count": 3},
        {"cusip": "111111111", "buyers_count": 1},
        {"cusip": "222222222", "buyers_count": 2},
    ], "report_dates": ["2026-06-30"]})
    result = portfolio_overlap(db)
    assert result["not_owned"] == [{"cusip": "222222222", "buyers_count": 2}]
    assert result["comparison_complete"] is False
