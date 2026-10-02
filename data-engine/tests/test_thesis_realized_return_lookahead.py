"""D3: el servicio no puede mirar al futuro.

El sesgo de look-ahead es el fallo que hace bonito un backtest y falso un
producto: si la entrada usa un precio posterior a la publicación, o la salida
una fecha que aún no había ocurrido, todo lo que se cuenta después está
contaminado. Aquí se ataca justo eso.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Company, MarketPrice, ThesisVersion
from app.models.entities import Base
from app.services.thesis_realized_return_service import (
    ENTRY_PRICE_GRACE_DAYS,
    ThesisRealizedReturnService,
)

PUBLISHED = dt.datetime(2024, 3, 15, 9, 0, tzinfo=dt.UTC)
PUBLISHED_DAY = dt.date(2024, 3, 15)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.info["tenant_id"] = 1
    yield session
    session.close()


def _company(db: Session, ticker: str = "FUT") -> Company:
    company = Company(
        ticker=ticker,
        name=f"{ticker} Co",
        exchange="NASDAQ",
        currency="USD",
        sector="Industrials",
        industry="Test",
        company_type="standard",
        valuation_model="standard_dcf",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.flush()
    return company


def _prices(
    db: Session,
    company: Company,
    days: list[dt.date],
    *,
    first: float = 100.0,
    drift: float = 0.001,
) -> None:
    for index, day in enumerate(days):
        value = Decimal(str(round(first * (1 + drift * index), 6)))
        db.add(
            MarketPrice(
                company_id=company.id,
                date=day,
                close=value,
                adj_close=value,
                source="test",
            )
        )
    db.flush()


def _thesis(db: Session, company: Company, published: dt.datetime = PUBLISHED) -> ThesisVersion:
    thesis = ThesisVersion(
        company_id=company.id,
        version=1,
        status="published",
        thesis_markdown="La tesis",
        executive_summary="Resumen",
        rating="buy",
        expected_value=Decimal("150"),
        created_at=published,
        updated_at=published,
    )
    db.add(thesis)
    db.commit()
    return thesis


def _daily(start: dt.date, count: int) -> list[dt.date]:
    return [start + dt.timedelta(days=index) for index in range(count)]


def test_entry_is_the_price_of_the_publication_day(db: Session) -> None:
    company = _company(db)
    # Serie que empieza DOS SEMANAS antes: la barra anterior no puede ser la entrada.
    _prices(db, company, _daily(PUBLISHED_DAY - dt.timedelta(days=14), 400))
    thesis = _thesis(db, company)

    row, _changed = ThesisRealizedReturnService().persist(
        db, company, thesis, as_of=dt.date(2025, 6, 30)
    )

    assert row.entry_date == PUBLISHED_DAY
    assert row.entry_date >= PUBLISHED_DAY


def test_entry_never_precedes_the_publication_even_if_prices_do(db: Session) -> None:
    """Una barra anterior a la publicación existe en la serie y no se usa."""
    company = _company(db)
    _prices(db, company, _daily(PUBLISHED_DAY - dt.timedelta(days=30), 400))
    thesis = _thesis(db, company)
    service = ThesisRealizedReturnService()

    payload = service.compute(db, company, thesis, as_of=dt.date(2025, 6, 30))

    assert payload["entry_date"] == PUBLISHED_DAY
    assert payload["entry_date"].isoformat() >= payload["thesis_published_at"].date().isoformat()


def test_a_price_long_after_publication_is_not_used_as_entry(db: Session) -> None:
    """Sin precio en la ventana de entrada, la entrada es N/D, no el primer precio."""
    company = _company(db)
    first_bar = PUBLISHED_DAY + dt.timedelta(days=ENTRY_PRICE_GRACE_DAYS + 40)
    _prices(db, company, _daily(first_bar, 300))
    thesis = _thesis(db, company)

    row, _changed = ThesisRealizedReturnService().persist(
        db, company, thesis, as_of=dt.date(2025, 12, 31)
    )

    assert row.entry_date is None
    assert row.entry_price is None
    assert row.entry_price_status == "missing"
    for item in row.horizons:
        assert item["realized_return"] is None
    assert row.outcome == "inconclusive"


def test_the_next_session_inside_the_grace_window_is_allowed_and_declared(db: Session) -> None:
    company = _company(db)
    next_session = PUBLISHED_DAY + dt.timedelta(days=2)
    _prices(db, company, _daily(next_session, 400))
    thesis = _thesis(db, company)

    row, _changed = ThesisRealizedReturnService().persist(
        db, company, thesis, as_of=dt.date(2025, 12, 31)
    )

    assert row.entry_date == next_session
    assert row.entry_price_status == "next_session"
    assert "declarado" in row.entry_price_rule
    assert (next_session - PUBLISHED_DAY).days <= ENTRY_PRICE_GRACE_DAYS


def test_session_after_the_grace_window_is_refused(db: Session) -> None:
    company = _company(db)
    late = PUBLISHED_DAY + dt.timedelta(days=ENTRY_PRICE_GRACE_DAYS + 1)
    _prices(db, company, _daily(late, 300))
    thesis = _thesis(db, company)

    row, _changed = ThesisRealizedReturnService().persist(
        db, company, thesis, as_of=dt.date(2025, 12, 31)
    )

    assert row.entry_date is None
    assert "no se usa el primer precio posterior" in row.entry_price_rule


def test_horizons_never_exit_after_as_of(db: Session) -> None:
    """Un as_of histórico no puede mirar barras que aún no se habían cotizado."""
    company = _company(db)
    _prices(db, company, _daily(PUBLISHED_DAY, 400))
    thesis = _thesis(db, company)
    cutoff = dt.date(2024, 6, 1)

    payload = ThesisRealizedReturnService().compute(db, company, thesis, as_of=cutoff)

    for item in payload["horizons"]:
        target = dt.date.fromisoformat(item["target_date"])
        if target > cutoff:
            assert item["status"] == "too_early"
            assert item["exit_date"] is None
            assert item["realized_return"] is None
        else:
            assert item["exit_date"] is None or item["exit_date"] <= cutoff.isoformat()


def test_a_fresh_thesis_reports_too_early_not_a_flat_return(db: Session) -> None:
    company = _company(db)
    _prices(db, company, _daily(PUBLISHED_DAY, 400))
    thesis = _thesis(db, company)
    tomorrow = dt.date(PUBLISHED_DAY.year, PUBLISHED_DAY.month, PUBLISHED_DAY.day) + (
        dt.timedelta(days=1)
    )

    row, _changed = ThesisRealizedReturnService().persist(
        db, company, thesis, as_of=tomorrow
    )

    assert row.outcome == "too_early"
    assert row.counts_toward_hit_rate is False
    measured = [item for item in row.horizons if item["status"] == "ok"]
    for item in measured:
        # Lo medible en un dia no puede ser un 0 % plano.
        assert item["realized_return"] != "0.000000"


def test_the_verdict_ignores_prices_published_after_the_thesis(db: Session) -> None:
    """Congelar el veredicto: corregir el futuro no reescribe el pasado."""
    company = _company(db)
    _prices(db, company, _daily(PUBLISHED_DAY, 400))
    thesis = _thesis(db, company)
    service = ThesisRealizedReturnService()
    first, _changed = service.persist(db, company, thesis, as_of=dt.date(2025, 12, 31))
    fingerprint = first.price_fingerprint
    revision = first.revision
    outcome = first.outcome

    # Una barra nueva, muy posterior al horizonte de juicio: no toca el veredicto.
    future = dt.date(2026, 6, 1)
    db.add(
        MarketPrice(company_id=company.id, date=future, close=Decimal("1"), adj_close=Decimal("1"))
    )
    db.commit()

    again, changed = service.persist(db, company, thesis, as_of=dt.date(2025, 12, 31))

    assert changed is False
    assert again.price_fingerprint == fingerprint
    assert again.revision == revision
    assert again.outcome == outcome
