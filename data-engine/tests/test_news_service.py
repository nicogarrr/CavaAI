"""NewsService contract tests.

News ingestion feeds materiality and thesis reviews: tickers must match
on word boundaries only, duplicates must be skipped deterministically,
and ingest accounting must be exact.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, NewsEvent
from app.schemas.api import NewsFeedItem
from app.services.news_service import NewsService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session, ticker: str = "AAPL") -> Company:
    company = Company(
        ticker=ticker, name=f"{ticker} Co", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def test_detect_ticker_respects_word_boundaries(db):
    apple = _company(db, "AAPL")
    service = NewsService()
    assert service.detect_ticker(db, "AAPL beats expectations") is apple
    # Substring inside another word must not match.
    assert service.detect_ticker(db, "The SNAPPIEST pineapple") is None
    assert service.detect_ticker(db, "no tickers here") is None


def test_company_for_item_prefers_explicit_ticker(db):
    apple = _company(db, "AAPL")
    service = NewsService()
    assert service._company_for_item(db, "some text", "aapl") is apple
    # Unknown explicit ticker falls back to text detection.
    assert service._company_for_item(db, "AAPL mentioned", "MSFT") is apple


def _event(db: Session, company: Company, *, title: str, url: str | None) -> NewsEvent:
    event = NewsEvent(
        company_id=company.id, title=title, url=url, source="feed",
        event_type="news", materiality_score=5,
    )
    db.add(event)
    db.commit()
    return event


def test_is_duplicate_by_url_or_normalized_title(db):
    company = _company(db)
    service = NewsService()
    _event(db, company, title="Apple beats expectations", url="https://x.test/a")
    assert service._is_duplicate(db, company, "anything", "https://x.test/a") is True
    # Title comparison uses the same whitespace-normalized, truncated form.
    assert service._is_duplicate(db, company, "Apple   beats  expectations", None) is True
    assert service._is_duplicate(db, company, "Different headline", "https://x.test/b") is False


def test_ingest_skips_duplicates_and_accounts_exactly(db):
    _company(db)
    service = NewsService()
    item = NewsFeedItem(
        ticker="AAPL", title="Apple raises buyback", text="Buyback expanded",
        source="feed", url="https://x.test/1",
    )
    first = service.ingest_news_items(db, [item])
    assert first.received == 1
    assert first.created == 1
    assert first.skipped_duplicates == 0
    second = service.ingest_news_items(db, [item, item])
    assert second.received == 2
    assert second.created == 0
    assert second.skipped_duplicates == 2



def test_ingest_preserves_source_publication_date(db):
    """Un filing de 2025 no puede aparecer con la fecha de ingesta (F73)."""
    filing_date = datetime(2025, 10, 15, 14, 30, tzinfo=UTC)
    response = NewsService().ingest_news_items(
        db,
        [NewsFeedItem(
            title="Apple files 10-K annual report",
            text="Apple 10-K",
            ticker="AAPL",
            url="https://sec.gov/x",
            published_at=filing_date,
        )],
    )
    assert response.created == 1
    event = db.query(NewsEvent).filter_by(url="https://sec.gov/x").one()
    assert event.date.replace(tzinfo=UTC) == filing_date


def test_ingest_without_source_date_falls_back_to_now(db):
    """Sin fecha de fuente, la de ingesta es el fallback legitimo."""
    response = NewsService().ingest_news_items(
        db,
        [NewsFeedItem(title="Noticia manual sin fecha fuente", text="manual", url="https://example.com/1")],
    )
    assert response.created == 1
    event = db.query(NewsEvent).filter_by(url="https://example.com/1").one()
    age = datetime.now(UTC) - event.date.replace(tzinfo=UTC)
    assert age.total_seconds() < 3600
