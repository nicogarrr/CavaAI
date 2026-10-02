"""Un ticker corto solo vincula una noticia con evidencia (cashtag, bolsa o nombre)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company
from app.services.news_service import NewsService, _ticker_evidence


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _company(db: Session, ticker: str, name: str) -> Company:
    company = Company(
        ticker=ticker, name=name, exchange="NYSE", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.commit()
    return company


def test_acronym_and_article_do_not_match_short_tickers():
    assert not _ticker_evidence("AAP", "Advance Auto Parts Inc", "AAP names four candidates for Bihar council polls")
    assert not _ticker_evidence("A", "Agilent Technologies Inc", "A Targeted News Service")
    assert not _ticker_evidence("A", "Agilent Technologies Inc", "Shares of a company rose")


def test_short_ticker_with_evidence_matches():
    assert _ticker_evidence("AAP", "Advance Auto Parts Inc", "Advance Auto Parts (AAP) cuts guidance")
    assert _ticker_evidence("ADI", "Analog Devices Inc", "ADI Analog Devices , Inc . $ADI Shares Sold")
    assert _ticker_evidence("JPM", "JPMorgan Chase & Co", "JPM JPMorgan Chase & Co . ( NYSE : JPM ) Stock Price Down")
    assert _ticker_evidence("AAP", "Advance Auto Parts Inc", "Stock $aap jumps")


def test_long_ticker_matches_with_case_sensitivity():
    assert _ticker_evidence("AAPL", "Apple Inc", "AAPL beats expectations")
    assert not _ticker_evidence("AAPL", "Apple Inc", "the snappiest pineapple")


def test_detect_ticker_uses_evidence(db):
    _company(db, "AAP", "Advance Auto Parts Inc")
    service = NewsService()
    assert service.detect_ticker(db, "AAP names four candidates for Bihar council polls") is None
    assert service.detect_ticker(db, "Advance Auto Parts (NYSE: AAP) cuts guidance") is not None
