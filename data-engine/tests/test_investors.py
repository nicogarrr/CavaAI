"""Modulo Inversores: tabla fija, CIK revisados y resumen sin inventar datos."""

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, FundManager, ManagerHolding
from app.services.investors import (
    INVESTORS,
    NO_13F_NOTE,
    get_investor,
    investor_detail,
    list_investors,
)
from app.services.manager_holding_ingestion_service import (
    REVIEWED_MANAGERS,
    ManagerHoldingIngestionService,
)


def _db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_slugs_unique_and_every_cik_is_reviewed():
    slugs = [i.slug for i in INVESTORS]
    assert len(slugs) == len(set(slugs))
    ciks = [i.cik for i in INVESTORS if i.cik]
    assert len(ciks) == len(set(ciks))
    for cik in ciks:
        assert cik in REVIEWED_MANAGERS, cik


def test_every_reviewed_manager_has_an_investor_entry():
    assert set(REVIEWED_MANAGERS) == {i.cik for i in INVESTORS if i.cik}


def test_pershing_uses_the_new_cik_not_the_13f_nt_one():
    assert "0002026053" in REVIEWED_MANAGERS
    assert "0001336528" not in REVIEWED_MANAGERS
    ackman = get_investor("ackman")
    assert ackman is not None
    assert ackman.cik == "0002026053"


def test_unlisted_ciks_are_refused():
    # Scion (ultimo 13F nov-2025) y Greenlight (feb-2024) quedan fuera.
    for cik in ("0001649339", "0001079114"):
        assert cik not in REVIEWED_MANAGERS
        result = ManagerHoldingIngestionService().sync_manager(_db(), cik=cik)
        assert result["status"] == "unreviewed_manager"


def test_daily_journal_is_never_labelled_as_munger_portfolio():
    inv = get_investor("daily-journal")
    assert inv is not None and inv.kind == "company"
    assert "munger" not in inv.name.lower()
    assert "munger" not in inv.firm.lower()


def test_investors_without_13f_say_so_and_have_no_numbers():
    db = _db()
    result = list_investors(db)
    by_slug = {i["slug"]: i for i in result["investors"]}
    for slug in ("bezos", "mark-leonard", "quintana", "munger", "nick-sleep", "lynch"):
        item = by_slug[slug]
        assert item["has_13f"] is False
        assert item["cik"] is None
        assert item["note"] == NO_13F_NOTE
        assert item["positions"] is None and item["value_usd_thousands"] is None
        detail = investor_detail(db, slug)
        assert detail is not None and detail["holdings"] == []


def test_unsynced_manager_is_honest_empty_not_zero():
    db = _db()
    item = {i["slug"]: i for i in list_investors(db)["investors"]}["buffett"]
    assert item["has_13f"] is True
    assert item["positions"] is None
    assert item["value_usd_thousands"] is None
    assert item["report_date"] is None


def _holding(manager: FundManager, accession: str, filing: date, cusip: str, value: str, name: str):
    return ManagerHolding(
        manager_id=manager.id,
        accession_number=accession,
        report_date=date(2026, 6, 30),
        filing_date=filing,
        name_of_issuer=name,
        title_of_class="COM",
        cusip=cusip,
        value_usd_thousands=Decimal(value),
        shares=Decimal("100"),
        is_amendment=accession.endswith("2"),
    )


def test_summary_uses_latest_accession_so_amendments_do_not_double_count():
    db = _db()
    manager = FundManager(
        cik="0001067983",
        name=REVIEWED_MANAGERS["0001067983"],
        last_report_date=date(2026, 6, 30),
    )
    db.add(manager)
    db.flush()
    db.add_all(
        [
            _holding(manager, "A-1", date(2026, 8, 14), "037833100", "100", "APPLE INC"),
            _holding(manager, "A-1", date(2026, 8, 14), "060505104", "300", "BANK OF AMERICA"),
            _holding(manager, "A-2", date(2026, 8, 20), "037833100", "150", "APPLE INC"),
            _holding(manager, "A-2", date(2026, 8, 20), "060505104", "250", "BANK OF AMERICA"),
        ]
    )
    db.commit()
    item = {i["slug"]: i for i in list_investors(db)["investors"]}["buffett"]
    assert item["positions"] == 2
    assert item["value_usd_thousands"] == 400.0
    assert item["report_date"] == "2026-06-30"
    detail = investor_detail(db, "buffett")
    assert detail is not None
    assert [h["name_of_issuer"] for h in detail["holdings"]] == ["BANK OF AMERICA", "APPLE INC"]
    assert [h["weight_pct"] for h in detail["holdings"]] == [62.5, 37.5]
    assert "ticker" not in detail["holdings"][0]


def test_unknown_slug_has_no_detail():
    assert investor_detail(_db(), "no-existe") is None
