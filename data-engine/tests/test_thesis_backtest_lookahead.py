"""La reja del look-ahead: que el backtest NO pueda ver el futuro.

Este es el archivo que justifica la feature. Un backtest con una sola fila de
futuro filtrada no produce un numero incorrecto: produce un numero *correcto y
sin sentido*, que es peor, porque se parece a todos los demas. Asi que los tests
de aqui no comprueban que el codigo "no falle": comprueban que la trampa se
sprunga, que se registre, y que el resultado sea una abstencion declarada.

La pieza que mas importa es la primera: sembrar un hecho de un ejercicio futuro y
demostrar que la celda de una fecha anterior no lo ve, y que la celda de una
fecha posterior si.
"""

from __future__ import annotations

import socket
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models import Document, FinancialFact
from app.models.thesis_backtest import (
    STATUS_INSUFFICIENT_DATA,
    STATUS_NOT_YET_PUBLISHED,
    STATUS_OK,
    STATUS_REJECTED_LOOKAHEAD,
)
from app.services.thesis_backtest_service import ThesisBacktestService, pit_replay_scope
from app.valuation.period_bounds import (
    PRECISION_EXACT_DATE,
    PRECISION_FISCAL_YEAR,
    PRECISION_UNKNOWN,
    assert_knowledge_no_lookahead,
    assert_period_no_lookahead,
    knowledge_bounds,
    parse_period_bounds,
)
from app.valuation.point_in_time import LookaheadError
from app.valuation.point_in_time_snapshot import PointInTimeSnapshotBuilder
from tests.backtest_fixtures import (
    CUTOFF_LATE,
    CUTOFF_MID,
    FILING_DAY,
    FUTURE_PERIOD,
    FY_PERIOD,
    TICKER,
    add_accounts,
    add_future_price,
    add_future_trap,
    add_prices,
    add_thesis,
    make_company,
    make_session,
    seed_company,
    ts,
)


@pytest.fixture
def no_network(monkeypatch):
    real_connect = socket.socket.connect

    def guarded(self, address):  # noqa: ANN001
        host = address[0] if isinstance(address, tuple) else address
        if isinstance(host, str) and host not in {"127.0.0.1", "::1", "localhost"}:
            raise AssertionError(f"acceso a red prohibido en un backtest: {host!r}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)


# ==================================================================== LA PRUEBA


def test_a_future_fact_is_invisible_before_its_cutoff_and_visible_after(no_network):
    """El test central de D1, en las dos direcciones.

    Se siembra un hecho FY2999 con un periodo perfectamente legible. A un corte
    de 2025-06-30 no puede haberlo visto nadie; a un corte de 3000-12-31 es el
    ultimo hecho publicado y debe entrar. Si solo se comprobara la primera mitad, un
    filtro que descartase TODO tambien pasaria.
    """
    session = make_session()
    company = seed_company(session)
    add_future_trap(session, company, metric="revenue")
    session.commit()

    service = ThesisBacktestService()

    antes = service.cell(session, TICKER, CUTOFF_MID)
    assert antes.status == STATUS_OK
    assert antes.fair_value is not None
    # The trap is named, not silently dropped: an empty list would be
    # indistinguishable from a filter that never looked.
    assert any("2999" in item for item in antes.excluded_future_inputs)
    assert antes.lookahead_violations == []
    assert antes.point_in_time["valuation_periods"]["revenue"] == "2024-12-31"
    # 999999 would show up in any revenue-based valuation.
    assert antes.fair_value < 1000

    despues = service.cell(session, TICKER, date(3000, 12, 31))
    assert despues.excluded_future_inputs == []
    assert despues.point_in_time["valuation_periods"]["revenue"] == FUTURE_PERIOD
    assert despues.fair_value != antes.fair_value


def test_the_future_fact_is_never_a_violation_because_it_is_never_used(no_network):
    """`lookahead_violations` lista hechos USADOS en el futuro, no los descartados.

    Un filtro point-in-time que funciona encuentra filas futuras en la base de
    datos en cada replay: para eso existe. Contarlas como violaciones
    rechazaria casi todas las celdas y dejaria el backtest inservible, asi que
    los dos conceptos van separados y ambos se persisten.
    """
    session = make_session()
    company = seed_company(session)
    add_future_trap(session, company)
    session.commit()
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert cell.excluded_future_inputs
    assert cell.lookahead_violations == []
    assert cell.status == STATUS_OK


def test_el_eje_de_publicacion_excluye_la_misma_cuenta_presentada_mas_tarde(no_network):
    """El segundo eje: no es solo el periodo, es CUANDO se publico.

    La trampa FY2999 de arriba la para el eje de periodo, y sola: periodo y
    ejercicio son de por si el futuro. Este caso es el que de verdad separa los
    dos ejes, porque el periodo es IDENTICO en las dos filas: los mismos numeros
    de FY2024, presentados dos veces. Un filtro que solo mirase el periodo las
    aceptaria a las dos y devolveria, segun el orden de la consulta, la
    presentacion mas reciente — es decir, un numero de 2026supporting a una
    valoracion de junio de 2025.

    Lo unico que distingue las dos filas es ``Document.published_at``, la fecha
    que escribe la ingesta (max(filed) de lo ingerido). Por eso este test mira
    el MOTIVO del descarte y no solo que la celda salga buena: un descarte por
    cualquier otra causa pasaria igual.
    """
    session = make_session()
    company = make_company(session)
    # Presentacion temprana: la que el analista del corte tiene.
    add_accounts(session, company, published_at=FILING_DAY)
    # Presentacion tardia de LOS MISMOS numeros de FY2024.
    presentacion_tardia = date(2026, 4, 20)
    add_accounts(
        session,
        company,
        published_at=presentacion_tardia,
        facts={
            "revenue": 999999.0,
            "free_cash_flow": 999999.0,
            "net_debt": 1.0,
            "shares_diluted": 1.0,
        },
        include_wacc=False,
    )
    session.commit()

    builder = PointInTimeSnapshotBuilder(as_of=CUTOFF_MID)
    snapshot = builder.build(session, company)

    # Las dos filas declaran el mismo periodo: ninguna regla de periodo las separa.
    periodos = {
        fact.period
        for fact in session.query(FinancialFact).filter(FinancialFact.metric == "revenue").all()
    }
    assert periodos == {FY_PERIOD}, f"el caso solo vale si el periodo es el mismo: {periodos}"

    # Y aun asi la tardia queda fuera, por publicacion, diciendo la fecha.
    rechazos = [
        item
        for item in builder.audit.dropped_future
        if f"publicable el {presentacion_tardia.isoformat()}" in item.reason
        and f"despues del corte {CUTOFF_MID.isoformat()}" in item.reason
    ]
    assert rechazos, f"el eje de publicacion no disparo: {builder.audit.as_dict()}"
    metrics_rechazadas = {item.metric for item in rechazos}
    assert metrics_rechazadas == {"revenue", "free_cash_flow", "net_debt", "shares_diluted"}

    # La cuenta que se valora es la que ya estaba publicada, no la re-presentada.
    assert float(snapshot.facts["revenue"].value) == 1000.0
    # Y el descarte queda nombrado en la celda, no descartado en silencio.
    assert builder.audit.lookahead_violations
    assert all("2999" not in item for item in builder.audit.lookahead_violations)


def test_ingesta_escribe_la_fecha_de_publicacion_que_el_eje_lee(no_network):
    """El otro lado del mismo eje: una fuente oficial SIN fecha no se presume publica.

    Es la contraprueba de que ``_published_dates`` se esta leyendo de verdad. Si
    el filtro ignorara la columna, estos hechos entrarian igual por su periodo
    (2024-12-31 es anterior al corte) y el backtest devolveria un numero hecho de
    una fuente cuya fecha de presentacion nadie conoce. El guard es fail-closed a
    proposito: sin fecha no hay prueba de que fuera publico.
    """
    session = make_session()
    company = make_company(session)
    add_accounts(session, company, published_at=FILING_DAY)
    session.commit()
    # Se vacia la fecha en todos los documentos: es el estado de una ingesta que
    # no la conoce, y el que dejaria un guard de publication ausente o ignorado.
    for fila in session.query(Document).all():
        fila.published_at = None
    session.commit()

    builder = PointInTimeSnapshotBuilder(as_of=CUTOFF_LATE)
    snapshot = builder.build(session, company)

    # NADA se presume publico: revenue tiene el periodo ANTERIOR al corte y aun
    # asi no entra, porque no hay fecha que pruebe que estaba publicado.
    assert builder.audit.kept == [], builder.audit.as_dict()
    assert snapshot.facts == {}
    assert not snapshot.coherent
    assert "revenue" in snapshot.missing_inputs
    assert builder.audit.dropped_future == []
    # El descarte esta nombrado y dice que falta la prueba, no solo que se cae.
    reasons = [item.reason for item in builder.audit.unverifiable]
    assert reasons, builder.audit.as_dict()
    assert all("no se puede probar que fuera publico" in reason for reason in reasons), reasons
    assert all(item.bounds.published_on is None for item in builder.audit.unverifiable)
    assert builder.audit.unverifiable_inputs

    # Mensaje dedicado cuando la fuente es oficial: no es «no se sabe», es
    # «esta fuente oficial no tiene fecha, asi que no se presume publicada».
    oficial = FinancialFact(
        metric="revenue",
        period=FY_PERIOD,
        fiscal_year=2024,
        fiscal_quarter="FY",
        source_type="sec_filing",
    )
    veredicto = PointInTimeSnapshotBuilder(as_of=CUTOFF_LATE).verdict(oficial, None)
    assert not veredicto.usable
    assert veredicto.reason == "sin fecha de publicacion: no se puede probar que fuera publico"


def test_una_fuente_no_oficial_sin_fecha_no_se_trata_como_oficial():
    """El mensaje dedicado es para fuente oficial, no un veto universal.

    Un hecho sin ``source_type`` de fuente oficial y sin ``published_at`` cae en
    el motivo generico (no verificable), no en «sin fecha de publicacion»: la
    distincion es de mensaje y de severidad del motivo, no de si se descarta.
    """
    sin_tipo = FinancialFact(metric="revenue", period=FY_PERIOD, fiscal_year=2024, fiscal_quarter="FY")
    veredicto = PointInTimeSnapshotBuilder(as_of=CUTOFF_LATE).verdict(sin_tipo, None)
    assert not veredicto.usable
    assert "sin fecha utilizable" in veredicto.reason
    assert veredicto.bounds.published_on is None


def test_a_leak_is_rejected_and_counted_not_discarded(no_network, monkeypatch):
    """Si el filtro falla, la celda se marca y se cuenta. Nunca se tira.

    Se desactiva el ambito point-in-time para simular un filtro roto: el
    ``FinancialSnapshotBuilder`` base lee "el ultimo" y el hecho FY2999 entra en
    la valoracion. El guard publico debe levantarse y la celda debe quedar como
    ``rejected_lookahead`` con la lista de violaciones, porque un backtest que
    descarta en silencio las celdas que no puede calcular parece un backtest
    limpio.
    """
    session = make_session()
    company = seed_company(session)
    add_future_trap(session, company)
    session.commit()

    import app.services.thesis_backtest_service as service_module

    monkeypatch.setattr(
        service_module, "pit_replay_scope", lambda **_kwargs: _null_context()
    )
    cell = service_module.ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)

    assert cell.status == STATUS_REJECTED_LOOKAHEAD
    assert cell.fair_value is None
    assert cell.lookahead_violations
    assert "2999" in cell.degraded_reason or "2999" in " ".join(cell.lookahead_violations)
    assert cell.current_price is not None


def _null_context():
    from contextlib import nullcontext

    return nullcontext()


# ================================================================== LAS TRAMPAS


def test_filing_after_the_cutoff_is_invisible_even_though_its_period_is_past(no_network):
    """La trampa que solo mira el periodo no ve.

    Las cuentas de FY2024 se depositan en 2026-03-10: pasan cualquier
    comprobacion de ejercicio y aun asi invalidan un replay de 2025.
    """
    session = make_session()
    company = make_company(session)
    add_accounts(session, company, published_at=date(2026, 3, 10))
    add_prices(session, company)
    add_thesis(
        session, company, created_at=date(2024, 7, 15), evidence_published_at=date(2024, 7, 15)
    )
    session.commit()

    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert cell.fair_value is None
    assert cell.status == STATUS_INSUFFICIENT_DATA

    # Y cuando la fecha de corte supera la fecha de presentacion, si entra.
    posterior = ThesisBacktestService().cell(session, TICKER, date(2026, 6, 30))
    assert posterior.status == STATUS_OK
    assert posterior.point_in_time["valuation_periods"]["revenue"] == "2024-12-31"


def test_thesis_published_after_the_cutoff_is_not_yet_published(no_network):
    session = make_session()
    company = make_company(session)
    add_accounts(session, company)
    add_prices(session, company)
    add_thesis(
        session, company, created_at=date(2025, 1, 15), evidence_published_at=date(2025, 1, 15)
    )
    session.commit()

    service = ThesisBacktestService()
    antes = service.cell(session, TICKER, date(2024, 12, 31))
    assert antes.status == STATUS_NOT_YET_PUBLISHED
    assert antes.fair_value is None
    assert antes.n_claims == 0
    assert antes.source_coverage_score is None

    despues = service.cell(session, TICKER, date(2025, 6, 30))
    assert despues.status == STATUS_OK
    assert despues.n_claims == 1


def test_evidence_filed_after_the_cutoff_does_not_count_as_evidence(no_network):
    """Una claim sin evidencia publicable es una claim sin evidencia.

    Contarla como "soportada por un filing posterior" seria medir la cobertura de
    fuentes con informacion que no existia.
    """
    session = make_session()
    company = make_company(session)
    add_accounts(session, company, published_at=date(2024, 3, 15))
    add_prices(session, company)
    add_thesis(
        session, company, created_at=date(2024, 1, 31), evidence_published_at=date(2026, 5, 1)
    )
    session.commit()

    cell = ThesisBacktestService().cell(session, TICKER, date(2024, 6, 30))
    assert cell.n_claims == 1
    assert cell.n_claims_with_evidence == 0
    assert cell.source_coverage_score == 0
    assert cell.point_in_time["claims_audit"]["evidence_excluded_after_cutoff"] == 1


def test_future_price_is_never_used_as_the_reference_price(no_network):
    session = make_session()
    company = seed_company(session)
    add_future_price(session, company, day=date(2030, 1, 2))
    session.commit()
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert cell.current_price is not None and cell.current_price < 1000
    assert cell.price_date <= CUTOFF_MID
    assert cell.upside is not None


def test_future_price_does_not_leak_into_the_realized_return(no_network):
    session = make_session()
    company = seed_company(session)
    add_future_price(session, company, day=date(2030, 1, 2))
    session.commit()
    cell = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    # The 9999 print is inside every 1Y/2Y window; a leak would show up as a
    # return of several thousand percent.
    assert cell.realized["1A"]["return"] < 10
    assert cell.realized["2A"]["return"] < 10


def test_quarterly_fact_is_visible_only_after_its_quarter_end(no_network):
    session = make_session()
    company = make_company(session)
    add_accounts(
        session,
        company,
        fiscal_year=2023,
        period="2023-12-31",
        published_at=date(2024, 3, 15),
    )
    add_prices(session, company)
    add_thesis(
        session, company, created_at=date(2024, 1, 31), evidence_published_at=date(2024, 1, 31)
    )
    # A Q3 fact whose period ends on 30 September, with no filing date of its own.
    # FIX-4: sin fecha de publicacion el eje falla cerrado: el hecho no es
    # verificable y se excluye del replay, aunque su periodo ya haya pasado.
    doc = Document(
        company_id=company.id,
        title="Q3 2024 filing",
        source_type="sec",
        published_at=ts(date(2024, 10, 15)),
    )
    session.add(doc)
    session.flush()
    session.add(
        FinancialFact(
            company_id=company.id,
            metric="revenue",
            value=Decimal("1200"),
            unit="EUR",
            period="Q3 2024",
            fiscal_year=2024,
            fiscal_quarter="Q3",
            source_id=doc.id,
            source_type="sec",
            confidence=Decimal("0.9"),
        )
    )
    session.commit()

    service = ThesisBacktestService()
    # Before the quarter closes, nobody could know it: the period end is the
    # earliest possible knowledge date, not the fiscal year.
    antes = service.cell(session, TICKER, date(2024, 6, 30))
    assert antes.status == STATUS_OK
    assert antes.point_in_time["valuation_periods"].get("revenue") == "2023-12-31"
    assert not any("Q3 2024" in item for item in antes.excluded_future_inputs)
    assert antes.lookahead_violations == []

    # After the filing date (2024-10-15) it becomes knowable.
    despues = service.cell(session, TICKER, date(2024, 10, 15))
    assert despues.point_in_time["valuation_periods"]["revenue"] == "Q3 2024"
    assert despues.fair_value != antes.fair_value


# ============================================================ PRIMITIVAS PURAS


def test_period_bounds_resolve_precision_explicitly():
    exact = parse_period_bounds(period="2024-12-31")
    assert exact.end_date == date(2024, 12, 31)
    assert exact.precision == PRECISION_EXACT_DATE

    quarter = parse_period_bounds(period=None, fiscal_year=2024, fiscal_quarter="Q3")
    assert quarter.end_date == date(2024, 9, 30)
    assert quarter.precision == PRECISION_EXACT_DATE

    # A bare fiscal year resolves to the LATEST day it could have ended, which
    # is the conservative direction: it can only cause an abstention, never a leak.
    year = parse_period_bounds(period="FY2024", fiscal_year=2024)
    assert year.end_date == date(2024, 12, 31)
    assert year.precision == PRECISION_FISCAL_YEAR

    unknown = parse_period_bounds(period="sin fecha")
    assert unknown.end_date is None
    assert unknown.precision == PRECISION_UNKNOWN
    assert unknown.is_unverifiable


def test_a_quarter_period_string_resolves_to_its_calendar_quarter_end():
    bounds = parse_period_bounds(period="Q3 2024")
    assert bounds.end_date == date(2024, 9, 30)
    assert bounds.fiscal_year == 2024


def test_unknown_period_never_raises_but_is_flagged_unverifiable():
    """El guard compartido no bloquea por metadatos ausentes, a proposito.

    Bloquear una valoracion viva por una fila sin fecha seria incorrecto. En un
    replay la misma fila es un agujero, y por eso ``is_unverifiable`` existe:
    la honestidad se traslada a quien la necesita.
    """
    bounds = parse_period_bounds(period="lo que sea")
    assert_period_no_lookahead(as_of=date(2020, 1, 1), bounds=bounds, label="x")
    assert bounds.is_unverifiable


def test_period_guard_raises_on_a_future_period():
    bounds = parse_period_bounds(period=FUTURE_PERIOD)
    with pytest.raises(LookaheadError, match="look-ahead"):
        assert_period_no_lookahead(as_of=CUTOFF_MID, bounds=bounds, label="revenue")


def test_publication_guard_raises_when_the_filing_is_later():
    bounds = knowledge_bounds(
        period="2024-12-31", fiscal_year=2024, published_at=date(2026, 3, 10)
    )
    assert bounds.known_on == date(2026, 3, 10)
    with pytest.raises(LookaheadError, match="aun no era publico"):
        assert_knowledge_no_lookahead(as_of=CUTOFF_MID, bounds=bounds, label="revenue")


def test_knowledge_is_the_later_of_period_end_and_publication():
    """Las dos ejes son independientes y hay que mirar los dos.

    Tomar solo el final de periodo es el error clasico: un FY2024 depositado en
    2026 pasa el chequeo de ejercicio y arruina el replay de 2025.
    """
    tarde = knowledge_bounds(period="2024-12-31", fiscal_year=2024, published_at=date(2026, 3, 10))
    assert tarde.known_on == date(2026, 3, 10)
    temprano = knowledge_bounds(
        period="2024-12-31", fiscal_year=2024, published_at=date(2025, 2, 1)
    )
    assert temprano.known_on == date(2025, 2, 1)


def test_missing_publication_date_uses_the_period_end_as_the_lower_bound():
    """FIX-4: sin fecha de presentacion el eje falla CERRADO.

    Antes conoc_on devolvia el final del periodo y unverifiable era False,
    permitiendo look-ahead silencioso. Ahora sin published_on no hay conocimiento
    verificable: known_on es None y unverifiable es True.
    """
    bounds = knowledge_bounds(period="2024-12-31", fiscal_year=2024)
    assert bounds.published_on is None
    assert bounds.known_on is None
    assert bounds.unverifiable is True


def test_a_fact_with_no_readable_period_at_all_is_unverifiable():
    bounds = knowledge_bounds(period="pendiente de revisar", fiscal_year=None)
    assert bounds.unverifiable is True
    assert bounds.known_on is None


# ================================================== AUDITORIA DEL SNAPSHOT


def test_pit_audit_records_kept_dropped_and_unverifiable_separately():
    session = make_session()
    company = seed_company(session)
    add_future_trap(session, company)
    session.add(
        FinancialFact(
            company_id=company.id,
            metric="revenue_growth",
            value=Decimal("0.1"),
            unit="ratio",
            period="revisar",
            source_type="manual",
            confidence=Decimal("0.4"),
        )
    )
    session.commit()

    builder = PointInTimeSnapshotBuilder(as_of=CUTOFF_MID)
    snapshot = builder.build(session, company)

    kept_metrics = {item.metric for item in builder.audit.kept}
    assert "revenue" in kept_metrics
    assert any("2999" in item.reason for item in builder.audit.dropped_future)
    assert [item.metric for item in builder.audit.unverifiable] == ["revenue_growth"]
    assert builder.audit.lookahead_violations
    assert builder.audit.unverifiable_inputs
    # The trap never reaches the snapshot the engine consumed.
    assert "2999-12-31" not in snapshot.periods().values()
    # And the audit is JSON-serialisable for the point_in_time block.
    assert builder.audit.as_dict()["as_of"] == CUTOFF_MID.isoformat()


def test_assert_no_lookahead_passes_on_a_cleanly_filtered_snapshot():
    session = make_session()
    company = seed_company(session)
    add_future_trap(session, company)
    session.commit()
    builder = PointInTimeSnapshotBuilder(as_of=CUTOFF_MID)
    snapshot = builder.build(session, company)
    # Would raise if a kept fact were dated after the cutoff.
    builder.assert_no_lookahead(snapshot)


def test_replay_scope_restores_the_shared_module_attributes():
    """El ambito es reversible: la valoracion viva no queda tocada.

    Si ``FinancialSnapshotBuilder`` se quedara apuntando al builder filtrado
    fuera del ``with``, toda valoracion posterior del proceso (otra peticion, el
    worker) leeria el ultimo hecho como si fuera el unico relevante.
    """
    import app.services.valuation_service as valuation_module
    import app.valuation.engines.base as engines_base

    original_builder = engines_base.FinancialSnapshotBuilder
    original_price = valuation_module._position_price

    builder = PointInTimeSnapshotBuilder(as_of=CUTOFF_MID)
    with pit_replay_scope(builder=builder, price=42.0):
        assert engines_base.FinancialSnapshotBuilder is not original_builder
        assert valuation_module._position_price is not original_price
        # The replacement builder really is point-in-time scoped.
        assert isinstance(engines_base.FinancialSnapshotBuilder, type)

    assert engines_base.FinancialSnapshotBuilder is original_builder
    assert valuation_module._position_price is original_price


def test_replay_scope_restores_the_attributes_even_when_the_body_raises():
    import app.services.thesis_backtest_service as service_module
    import app.valuation.engines.base as engines_base

    original_builder = engines_base.FinancialSnapshotBuilder
    with pytest.raises(RuntimeError):
        with pit_replay_scope(builder=PointInTimeSnapshotBuilder(as_of=CUTOFF_MID), price=1.0):
            raise RuntimeError("boom")
    assert engines_base.FinancialSnapshotBuilder is original_builder
    del service_module


def test_live_valuation_after_a_replay_is_unaffected(no_network):
    """La prueba de que el parche no se filtra a la ruta de producto.

    Se hace un replay con una trampa en la base de datos y despues se valora la
    empresa como lo haria el producto, sin ``as_of``. Si el ambito point-in-time
    se hubiera colado, esa segunda valoracion leeria el builder filtrado, no
    veria el hecho FY2999 y devolveria un numero. Que en su lugar se levante el
    guard publico es la prueba: el camino vivo sigue leyendo "el ultimo".
    """
    from app.services.valuation_service import ValuationService

    session = make_session()
    company = seed_company(session)
    add_future_trap(session, company)
    session.commit()

    replay = ThesisBacktestService().cell(session, TICKER, CUTOFF_MID)
    assert replay.fair_value is not None and replay.fair_value < 1000

    # Live path, no as_of: the base builder reads the latest fact, FY2999, and
    # the shared guard refuses to price it. That refusal is the proof.
    with pytest.raises(LookaheadError, match="2999-12-31"):
        ValuationService().value_company(session, company)


def test_no_future_row_reaches_the_snapshot_across_a_whole_grid(no_network):
    """Invariante de la rejilla completa, no de una celda suelta."""
    session = make_session()
    for ticker in ("AAA", "BBB", "CCC"):
        company = seed_company(session, ticker=ticker)
        add_future_trap(session, company)
    session.commit()

    service = ThesisBacktestService()
    for ticker in ("AAA", "BBB", "CCC"):
        for offset in range(12):
            cutoff = date(2024, 1, 31) + timedelta(days=offset * 30)
            cell = service.cell(session, ticker, cutoff)
            assert cell.lookahead_violations == []
            assert cell.status != STATUS_REJECTED_LOOKAHEAD
            if cell.fair_value is not None:
                assert cell.fair_value < 1000
