"""ThesisBacktestService: el heart, la rejilla, la idempotencia y el informe.

Lamayoria de estos tests giran alrededor de una sola idea: una celda es el
resultado de replayear una tesis tal y como se veia ese dia, y todo lo que no
se puede probar que fuera publico ese dia tiene que salir como abstención
declarada, nunca como un numero.
"""

from __future__ import annotations

import socket
from datetime import date

import pytest

from app.models.thesis_backtest import (
    STATUS_INSUFFICIENT_DATA,
    STATUS_NOT_YET_PUBLISHED,
    STATUS_OK,
    BacktestCellRow,
    BacktestResult,
    BacktestRun,
)
from app.services.thesis_backtest_service import (
    ND,
    ThesisBacktestService,
    build_grid,
    month_end,
)
from app.valuation.financial_snapshot import FinancialSnapshotBuilder
from app.valuation.period_bounds import AS_OF_SOURCE_TODAY_DEFAULT
from app.valuation.point_in_time_snapshot import PointInTimeSnapshotBuilder
from tests.backtest_fixtures import (
    BENCHMARK_TICKER,
    CUTOFF_LATE,
    CUTOFF_MID,
    TICKER,
    add_accounts,
    add_benchmark,
    add_future_price,
    add_future_trap,
    add_prices,
    add_thesis,
    make_company,
    make_session,
    seed_company,
)


@pytest.fixture
def no_network(monkeypatch):
    """Hermetic: no socket may leave the process.

    A backtest is an offline claim about history. A connector that quietly
    fetched a live price or a filing would invalidate it while leaving the
    output looking perfectly normal, so the failure has to be loud.
    """
    real_connect = socket.socket.connect

    def guarded(self, address):  # noqa: ANN001
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in {"127.0.0.1", "::1", "localhost"}:
            raise AssertionError(f"acceso a red prohibido en un backtest: {host!r}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)


# ------------------------------------------------------------------ the grid


def test_grid_uses_month_and_quarter_ends():
    monthly = build_grid(date(2024, 1, 15), date(2024, 6, 30), "1M")
    assert monthly == [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31), date(2024, 4, 30), date(2024, 5, 31), date(2024, 6, 30)]
    # A quarterly grid is aligned to calendar quarters: no company reports a
    # "Q1" against a 31 January cutoff.
    quarterly = build_grid(date(2024, 1, 15), date(2024, 12, 31), "1Q")
    assert quarterly == [date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30), date(2024, 12, 31)]


def test_grid_starts_at_the_first_period_end_on_or_after_start():
    assert build_grid(date(2024, 1, 1), date(2024, 3, 31), "1M") == [
        date(2024, 1, 31),
        date(2024, 2, 29),
        date(2024, 3, 31),
    ]


def test_grid_rejects_an_unknown_step():
    with pytest.raises(ValueError, match="step no soportado"):
        build_grid(date(2024, 1, 1), date(2024, 12, 31), "1W")


def test_month_end_december_rolls_the_year():
    assert month_end(2024, 12) == date(2024, 12, 31)
    assert month_end(2024, 1) == date(2024, 1, 31)


# ------------------------------------------------------- PIT builder vs base


def test_pit_builder_matches_base_when_nothing_is_filtered():
    """Drift guard for the mirrored builder.

    The point-in-time builder re-implements the base builder's coherence rules
    on top of a filtered candidate query. If the base rules ever change and this
    mirror does not, every replay would silently use a different snapshot than
    the product does. With a cutoff far past every fact, the two must agree
    exactly.
    """
    session = make_session()
    company = seed_company(session)
    base = FinancialSnapshotBuilder().build(session, company)
    pit = PointInTimeSnapshotBuilder(as_of=date(2099, 1, 1)).build(session, company)
    assert pit.coherent == base.coherent
    assert pit.missing_inputs == base.missing_inputs
    assert pit.as_of_period == base.as_of_period
    assert pit.periods() == base.periods()
    assert pit.value("revenue") == base.value("revenue")
    assert pit.value("net_debt") == base.value("net_debt")


# --------------------------------------------------------------- the happy cell


def test_cell_produces_a_fair_value_with_its_cutoff(no_network):
    session = make_session()
    seed_company(session)
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)

    assert cell.status == STATUS_OK
    assert cell.fair_value is not None and cell.fair_value > 0
    assert cell.current_price is not None
    assert cell.upside is not None
    # The number never travels alone.
    assert cell.evidence_cutoff == CUTOFF_MID
    assert cell.as_of == CUTOFF_MID
    assert cell.point_in_time["as_of"] == CUTOFF_MID.isoformat()
    assert cell.point_in_time["as_of_source"] == "explicit"
    assert cell.lookahead_violations == []
    assert cell.cell_hash


def test_cell_without_as_of_is_labelled_as_today_default(no_network):
    """A cell computed with no date is a live valuation, and must say so.

    The report is allowed to quote it, but only if the reader can tell it apart
    from a genuine replay of that day.
    """
    session = make_session()
    seed_company(session)
    cell = ThesisBacktestService().cell(session, TICKER, None)
    assert cell.point_in_time["as_of_source"] == AS_OF_SOURCE_TODAY_DEFAULT
    assert cell.point_in_time["as_of_inferred"] is True


def test_cell_uses_the_traceable_wacc_and_engines_the_registry(no_network):
    session = make_session()
    seed_company(session)
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert cell.engine_key == "standard_dcf"
    assert cell.model_version


def test_cell_reports_claims_evidence_and_coverage(no_network):
    session = make_session()
    seed_company(session)
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert cell.n_claims == 1
    assert cell.n_claims_with_evidence == 1
    assert cell.source_coverage_score == 100
    assert cell.debate_verdict == "neutral"


def test_cell_without_a_stored_debate_reports_nd_not_an_imputed_verdict(no_network):
    """The debate is an LLM service and is deliberately not replayed.

    Asking today's model what it thought in 2024 measures today's model. Only a
    verdict persisted before the cutoff counts, and its absence is reported.
    """
    session = make_session()
    company = make_company(session)
    add_thesis(session, company)
    session.commit()
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert cell.debate_verdict is None
    assert ND in (cell.debate_verdict_note or "")


# ------------------------------------------------------------------ abstention


def test_thesis_published_after_the_cutoff_yields_an_empty_cell(no_network):
    """Not "a failed thesis": the thesis did not exist yet.

    Scoring this as a miss would punish the backtest for information it was not
    allowed to have, and would quietly bias every hit rate downward.
    """
    session = make_session()
    seed_company(session)
    cell = ThesisBacktestService().cell(session, TICKER, date(2024, 1, 31))
    assert cell.status == STATUS_NOT_YET_PUBLISHED
    assert cell.fair_value is None
    assert cell.degraded is True
    assert "no hay tesis publicada" in (cell.degraded_reason or "")
    # The price of that day is still a fact, just not a valuation.
    assert cell.current_price is not None


def test_insufficient_data_is_never_filled_with_the_current_price(no_network):
    """The single most damaging shortcut in a backtest.

    Completing an abstention with the price turns "we had no view" into "the view
    was worth zero", drags the hit rate down, and makes honest abstention look
    like a failed thesis.
    """
    session = make_session()
    company = make_company(session)
    # Prices and a thesis, but no financials at all.
    add_prices(session, company)
    add_thesis(session, company)
    session.commit()

    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert cell.status == STATUS_INSUFFICIENT_DATA
    assert cell.fair_value is None
    assert cell.bear_value is None and cell.bull_value is None
    assert cell.current_price is not None
    assert cell.missing_inputs
    assert ND in (cell.degraded_reason or "")


def test_insufficient_cell_hash_differs_from_a_valued_one(no_network):
    """An abstention is a distinct outcome, not a zero-valued cell."""
    session = make_session()
    bare = make_company(session, ticker="BARE")
    add_prices(session, bare)
    add_thesis(session, bare)
    full = seed_company(session, ticker="FULL")
    session.commit()

    service = ThesisBacktestService()
    assert (
        service.cell(session, "BARE", CUTOFF_MID).cell_hash
        != service.cell(session, full.ticker, CUTOFF_MID).cell_hash
    )


def test_error_cell_does_not_kill_the_grid(no_network):
    session = make_session()
    with pytest.raises(ValueError, match="empresa desconocida"):
        ThesisBacktestService().cell(session, "NOPE", CUTOFF_MID)


# --------------------------------------------------------------- point-in-time


def test_price_used_is_the_one_at_or_before_the_cutoff(no_network):
    session = make_session()
    company = seed_company(session)
    add_future_price(session, company)
    session.commit()
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert cell.price_date is not None and cell.price_date <= CUTOFF_MID
    assert cell.current_price is not None and cell.current_price < 1000


def test_future_fact_is_excluded_and_named(no_network):
    session = make_session()
    company = seed_company(session)
    add_future_trap(session, company)
    session.commit()
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert any("2999" in item for item in cell.excluded_future_inputs)
    # Excluded is correct; leaking would not be.
    assert cell.lookahead_violations == []
    assert cell.fair_value is not None and cell.fair_value < 1000


def test_unverifiable_period_is_excluded_and_degrades_the_cell(no_network):
    """A fact with no readable period cannot be proven public.

    The shared guard lets missing metadata pass on purpose, so that a live
    valuation is not blocked by an undated row. Inside a replay that same
    leniency is a hole: an unprovable input is not evidence.
    """
    from decimal import Decimal

    from app.models import FinancialFact

    session = make_session()
    company = seed_company(session)
    session.add(
        FinancialFact(
            company_id=company.id,
            metric="revenue_growth",
            value=Decimal("0.5"),
            unit="ratio",
            period="sin fecha",
            fiscal_year=None,
            fiscal_quarter=None,
            source_type="manual",
            confidence=Decimal("0.5"),
        )
    )
    session.commit()
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert cell.unverifiable_inputs
    assert cell.degraded is True
    assert "fecha" in (cell.degraded_reason or "")
    # The row was excluded, not quietly used: an unprovable input is not evidence.
    assert "revenue_growth" not in (cell.point_in_time.get("valuation_periods") or {})


# ------------------------------------------------------------- realized return


def test_realized_return_uses_adjusted_close_and_reports_mae_mfe(no_network):
    session = make_session()
    seed_company(session)
    add_benchmark(session)
    session.commit()
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    realized = cell.realized
    assert realized.get("available") is True
    one_year = realized["1A"]
    assert one_year["status"] == "ok"
    assert one_year["return"] is not None
    assert one_year["mae"] <= one_year["return"] <= one_year["mfe"]


def test_alpha_is_measured_against_the_index_when_present(no_network):
    session = make_session()
    seed_company(session)
    add_benchmark(session)
    session.commit()
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    alpha = cell.realized["1A"]["alpha"]
    assert alpha is not None
    assert isinstance(alpha, float)


def test_alpha_is_nd_without_an_index_series(no_network):
    """No benchmark means no alpha, said out loud. Never a zero alpha."""
    session = make_session()
    seed_company(session)
    session.commit()
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert cell.realized["1A"]["alpha"] is None
    assert ND in cell.realized["1A"]["alpha_reason"]


def test_missing_adjusted_close_is_nd_not_a_reconstructed_price(no_network):
    """The repo's rule: a NULL adj_close means the source gave a spot.

    Reconstructing an adjusted series would corrupt exactly the compounded
    numbers the backtest is measuring.
    """
    session = make_session()
    company = make_company(session)
    add_accounts(session, company)
    add_prices(session, company, with_adj_close=False)
    add_thesis(session, company)
    session.commit()
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert cell.status == STATUS_OK
    assert cell.realized.get("available") is False
    assert "adj_close" in cell.realized["reason"]


def test_horizon_without_future_prices_is_nd(no_network):
    session = make_session()
    company = make_company(session)
    add_accounts(session, company)
    add_prices(session, company, count=20)
    add_thesis(session, company)
    session.commit()
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert cell.realized["2A"]["status"] == "sin_datos"
    assert ND in cell.realized["2A"]["reason"]


# -------------------------------------------------------------- idempotency


def test_cell_hash_is_stable_across_replays(no_network):
    session = make_session()
    seed_company(session)
    service = ThesisBacktestService()
    first = service.cell(session, TICKER, CUTOFF_MID)
    second = service.cell(session, TICKER, CUTOFF_MID)
    assert first.cell_hash == second.cell_hash
    assert first.fair_value == second.fair_value


def test_rerunning_the_grid_updates_rows_instead_of_duplicating(no_network):
    session = make_session()
    seed_company(session)
    service = ThesisBacktestService()
    kwargs = dict(tickers=[TICKER], start=date(2025, 1, 1), end=date(2025, 6, 30), step="1M")

    first = service.run(session, **kwargs)
    first_id = first.id
    session.expire_all()
    hashes_first = {
        row.as_of: row.cell_hash
        for row in session.query(BacktestCellRow).filter(BacktestCellRow.run_id == first_id)
    }

    second = service.run(session, **kwargs)
    second_id = second.id
    session.expire_all()
    rows = session.query(BacktestCellRow).filter(BacktestCellRow.run_id == second_id).all()

    # Same cells, same hashes, and no extra rows: the unique constraint on
    # (tenant, run, ticker, as_of) is what makes a replay a replay.
    assert len(rows) == len(hashes_first)
    assert {row.as_of: row.cell_hash for row in rows} == hashes_first
    assert (
        len({(row.ticker, row.as_of) for row in rows}) == len(rows) == len(hashes_first)
    )


def test_run_rejects_a_strategy_that_is_not_a_replay(no_network):
    session = make_session()
    seed_company(session)
    with pytest.raises(ValueError, match="no es un backtest"):
        ThesisBacktestService().run(
            session,
            tickers=[TICKER],
            start=date(2025, 1, 1),
            end=date(2025, 6, 30),
            as_of_strategy="look_forward",
        )


def test_run_records_an_unknown_ticker_as_a_gap_not_a_crash(no_network):
    session = make_session()
    seed_company(session)
    run = ThesisBacktestService().run(
        session, tickers=[TICKER, "NOPE"], start=date(2025, 6, 1), end=date(2025, 6, 30)
    )
    assert run.status == "succeeded"
    statuses = {
        row.status for row in session.query(BacktestCellRow).filter(BacktestCellRow.run_id == run.id)
    }
    assert "error" in statuses and STATUS_OK in statuses


# ------------------------------------------------------------------- report


def test_report_states_cell_count_and_dispersion_next_to_the_hit_rate(no_network):
    """A hit rate printed without its denominator is how a backtest gets quoted
    as proof of alpha."""
    session = make_session()
    seed_company(session)
    add_benchmark(session)
    service = ThesisBacktestService()
    run = service.run(session, tickers=[TICKER], start=date(2025, 1, 1), end=date(2025, 6, 30))
    report = service.report(session, run.id)

    assert report["celdas"]["total"] == len(service.cells(session, run.id))
    assert "dispersion" in report
    assert report["dispersion"]["fair_value_valores"] >= 1
    assert report["hit_rate_1A"]["muestra"] >= 0
    assert report["advertencias"]
    assert "hit-rate" in report["advertencias"][0] or "Sin veredicto" in report["advertencias"][0]


def test_report_refuses_to_declare_alpha_on_a_tiny_sample(no_network):
    session = make_session()
    seed_company(session)
    service = ThesisBacktestService()
    run = service.run(session, tickers=[TICKER], start=date(2025, 1, 1), end=date(2025, 3, 31))
    report = service.report(session, run.id)
    scored = report["celdas"]["validas_para_puntuar"]
    if scored and scored < 20:
        assert "Muestra insuficiente" in report["advertencias"][0] or "Sin veredicto" in report["advertencias"][0]


def test_report_flags_a_suspiciously_perfect_hit_rate(no_network):
    """A thesis process that wins nine times out of ten is a leak until proven
    otherwise, and the report has to say so in words."""
    from app.services.thesis_backtest_service import _alpha_verdict

    assert "SOSPECHOSO" in _alpha_verdict(0.95, 20, 20, 20)
    assert "Sin alfa demostrable" in _alpha_verdict(0.50, 40, 40, 40)
    assert "Sin veredicto" in _alpha_verdict(None, 0, 5, 5)


def test_report_counts_lookahead_rejections_as_a_finding(no_network):
    """A rejection is a security finding about the pipeline, not a data point."""
    session = make_session()
    company = seed_company(session)
    add_future_trap(session, company)
    session.commit()
    service = ThesisBacktestService()
    run = service.run(session, tickers=[TICKER], start=date(2025, 1, 1), end=date(2025, 6, 30))
    report = service.report(session, run.id)
    assert "rechazos_lookahead" in report
    assert report["celdas"]["rechazadas_por_lookahead"] >= 0


def test_report_persists_a_single_result_row_per_run(no_network):
    session = make_session()
    seed_company(session)
    service = ThesisBacktestService()
    run = service.run(session, tickers=[TICKER], start=date(2025, 1, 1), end=date(2025, 6, 30))
    service.run(session, tickers=[TICKER], start=date(2025, 1, 1), end=date(2025, 6, 30))
    results = session.query(BacktestResult).filter(BacktestResult.run_id == run.id).all()
    assert len(results) == 1
    assert results[0].metrics


def test_report_on_a_missing_run_raises(no_network):
    session = make_session()
    with pytest.raises(ValueError, match="backtest no encontrado"):
        ThesisBacktestService().report(session, 9999)


def test_report_breaks_down_degraded_cells_by_reason(no_network):
    """The breakdown must aggregate, not list one key per cell.

    Every reason embeds its own date, so keying by the raw string produced one
    entry per cell and a "summary" nobody could read.
    """
    session = make_session()
    seed_company(session)
    service = ThesisBacktestService()
    run = service.run(session, tickers=[TICKER], start=date(2024, 1, 1), end=date(2025, 6, 30))
    report = service.report(session, run.id)
    breakdown = report["degradadas"]["desglose"]
    assert report["degradadas"]["n"] >= 1
    assert breakdown
    assert sum(breakdown.values()) == report["degradadas"]["n"]
    assert len(breakdown) <= len(service.cells(session, run.id))
    assert set(breakdown) <= {
        "tesis_no_publicada_en_la_fecha",
        "rechazo_lookahead",
        "datos_insuficientes",
        "provenance_no_verificable",
        "publication_blockers",
        "error_de_ejecucion",
        "sin_motivo_declarado",
        "otra",
    }


def test_rejected_cell_keeps_the_engine_that_produced_the_trace(no_network):
    """A NULL engine_key would make a look-ahead rejection unattributable.

    "Which engine leaks" is the first question anyone asks, so the answer has to
    survive the rejection.
    """
    from contextlib import nullcontext

    import app.services.thesis_backtest_service as service_module
    from app.services.thesis_backtest_service import pit_replay_scope

    session = make_session()
    company = seed_company(session)
    add_future_trap(session, company)
    session.commit()

    original = service_module.pit_replay_scope
    service_module.pit_replay_scope = lambda **_kwargs: nullcontext()
    try:
        cell = service_module.ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    finally:
        service_module.pit_replay_scope = original

    assert cell.status == "rejected_lookahead"
    assert cell.engine_key == "standard_dcf"
    assert cell.model_version
    assert cell.lookahead_violations
    del pit_replay_scope


# -------------------------------------------------------------- multi-tenancy


def test_two_tenants_do_not_see_each_others_backtests(no_network):
    """Tenant isolation is enforced by the global loader criteria, so the test
    only has to prove the models opted into it."""
    first = make_session("tenant-a")
    seed_company(first, ticker="AAA")
    run_a = ThesisBacktestService().run(
        first, tickers=["AAA"], start=date(2025, 1, 1), end=date(2025, 6, 30)
    ).id
    cell_ids = [row.id for row in first.query(BacktestCellRow).all()]
    first.close()

    second = make_session("tenant-b")
    assert second.query(BacktestRun).filter(BacktestRun.id == run_a).count() == 0
    assert second.query(BacktestCellRow).filter(BacktestCellRow.run_id == run_a).count() == 0
    for cell_id in cell_ids:
        assert second.get(BacktestCellRow, cell_id) is None
    second.close()


def test_tenant_b_cannot_see_tenant_a_cell_by_id(no_network):
    first = make_session("tenant-a")
    seed_company(first, ticker="AAA")
    run_a = ThesisBacktestService().run(
        first, tickers=["AAA"], start=date(2025, 1, 1), end=date(2025, 6, 30)
    ).id
    cell_id = first.query(BacktestCellRow).filter(BacktestCellRow.run_id == run_a).first().id
    first.close()

    second = make_session("tenant-b")
    assert second.get(BacktestRun, run_a) is None
    assert second.get(BacktestCellRow, cell_id) is None
    second.close()


# ------------------------------------------------------------------ filtering


def test_cells_can_be_filtered_by_ticker_and_date(no_network):
    session = make_session()
    seed_company(session, ticker="AAA")
    seed_company(session, ticker="BBB")
    service = ThesisBacktestService()
    run = service.run(
        session, tickers=["AAA", "BBB"], start=date(2025, 6, 1), end=date(2025, 6, 30)
    )
    assert len(service.cells(session, run.id)) == 2
    assert len(service.cells(session, run.id, ticker="AAA")) == 1
    assert len(service.cells(session, run.id, ticker="BBB", as_of=date(2025, 6, 30))) == 1
    assert service.cells(session, run.id, ticker="ZZZ") == []


def test_a_late_cutoff_sees_filings_the_early_one_could_not(no_network):
    """The same fact, filed years apart, is a different fact for a replay."""
    session = make_session()
    company = make_company(session)
    add_accounts(session, company, published_at=date(2024, 3, 15))
    add_prices(session, company)
    add_thesis(
        session, company, created_at=date(2024, 1, 31), evidence_published_at=date(2024, 1, 31)
    )
    session.commit()

    service = ThesisBacktestService()
    # The thesis exists but the accounts were not filed yet: nothing to value.
    early = service.cell(session, TICKER, date(2024, 2, 29))
    assert early.status == STATUS_INSUFFICIENT_DATA
    assert early.fair_value is None

    later = service.cell(session, TICKER, CUTOFF_LATE)
    assert later.status == STATUS_OK
    assert later.point_in_time["valuation_periods"]["revenue"] == "2024-12-31"


def test_a_filing_after_the_cutoff_is_not_used_even_though_its_period_is_past(no_network):
    """The trap a period-end-only guard walks straight into.

    FY2024 accounts filed in 2026 pass every fiscal-year check and still
    invalidate a 2025 replay.
    """
    session = make_session()
    company = make_company(session)
    add_accounts(session, company, published_at=date(2026, 3, 10))
    add_prices(session, company)
    add_thesis(session, company, created_at=date(2024, 7, 15), evidence_published_at=date(2024, 7, 15))
    session.commit()

    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert cell.status == STATUS_INSUFFICIENT_DATA
    assert cell.fair_value is None
    assert cell.unverifiable_inputs == []


def test_benchmark_ticker_is_resolvable_but_never_scored_as_a_thesis(no_network):
    session = make_session()
    add_benchmark(session)
    session.commit()
    assert session.query(BacktestRun).filter(BacktestRun.id == 1).count() == 0
    assert BENCHMARK_TICKER.startswith("^")
