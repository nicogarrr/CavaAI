import hashlib
from pathlib import Path

import pytest
from lxml import html

from app.services.itu_listing_connector import LIST_URL, discover_itu_notices, parse_listing

FIXTURE = Path(__file__).parent / "fixtures" / "itu" / "asreceived-listing.html"


def test_official_listing_real_capture_emits_unassigned_notice():
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "383fad2778ed7a90aa6c0facaa6cf1cab8bf39b505879324f404af4db2c8b9c3"
    notices = parse_listing(raw)
    match = next(row for row in notices if row.submission_id == "72184")
    assert match.reference == "D2026-84958" and match.satellite_name == "D-BLUEBIRD"
    assert match.br_registry_date == "24.09.2026" and match.act_code == "M"
    assert match.ticker is None and match.date_source == "br_registry_date_not_publication"
    assert match.detail_url == "https://www.itu.int/ITU-R/space/asreceived/Publication/DisplayPublication/72184"
    assert len(notices) <= 30


def test_malformed_identity_fails_closed():
    tree = html.fromstring(FIXTURE.read_bytes())
    row = tree.xpath("//*[@data-submission-id='72184']")[0]
    row.attrib.pop("data-submission-id")
    with pytest.raises(ValueError, match="Malformed"):
        parse_listing(html.tostring(tree))


def test_discovery_reports_partial_coverage_and_detects_duplicate_page(monkeypatch):
    from app.services import itu_listing_connector as module

    def fetch(url, **kwargs):
        return FIXTURE.read_bytes(), "text/html", url

    monkeypatch.setattr(module, "fetch_public_url", fetch)
    notices, coverage = discover_itu_notices(max_pages=1)
    assert len(notices) == 30 and coverage == {"seen": 30, "reported_total": 517,
                                               "pages": 1, "complete": False}
    with pytest.raises(ValueError, match="pagination"):
        discover_itu_notices(max_pages=2)
    monkeypatch.setattr(module, "fetch_public_url", lambda url, **kw: (FIXTURE.read_bytes(), "text/html", "https://www.itu.int/other"))
    with pytest.raises(ValueError, match="Unexpected"):
        discover_itu_notices()


def test_real_second_page_uses_site_encoded_paging_and_unique_ids(monkeypatch):
    from app.services import itu_listing_connector as module
    page2 = (Path(__file__).parent / "fixtures" / "itu" / "asreceived-page2.html").read_bytes()
    assert hashlib.sha256(page2).hexdigest() == "021691ed892522e9204658fe5d83f95e9780e019f3e0fd1a809ca55a1376ec71"
    requested = []

    def fetch(url, **kwargs):
        requested.append(url)
        return (FIXTURE.read_bytes() if url == LIST_URL else page2), "text/html", url

    monkeypatch.setattr(module, "fetch_public_url", fetch)
    notices, coverage = discover_itu_notices(max_pages=2)
    assert coverage == {"seen": 60, "reported_total": 517, "pages": 2, "complete": False}
    assert len({notice.submission_id for notice in notices}) == 60
    assert requested[1] == module._page_url(30)
    assert "publication-table.p=" in requested[1]


def test_persist_registry_candidates_without_ticker_or_alerts():
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.models.entities import Base, ITUNotice, NewsEvent, ResearchAlert, Tenant
    from app.services.itu_listing_connector import persist_unassigned_notices

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        tenant = Tenant(external_id="itu-unassigned", name="A")
        session.add(tenant)
        session.commit()
        session.info["tenant_id"] = tenant.id
        candidate = next(c for c in parse_listing(FIXTURE.read_bytes()) if c.submission_id == "72184")
        now = datetime(2026, 9, 27, tzinfo=UTC)
        assert persist_unassigned_notices(session, [candidate], observed_at=now)["company_alerts"] == 0
        first = session.scalar(select(ITUNotice))
        assert first.first_seen_at.replace(tzinfo=UTC) == now
        assert first.metadata_["identity_status"] == "unassigned"
        assert persist_unassigned_notices(session, [candidate], observed_at=now + timedelta(days=1))["created"] == 0
        assert session.scalar(select(ITUNotice)).first_seen_at.replace(tzinfo=UTC) == now
        assert session.scalars(select(NewsEvent)).all() == []
        assert session.scalars(select(ResearchAlert)).all() == []
    engine.dispose()
