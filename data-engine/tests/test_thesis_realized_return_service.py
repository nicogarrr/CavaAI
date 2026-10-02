"""D3: el puente tesis <-> retorno realizado.

Un ano largo de precios para que la escalera 1M/3M/6M/1A/2A quepa entera, y
afirmaciones sobre lo que el servicio se atreve a decir y lo que no.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import (
    Company,
    DecisionJournalEntry,
    DecisionLesson,
    FXRate,
    MarketPrice,
    Portfolio,
    ThesisVersion,
)
from app.models.entities import Base
from app.models.thesis_realized_return import ThesisRealizedReturn
from app.services.thesis_realized_return_service import (
    OUTCOME_DEAD_BAND,
    ThesisRealizedReturnService,
    realized_return_payload,
)

PUBLISHED = dt.datetime(2023, 1, 2, 9, 0, tzinfo=dt.UTC)
ENTRY_DAY = dt.date(2023, 1, 2)
AS_OF = dt.date(2025, 12, 31)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.info["tenant_id"] = 1
    yield session
    session.close()


def _set_base_currency(db: Session, currency: str) -> None:
    from app.services.portfolio_fx_service import PortfolioFXService

    service = PortfolioFXService()
    portfolio = service.portfolio(db)
    if portfolio is None:
        db.add(Portfolio(name="Main", base_currency=currency, is_default=True))
    else:
        portfolio.base_currency = currency
    db.flush()


def _company(
    db: Session,
    ticker: str = "ACME",
    *,
    currency: str = "USD",
    base_currency: str | None = "USD",
) -> Company:
    company = Company(
        ticker=ticker,
        name=f"{ticker} Co",
        exchange="NASDAQ",
        currency=currency,
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
    if base_currency:
        _set_base_currency(db, base_currency)
    return company


def _prices(
    db: Session,
    company: Company,
    *,
    start: dt.date = ENTRY_DAY,
    days: int = 1100,
    drift: float = 0.0008,
    first: float = 100.0,
    adjusted: bool = True,
    source: str = "test",
) -> None:
    for index in range(days):
        day = start + dt.timedelta(days=index)
        value = Decimal(str(round(first * (1 + drift * index), 6)))
        db.add(
            MarketPrice(
                company_id=company.id,
                date=day,
                close=value,
                adj_close=value if adjusted else None,
                source=source,
            )
        )
    db.flush()


def _thesis(
    db: Session,
    company: Company,
    *,
    version: int = 1,
    published: dt.datetime = PUBLISHED,
    expected_value: str | None = "150.000000",
    rating: str = "buy",
    hypothesis: str | None = None,
) -> ThesisVersion:
    thesis = ThesisVersion(
        company_id=company.id,
        version=version,
        status="published",
        thesis_markdown="La tesis",
        executive_summary="Resumen",
        rating=rating,
        expected_value=Decimal(expected_value) if expected_value else None,
        hypothesis=hypothesis,
        created_at=published,
        updated_at=published,
    )
    db.add(thesis)
    db.commit()
    return thesis


def _benchmark(db: Session, *, drift: float = 0.0004, days: int = 1100) -> Company:
    company = _company(db, ticker="^GSPC", base_currency=None)
    _prices(db, company, drift=drift, days=days, first=4000.0, source="idx-test")
    db.commit()
    return company


def _horizon(row: ThesisRealizedReturn, label: str) -> dict:
    return next(item for item in row.horizons if item["horizon"] == label)


def _dec(value) -> Decimal | None:
    """La columna JSON devuelve el numero como texto; el mercado, como Decimal."""
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def test_long_thesis_up_is_right_with_explicit_reason(db: Session) -> None:
    company = _company(db)
    _prices(db, company)
    _benchmark(db)
    thesis = _thesis(db, company)

    row, changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    assert changed is True
    assert row.entry_date == ENTRY_DAY
    assert row.entry_price == Decimal("100.000000")
    assert row.entry_price_status == "exact"
    assert row.upside_at_entry == Decimal("0.500000")
    assert row.fair_value_source == "thesis_expected_value"
    assert row.outcome == "thesis_right"
    assert row.counts_toward_hit_rate is True
    assert "Tesis acertada" in row.verdict_reason
    six = _horizon(row, "6M")
    assert six["status"] == "ok"
    # 100 * (1 + 0.0008 * 180) / 100 - 1 = 0.144
    assert _dec(six["realized_return"]) == Decimal("0.144000")
    assert _dec(six["alpha"]) == Decimal("0.072000")
    assert _dec(six["max_drawdown"]) == Decimal("0")
    assert _dec(six["max_run_up"]) == Decimal("0.144000")


def test_long_thesis_down_is_wrong(db: Session) -> None:
    company = _company(db)
    _prices(db, company, drift=-0.001)
    _benchmark(db, drift=0.0004)
    thesis = _thesis(db, company)

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    assert row.outcome == "thesis_wrong"
    assert row.counts_toward_hit_rate is True
    assert "Tesis fallada" in row.verdict_reason


def test_short_thesis_that_falls_is_right(db: Session) -> None:
    """La direccion la declara la tesis: caer es acertar si la tesis pedia caer."""
    company = _company(db)
    _prices(db, company, drift=-0.001)
    _benchmark(db)
    thesis = _thesis(db, company, expected_value="60.000000", rating="sell")

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    assert row.upside_at_entry < 0
    assert _dec(_horizon(row, "6M")["realized_return"]) < 0
    assert row.outcome == "thesis_right"


def test_rating_beats_the_sign_of_the_upside(db: Session) -> None:
    """Un `buy` con valor razonable por debajo del precio sigue siendo largo."""
    company = _company(db)
    _prices(db, company, drift=0.0008, first=100.0)
    _benchmark(db)
    # El valor razonable congelado queda por debajo del precio de entrada.
    thesis = _thesis(db, company, expected_value="90.000000", rating="buy")

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    assert row.upside_at_entry < 0
    assert "rating buy" in row.verdict_reason
    assert row.outcome == "thesis_right"


def test_return_inside_dead_band_is_inconclusive_not_a_win(db: Session) -> None:
    company = _company(db)
    _prices(db, company, drift=0.00001)
    _benchmark(db)
    thesis = _thesis(db, company)

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    assert _dec(_horizon(row, "6M")["realized_return"]) < OUTCOME_DEAD_BAND
    assert row.outcome == "inconclusive"
    assert row.counts_toward_hit_rate is False
    assert "banda muerta" in row.verdict_reason


def test_thesis_without_direction_cannot_be_judged(db: Session) -> None:
    company = _company(db)
    _prices(db, company)
    _benchmark(db)
    thesis = _thesis(db, company, expected_value=None, rating="watch")

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    assert row.outcome == "inconclusive"
    assert row.judgement_status == "no_direction"
    assert "sin direcci" in row.verdict_reason


def test_no_entry_price_is_nd_never_the_first_later_price(db: Session) -> None:
    company = _company(db)
    # Cotizaciones desde dos meses DESPUES de la publicacion.
    _prices(db, company, start=ENTRY_DAY + dt.timedelta(days=60))
    _benchmark(db)
    thesis = _thesis(db, company)

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    assert row.entry_date is None
    assert row.entry_price is None
    assert row.entry_price_status == "missing"
    assert "no se usa el primer precio posterior" in row.entry_price_rule
    assert row.outcome == "inconclusive"
    assert row.counts_toward_hit_rate is False
    for item in row.horizons:
        assert item["status"] == "no_entry_price"
        assert item["realized_return"] is None
        assert item["reason"].startswith("N/D")


def test_spot_only_prices_are_not_measurable(db: Session) -> None:
    company = _company(db)
    _prices(db, company, adjusted=False)
    _benchmark(db)
    thesis = _thesis(db, company)

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    assert row.entry_price_status == "spot_only"
    assert row.outcome == "inconclusive"
    assert all(item["realized_return"] is None for item in row.horizons)
    assert "splits" in row.entry_price_rule


def test_too_early_is_not_a_thesis_wrong(db: Session) -> None:
    company = _company(db)
    _prices(db, company)
    _benchmark(db)
    thesis = _thesis(db, company, published=dt.datetime(2025, 12, 20, 9, 0, tzinfo=dt.UTC))

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    assert row.outcome == "too_early"
    assert row.counts_toward_hit_rate is False
    assert row.judgement_status == "too_early"
    judgement = _horizon(row, row.judgement_horizon)
    assert judgement["status"] == "too_early"
    assert judgement["realized_return"] is None
    assert "no se punt" in judgement["reason"] and "0 %" in judgement["reason"]


def test_too_early_becomes_measurable_once_the_horizon_elapses(db: Session) -> None:
    company = _company(db)
    _prices(db, company)
    _benchmark(db)
    thesis = _thesis(db, company, published=dt.datetime(2025, 6, 1, 9, 0, tzinfo=dt.UTC))
    service = ThesisRealizedReturnService()

    early, _changed = service.persist(db, company, thesis, as_of=dt.date(2025, 7, 1))
    # `persist` devuelve la misma fila de la sesion: hay que copiar el estado
    # ANTES de la segunda pasada o se compararia el antes con el despues.
    early_outcome = early.outcome
    later, changed = service.persist(db, company, thesis, as_of=dt.date(2025, 12, 31))

    assert early_outcome == "too_early"
    assert changed is True
    assert later.outcome == "thesis_right"
    # Cerrar el horizonte de juicio es un cambio real: queda una revision nueva
    # con la foto anterior, no una reescritura silenciosa.
    assert later.revision == 2
    assert later.revisions[-1]["outcome"] == "too_early"
    assert "cerr" in later.revisions[-1]["motivo"]


def test_alpha_is_nd_without_benchmark(db: Session) -> None:
    company = _company(db)
    _prices(db, company)
    thesis = _thesis(db, company)

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    assert row.benchmark_status == "missing_company"
    assert row.benchmark_ticker is None
    for item in row.horizons:
        assert item["status"] == "ok"
        assert item["benchmark_return"] is None
        assert item["alpha"] is None
        assert "no se inventa como 0" in item["alpha_reason"]


def test_base_return_is_nd_without_declared_currency(db: Session) -> None:
    company = _company(db, currency="", base_currency="EUR")
    _prices(db, company)
    _benchmark(db)
    thesis = _thesis(db, company)

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    assert row.currency is None
    for item in row.horizons:
        assert _dec(item["realized_return"]) is not None
        assert item["realized_return_base"] is None
        assert "no declara divisa" in item["base_reason"]
        assert item["alpha"] is None


def test_alpha_needs_benchmark_and_asset_in_the_same_base(db: Session) -> None:
    """Benchmark en USD y activo en EUR sin FX fechado: alfa N/D, no 0."""
    company = _company(db, currency="EUR", base_currency="EUR")
    _prices(db, company)
    _benchmark(db)
    thesis = _thesis(db, company)

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    six = _horizon(row, "6M")
    assert _dec(six["realized_return_base"]) == _dec(six["realized_return"])
    assert six["benchmark_return"] is None
    assert six["alpha"] is None
    assert "EUR/USD" in six["alpha_reason"]


def test_dated_fx_makes_the_base_return_and_the_alpha_computable(db: Session) -> None:
    company = _company(db, currency="USD", base_currency="EUR")
    _prices(db, company)
    _benchmark(db)
    thesis = _thesis(db, company)

    for index, day in enumerate((ENTRY_DAY, ENTRY_DAY + dt.timedelta(days=180))):
        db.add(
            FXRate(
                base_currency="EUR",
                quote_currency="USD",
                rate_date=day,
                rate=Decimal("0.90") + Decimal("0.001") * index,
                source="test",
            )
        )
    db.commit()

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    six = _horizon(row, "6M")
    assert _dec(six["realized_return_base"]) is not None
    # El euro se aprecio contra el dolar: el retorno en euros supera al local.
    assert _dec(six["realized_return_base"]) > _dec(six["realized_return"])
    assert _dec(six["alpha"]) is not None


def test_horizons_are_monotonic_and_carry_every_step(db: Session) -> None:
    company = _company(db)
    _prices(db, company)
    _benchmark(db)
    thesis = _thesis(db, company)

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    days = [item["horizon_days"] for item in row.horizons]
    assert days == sorted(days) == [30, 90, 180, 365, 730]
    exits = [item["exit_date"] for item in row.horizons]
    assert exits == sorted(exits)
    for item in row.horizons:
        assert item["exit_date"] >= str(row.entry_date)


def test_max_drawdown_and_run_up_bound_the_realized_return(db: Session) -> None:
    company = _company(db)
    _prices(db, company, drift=0.002)
    _benchmark(db)
    thesis = _thesis(db, company)

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    for item in row.horizons:
        realized = _dec(item["realized_return"])
        if realized is None:
            continue
        assert _dec(item["max_drawdown"]) <= 0
        assert _dec(item["max_run_up"]) >= 0
        assert _dec(item["max_drawdown"]) <= realized <= _dec(item["max_run_up"])


def test_declared_horizon_in_the_thesis_text_wins_over_the_default(db: Session) -> None:
    company = _company(db)
    _prices(db, company)
    _benchmark(db)
    thesis = _thesis(db, company, hypothesis="El margen se recupera en 12 meses")

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    assert row.holding_horizon_days == 365
    assert row.judgement_horizon == "1A"
    assert "declarado en la tesis" in row.holding_horizon_source


def test_recompute_is_idempotent(db: Session) -> None:
    company = _company(db)
    _prices(db, company)
    _benchmark(db)
    thesis = _thesis(db, company)
    service = ThesisRealizedReturnService()

    first, changed_first = service.persist(db, company, thesis, as_of=AS_OF)
    fingerprint = first.price_fingerprint
    second, changed_second = service.persist(db, company, thesis, as_of=AS_OF)

    assert (changed_first, changed_second) == (True, False)
    assert second.id == first.id
    assert second.revision == 1
    assert second.price_fingerprint == fingerprint
    assert len(second.revisions) == 1
    assert len(list(db.scalars(select(ThesisRealizedReturn)).all())) == 1


def test_price_correction_opens_a_revision_and_keeps_the_old_one(db: Session) -> None:
    company = _company(db)
    _prices(db, company)
    _benchmark(db)
    thesis = _thesis(db, company)
    service = ThesisRealizedReturnService()
    first, _changed = service.persist(db, company, thesis, as_of=AS_OF)
    old_fingerprint = first.price_fingerprint
    old_outcome = first.outcome

    # El proveedor corrige el cierre que cierra el horizonte de 6M.
    target = ENTRY_DAY + dt.timedelta(days=180)
    bar = db.scalar(
        select(MarketPrice).where(
            MarketPrice.company_id == company.id, MarketPrice.date == target
        )
    )
    bar.adj_close = Decimal("99.000000")
    db.commit()

    second, changed = service.persist(db, company, thesis, as_of=AS_OF)

    assert changed is True
    assert second.revision == 2
    assert second.price_fingerprint != old_fingerprint
    assert len(second.revisions) == 2
    assert second.revisions[-1]["price_fingerprint"] == old_fingerprint
    assert second.revisions[-1]["outcome"] == old_outcome
    assert len(list(db.scalars(select(ThesisRealizedReturn)).all())) == 1


def test_recompute_portfolio_is_bounded_and_reports_truncation(db: Session) -> None:
    _benchmark(db)
    for index in range(3):
        company = _company(db, ticker=f"T{index}")
        _prices(db, company)
        _thesis(db, company)

    service = ThesisRealizedReturnService()
    stats = service.recompute_portfolio(db, limit=10)

    assert stats["recomputados"] == 3
    assert stats["actualizados"] == 3
    assert stats["truncado"] is False
    assert service.recompute_portfolio(db, limit=10)["actualizados"] == 0
    assert service.recompute_portfolio(db, limit=2)["truncado"] is True


def test_records_are_scoped_to_their_tenant(db: Session) -> None:
    company = _company(db, ticker="SCOP")
    _prices(db, company)
    _benchmark(db)
    thesis = _thesis(db, company)
    service = ThesisRealizedReturnService()
    service.persist(db, company, thesis, as_of=AS_OF)

    assert len(service.for_company(db, company.id)) == 1
    assert service.portfolio_summary(db)["casos_totales"] == 1

    # Otro tenant del mismo deployment no ve la fila.
    other = Session(db.get_bind())
    other.info["tenant_id"] = 2
    assert service.for_thesis(other, thesis.id) is None
    assert service.portfolio_summary(other)["casos_totales"] == 0
    other.close()


def test_decision_lesson_is_linked_by_reading_only(db: Session) -> None:
    company = _company(db, ticker="LESS")
    _prices(db, company)
    _benchmark(db)
    thesis = _thesis(db, company)
    decision = DecisionJournalEntry(
        company_id=company.id,
        thesis_version_id=thesis.id,
        decision="buy",
        rationale="Margen en expansion",
        what_must_be_true=["ROIC > WACC"],
        decision_date=ENTRY_DAY,
    )
    db.add(decision)
    db.flush()
    lesson = DecisionLesson(
        company_id=company.id,
        decision_journal_entry_id=decision.id,
        taxonomy="extrapolating_peak_margin",
        lesson="No comprar el pico del margen",
        status="approved",
    )
    db.add(lesson)
    db.commit()

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)

    assert row.decision_lesson_id == lesson.id
    assert row.decision_lesson_link == "decision_journal_entry"
    # Solo lectura: la leccion no se toca.
    db.refresh(lesson)
    assert lesson.status == "approved"
    assert lesson.taxonomy == "extrapolating_peak_margin"


def test_summary_reports_the_denominator_and_the_excluded(db: Session) -> None:
    service = ThesisRealizedReturnService()
    _benchmark(db)

    right = _company(db, ticker="RIGHT")
    _prices(db, right)
    service.persist(db, right, _thesis(db, right), as_of=AS_OF)

    wrong = _company(db, ticker="WRONG")
    _prices(db, wrong, drift=-0.001)
    service.persist(db, wrong, _thesis(db, wrong), as_of=AS_OF)

    early = _company(db, ticker="EARLY")
    _prices(db, early)
    service.persist(
        db,
        early,
        _thesis(db, early, published=dt.datetime(2025, 12, 20, 9, 0, tzinfo=dt.UTC)),
        as_of=AS_OF,
    )

    summary = service.portfolio_summary(db)

    assert summary["casos_totales"] == 3
    assert summary["denominador_hit_rate"] == 2
    assert summary["hit_rate"] == Decimal("0.5")
    assert summary["conteo"] == {
        "thesis_right": 1,
        "thesis_wrong": 1,
        "inconclusive": 0,
        "too_early": 1,
    }
    assert summary["excluidos_del_hit_rate"]["too_early"] == 1
    assert "2 tesis juzgadas" in summary["hit_rate_texto"]
    # El 6M solo se midio en dos de los tres casos: la tes de ayer queda fuera.
    assert summary["retorno_realizado_por_horizonte"]["6M"]["n"] == 2


def test_summary_without_any_judged_case_is_nd_not_zero(db: Session) -> None:
    company = _company(db, ticker="NODATA")
    _prices(db, company, start=ENTRY_DAY + dt.timedelta(days=60))
    ThesisRealizedReturnService().persist(db, company, _thesis(db, company), as_of=AS_OF)

    summary = ThesisRealizedReturnService().portfolio_summary(db)

    assert summary["denominador_hit_rate"] == 0
    assert summary["hit_rate"] is None
    assert summary["hit_rate_sin_datos"] is True
    assert summary["hit_rate_texto"] == "N/D"


def test_api_payload_reports_nd_with_a_reason_for_every_field(db: Session) -> None:
    company = _company(db, currency="", base_currency="EUR")
    _prices(db, company)
    thesis = _thesis(db, company)

    row, _changed = ThesisRealizedReturnService().persist(db, company, thesis, as_of=AS_OF)
    payload = realized_return_payload(row)

    assert payload["divisa"] == "N/D"
    assert payload["leccion"]["decision_lesson_id"] == "N/D"
    assert payload["leccion"]["motivo"]
    horizon = next(item for item in payload["horizontes"] if item["horizonte"] == "1M")
    assert horizon["retorno_realizado"]["valor"] != "N/D"
    assert horizon["retorno_realizado_base"]["valor"] == "N/D"
    assert horizon["retorno_realizado_base"]["motivo"]
    assert horizon["alfa"]["valor"] == "N/D"
    assert horizon["alfa"]["motivo"]
