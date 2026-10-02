"""Hit-rate de tesis: la definicion de acierto, el look-ahead y el denominador
(#E5, metrica 3).

Estos tests son la defensa contra el fallo que ya se sufrio en otro punto del
repo: un `hit_rate 1.0` sobre 14 celdas con un aviso SOSPECHOSO. aqui se
comprueba, uno por uno, que el numerador, el denominador y los excluidos viajan
siempre y que la exclusion se cuenta con su motivo.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.metrics import config, prometheus
from app.metrics import thesis as thesis_stats
from app.models.entities import Company, MarketPrice, ThesisVersion
from app.models.metrics import ThesisHitRateCell

TODAY = date(2026, 6, 30)
HORIZON = 30


def _session(tenant_id: int | None = 1):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    if tenant_id is not None:
        session.info["tenant_id"] = tenant_id
    return session


def _company(session, ticker: str, sector: str = "Tecnologia") -> Company:
    company = Company(
        ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
        sector=sector, company_type="operating", valuation_model="dcf",
    )
    session.add(company)
    session.commit()
    return company


def _prices(session, company: Company, start: date, count: int, step_days: int = 10,
            start_price: float = 100.0, adjusted: bool = False) -> None:
    for index in range(count):
        day = start + timedelta(days=index * step_days)
        row = MarketPrice(
            company_id=company.id, date=day,
            open=Decimal("1"), high=Decimal("1"), low=Decimal("1"),
            close=Decimal(str(start_price * (1 + 0.01 * index))),
            volume=1000, source="test",
        )
        if adjusted:
            row.adj_close = row.close
        session.add(row)
    session.commit()


def _thesis(session, company: Company, published: date, rating: str,
            coverage: int = 80) -> ThesisVersion:
    # `thesis_versions` es UNIQUE en (tenant_id, company_id, version): varias
    # tesis de la misma empresa son varias VERSIONES, que es justo lo que el
    # hit-rate cuenta (una regeneracion es una opinion nueva, no una repetida).
    siguiente = len(
        session.query(ThesisVersion).filter(ThesisVersion.company_id == company.id).all()
    ) + 1
    version = ThesisVersion(
        company_id=company.id,
        version=siguiente,
        status="final",
        thesis_markdown="# tesis",
        executive_summary="resumen",
        rating=rating,
        source_coverage_score=coverage,
    )
    session.add(version)
    session.commit()
    # `created_at` tiene default del modelo; se fuerza para controlar la fecha de
    # publicacion sin depender de como se inicialice el reloj en el test.
    version.created_at = datetime(
        published.year, published.month, published.day, 12, 0, 0
    )
    session.commit()
    return version


# --- la definicion de acierto ------------------------------------------------


@pytest.mark.parametrize(
    ("rating", "direction", "decision", "excluded"),
    [
        ("attractive", 1, thesis_stats.RATING_LONG, None),
        ("expensive", -1, thesis_stats.RATING_SHORT, None),
        ("watch", 0, thesis_stats.ANY, "decision_neutra"),
        ("blocked", 0, thesis_stats.ANY, "decision_neutra"),
        ("incomplete_price", 0, thesis_stats.ANY, "decision_neutra"),
        ("insufficient_data", 0, thesis_stats.ANY, "decision_neutra"),
        ("", 0, thesis_stats.ANY, "rating_desconocido"),
        ("inventado_ayer", 0, thesis_stats.ANY, "decision_neutra"),
    ],
)
def test_la_direccion_sale_del_rating_del_repo(rating, direction, decision, excluded):
    resultado = thesis_stats.direction_for(rating)
    assert resultado == (direction, decision, excluded)


def test_una_tesis_neutra_no_es_un_fallo():
    # Meter `watch` en el denominador como fallo baja el hit-rate sin que nadie
    # haya apostado nada. Es la primera forma de fabricar un numero pessimistico.
    session = _session()
    company = _company(session, "NEUT")
    _thesis(session, company, date(2026, 1, 1), "watch")
    rows, outcomes, _defs = thesis_stats.compute_hit_rate(
        session, as_of=TODAY, horizons=(HORIZON,)
    )
    global_row = next(
        row for row in rows
        if row.decision == thesis_stats.ANY and row.sector == thesis_stats.ANY
        and row.evidence_bucket == thesis_stats.ANY
    )
    assert global_row.evaluated == 0
    assert global_row.hit_rate is None
    assert global_row.excluded_neutral == 1
    assert outcomes[0].excluded == "decision_neutra"


# --- look-ahead -------------------------------------------------------------


def test_la_entrada_es_el_primer_cierre_posterior_a_la_publicacion():
    session = _session()
    company = _company(session, "LOOK")
    publicado = date(2026, 2, 10)
    # Serie que empieza ANTES de la publicacion con precios mas bajos: usar el
    # precio anterior seria comprar antes de que la tesis existiera.
    _prices(session, company, date(2026, 1, 1), 30, step_days=7, start_price=10.0)
    version = _thesis(session, company, publicado, "attractive")
    outcome = thesis_stats.evaluate_thesis(
        session, version, horizon_days=HORIZON, as_of=TODAY,
        benchmark_company_id=None, sectors={company.id: "Tecnologia"},
        tickers={company.id: "LOOK"},
    )
    assert outcome.entry_date is not None
    assert outcome.entry_date >= publicado


def test_reescribir_la_tesis_no_rebobina_el_precio_de_entrada():
    # `updated_at` cambia al reescribir; usarlo seria look-ahead. Aqui se
    # comprueba que la fecha de publicacion es `created_at` y no "la ultima vez
    # que se toco la fila".
    session = _session()
    company = _company(session, "EDIT")
    publicado = date(2026, 2, 10)
    _prices(session, company, date(2026, 2, 10), 20, step_days=5)
    version = _thesis(session, company, publicado, "attractive")
    version.created_at = datetime(2026, 2, 10, 12, 0, 0)
    version.updated_at = datetime(2026, 5, 1, 8, 0, 0)
    session.commit()
    assert thesis_stats.published_date(version) == publicado


def test_un_horizonte_que_no_ha_ocurrido_es_demasiado_temprano():
    session = _session()
    company = _company(session, "JOVEN")
    _prices(session, company, date(2026, 6, 20), 5, step_days=2)
    version = _thesis(session, company, date(2026, 6, 20), "attractive")
    outcome = thesis_stats.evaluate_thesis(
        session, version, horizon_days=180, as_of=TODAY,
        benchmark_company_id=None, sectors={}, tickers={},
    )
    assert outcome.excluded == "demasiado_temprano"
    assert outcome.hit is None


def test_evaluar_a_mitad_de_camino_es_demasiado_temprano_aunque_haya_precios():
    # La trampa clasica: hay 45 dias de precios y se evalua el horizonte de 180.
    # Sale "acierto" o "fallo" y el hit-rate sube sin motivo.
    session = _session()
    company = _company(session, "MITAD")
    _prices(session, company, date(2026, 3, 1), 12, step_days=5)
    version = _thesis(session, company, date(2026, 3, 1), "attractive")
    outcome = thesis_stats.evaluate_thesis(
        session, version, horizon_days=180, as_of=TODAY,
        benchmark_company_id=None, sectors={}, tickers={},
    )
    assert outcome.excluded == "demasiado_temprano"


def test_sin_precios_es_excluido_y_no_fallo():
    session = _session()
    company = _company(session, "SINPX")
    version = _thesis(session, company, date(2026, 1, 1), "attractive")
    outcome = thesis_stats.evaluate_thesis(
        session, version, horizon_days=HORIZON, as_of=TODAY,
        benchmark_company_id=None, sectors={}, tickers={},
    )
    assert outcome.excluded == "sin_precio_entrada"


def test_sin_serie_ajustada_se_usa_close_y_no_se_mezcla():
    session = _session()
    company = _company(session, "MIX")
    _prices(session, company, date(2026, 1, 1), 20, step_days=5, adjusted=False)
    rows = thesis_stats._series(session, company.id, date(2026, 1, 1), TODAY)
    assert thesis_stats._price_column(rows) == "close"


def test_sin_movimiento_el_retorno_cero_es_empate_no_certeza():
    session = _session()
    company = _company(session, "PLANO")
    published = date(2026, 1, 1)
    for offset in range(8):
        session.add(
            MarketPrice(
                company_id=company.id, date=published + timedelta(days=offset * 5),
                open=Decimal("1"), high=Decimal("1"), low=Decimal("1"),
                close=Decimal("50"), volume=1, source="test",
                adj_close=Decimal("50"),
            )
        )
    session.commit()
    version = _thesis(session, company, published, "attractive")
    outcome = thesis_stats.evaluate_thesis(
        session, version, horizon_days=30, as_of=TODAY,
        benchmark_company_id=None, sectors={}, tickers={},
    )
    assert outcome.excluded == "empate"
    assert outcome.hit is None


# --- acierto por direccion --------------------------------------------------


def test_una_tesis_alcista_que_sube_acierta_y_una_que_baja_falla():
    session = _session()
    buena = _company(session, "SUBE")
    mala = _company(session, "BAJA")
    published = date(2026, 1, 1)
    _prices(session, buena, published, 8, step_days=5, start_price=100.0, adjusted=True)
    for index in range(8):
        session.add(
            MarketPrice(
                company_id=mala.id, date=published + timedelta(days=index * 5),
                open=Decimal("1"), high=Decimal("1"), low=Decimal("1"),
                close=Decimal(str(100.0 - index * 2)), volume=1, source="test",
                adj_close=Decimal(str(100.0 - index * 2)),
            )
        )
    session.commit()
    assert thesis_stats.evaluate_thesis(
        session, _thesis(session, buena, published, "attractive"),
        horizon_days=HORIZON, as_of=TODAY, benchmark_company_id=None,
        sectors={}, tickers={},
    ).hit is True
    assert thesis_stats.evaluate_thesis(
        session, _thesis(session, mala, published, "attractive"),
        horizon_days=HORIZON, as_of=TODAY, benchmark_company_id=None,
        sectors={}, tickers={},
    ).hit is False


def test_una_tesis_bajista_que_baja_acierta():
    session = _session()
    company = _company(session, "BEAROK")
    published = date(2026, 1, 1)
    for index in range(8):
        session.add(
            MarketPrice(
                company_id=company.id, date=published + timedelta(days=index * 5),
                open=Decimal("1"), high=Decimal("1"), low=Decimal("1"),
                close=Decimal(str(100.0 - index * 2)), volume=1, source="test",
                adj_close=Decimal(str(100.0 - index * 2)),
            )
        )
    session.commit()
    outcome = thesis_stats.evaluate_thesis(
        session, _thesis(session, company, published, "expensive"),
        horizon_days=HORIZON, as_of=TODAY, benchmark_company_id=None,
        sectors={}, tickers={},
    )
    assert outcome.hit is True
    assert outcome.direction == -1


# --- alpha contra benchmark -------------------------------------------------


def test_el_alpha_usa_las_mismas_fechas_que_la_tesis():
    session = _session()
    empresa = _company(session, "ALFA")
    indice = _company(session, config.benchmark_ticker(), sector="Indice")
    published = date(2026, 1, 1)
    _prices(session, empresa, published, 8, step_days=5, start_price=100.0, adjusted=True)
    _prices(session, indice, published, 8, step_days=5, start_price=200.0, adjusted=True)
    session.commit()
    version = _thesis(session, empresa, published, "attractive")
    outcome = thesis_stats.evaluate_thesis(
        session, version, horizon_days=HORIZON, as_of=TODAY,
        benchmark_company_id=indice.id,
        sectors={empresa.id: "Tecnologia"}, tickers={empresa.id: "ALFA"},
    )
    assert outcome.entry_date is not None and outcome.exit_date is not None
    # El benchmark se mide en EXACTAMENTE el mismo tramo que la tesis: primer y
    # ultimo cierre de [entry, exit]. Si usara otras fechas, el alpha compararia
    # dos periodos distintos y no significaria nada.
    tramo = thesis_stats._series(
        session, indice.id, outcome.entry_date, outcome.exit_date
    )
    primero = float(tramo[0].adj_close)
    ultimo = float(tramo[-1].adj_close)
    assert outcome.benchmark_return_pct == pytest.approx((ultimo / primero - 1) * 100)
    assert outcome.excluded is None


def test_sin_indice_el_alpha_es_nd_con_motivo_nunca_cero():
    session = _session()
    empresa = _company(session, "NOIDX")
    published = date(2026, 1, 1)
    _prices(session, empresa, published, 8, step_days=5, adjusted=True)
    version = _thesis(session, empresa, published, "attractive")
    rows, _outcomes, _defs = thesis_stats.compute_hit_rate(
        session, as_of=TODAY, horizons=(HORIZON,)
    )
    global_row = next(
        row for row in rows
        if row.decision == thesis_stats.ANY and row.sector == thesis_stats.ANY
        and row.evidence_bucket == thesis_stats.ANY
    )
    assert global_row.alpha is None
    assert global_row.benchmark_status == "N/D"
    assert config.benchmark_ticker() in (global_row.benchmark_reason or "")
    assert global_row.hit_rate is not None  # el acierto se sigue podrendo medir
    payload = thesis_stats.hit_rate_payload(global_row)
    assert payload["alpha_vs_benchmark"]["valor"] is None
    assert payload["alpha_vs_benchmark"]["estado"] == "N/D"
    del version


# --- el denominador y los excluidos, siempre visibles -----------------------


def test_el_payload_siempre_lleva_numerador_denominador_y_excluidos():
    session = _session()
    company = _company(session, "FULL")
    published = date(2026, 1, 1)
    _prices(session, company, published, 8, step_days=5, adjusted=True)
    _thesis(session, company, published, "attractive")
    _thesis(session, company, published, "watch")
    rows, _outcomes, _defs = thesis_stats.compute_hit_rate(
        session, as_of=TODAY, horizons=(HORIZON,)
    )
    payload = next(
        thesis_stats.hit_rate_payload(row) for row in rows
        if row.decision == thesis_stats.ANY and row.sector == thesis_stats.ANY
        and row.evidence_bucket == thesis_stats.ANY
    )
    assert payload["numerador_aciertos"] == payload["denominador_evaluados"] + payload["fallos"]
    assert payload["excluidos"]["decision_neutra"] == 1
    assert payload["excluidos_total"] == 1
    # Y la definicion viaja con el dato: un hit-rate historico sin su regla no es
    # auditable.
    assert payload["definiciones"]["acierto"]
    assert payload["definiciones"]["entrada"].startswith("primer cierre")
    assert payload["definiciones"]["horizontes_dias"] == [HORIZON]


def test_sin_denominador_el_hit_rate_es_nd_no_cero():
    session = _session()
    company = _company(session, "VACIA")
    _thesis(session, company, date(2026, 6, 20), "attractive")  # sin precios
    rows, _outcomes, _defs = thesis_stats.compute_hit_rate(
        session, as_of=TODAY, horizons=(HORIZON,)
    )
    payload = next(
        thesis_stats.hit_rate_payload(row) for row in rows
        if row.decision == thesis_stats.ANY and row.sector == thesis_stats.ANY
        and row.evidence_bucket == thesis_stats.ANY
    )
    assert payload["denominador_evaluados"] == 0
    assert payload["hit_rate"]["estado"] == "N/D"
    assert payload["hit_rate"]["valor"] is None
    assert "sin_precio_entrada" in payload["hit_rate"]["motivo"]
    # Y la prueba de que no es propaganda: un 0 aqui seria "acertamos el 0 %".
    assert payload["hit_rate"]["valor"] != 0


def test_recalcular_el_mismo_dia_reemplaza_no_apila():
    session = _session()
    company = _company(session, "IDEM")
    published = date(2026, 1, 1)
    _prices(session, company, published, 8, step_days=5, adjusted=True)
    _thesis(session, company, published, "attractive")
    thesis_stats.compute_hit_rate(session, as_of=TODAY, horizons=(HORIZON,))
    primera = session.query(ThesisHitRateCell).count()
    thesis_stats.compute_hit_rate(session, as_of=TODAY, horizons=(HORIZON,))
    assert session.query(ThesisHitRateCell).count() == primera


# --- desagregacion por decision, sector y calidad de evidencia --------------


def test_las_cinco_familias_de_corte_se_emiten():
    session = _session()
    tech = _company(session, "TEC1", sector="Tecnologia")
    health = _company(session, "SAL1", sector="Salud")
    published = date(2026, 1, 1)
    _prices(session, tech, published, 8, step_days=5, adjusted=True)
    _prices(session, health, published, 8, step_days=5, adjusted=True)
    _thesis(session, tech, published, "attractive", coverage=90)
    _thesis(session, health, published, "attractive", coverage=20)
    rows, _outcomes, _defs = thesis_stats.compute_hit_rate(
        session, as_of=TODAY, horizons=(HORIZON,)
    )
    claves = {(row.horizon_days, row.decision, row.sector, row.evidence_bucket) for row in rows}
    # (1) total, (2) por decision, (3) por sector, (4) por evidencia,
    # (5) sector x evidencia.
    assert (HORIZON, thesis_stats.ANY, thesis_stats.ANY, thesis_stats.ANY) in claves
    assert (HORIZON, thesis_stats.RATING_LONG, thesis_stats.ANY, thesis_stats.ANY) in claves
    assert (HORIZON, thesis_stats.ANY, "Tecnologia", thesis_stats.ANY) in claves
    assert (HORIZON, thesis_stats.ANY, thesis_stats.ANY, "76-100") in claves
    assert (HORIZON, thesis_stats.ANY, "Salud", "0-25") in claves


def test_una_tesis_neutra_no_contamina_el_corte_por_decision():
    session = _session()
    company = _company(session, "MIXDEC")
    published = date(2026, 1, 1)
    _prices(session, company, published, 8, step_days=5, adjusted=True)
    _thesis(session, company, published, "attractive")
    _thesis(session, company, published, "watch")
    rows, _outcomes, _defs = thesis_stats.compute_hit_rate(
        session, as_of=TODAY, horizons=(HORIZON,)
    )
    compra = next(
        row for row in rows
        if row.decision == thesis_stats.RATING_LONG and row.sector == thesis_stats.ANY
        and row.evidence_bucket == thesis_stats.ANY
    )
    assert compra.evaluated == 1
    assert compra.excluded_neutral == 0


def test_el_tramo_de_evidencia_sale_del_score_ya_persistido():
    assert thesis_stats.evidence_bucket(0) == "0-25"
    assert thesis_stats.evidence_bucket(26) == "26-50"
    assert thesis_stats.evidence_bucket(51) == "51-75"
    assert thesis_stats.evidence_bucket(100) == "76-100"
    assert thesis_stats.evidence_bucket(None) == "desconocido"


def test_la_calidad_de_evidencia_es_una_dimension_del_hit_rate():
    # Dos tesis identicas salvo en el sourcing. Si el sourcing no cambiase nada,
    # esto seria una dimension decorativa.
    session = _session()
    bien = _company(session, "BIEN")
    mal = _company(session, "MAL")
    published = date(2026, 1, 1)
    _prices(session, bien, published, 8, step_days=5, start_price=100.0, adjusted=True)
    _prices(session, mal, published, 8, step_days=5, start_price=50.0, adjusted=True)
    _thesis(session, bien, published, "attractive", coverage=95)
    _thesis(session, mal, published, "attractive", coverage=5)
    rows, _outcomes, _defs = thesis_stats.compute_hit_rate(
        session, as_of=TODAY, horizons=(HORIZON,)
    )
    por_bucket = {
        row.evidence_bucket: row for row in rows
        if row.sector == thesis_stats.ANY and row.decision == thesis_stats.ANY
    }
    assert por_bucket["76-100"].evaluated == 1
    assert por_bucket["0-25"].evaluated == 1


# --- aislamiento por tenant -------------------------------------------------


def test_dos_tenants_no_comparten_celdas():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def sembrar(tenant_id: int, ticker: str) -> None:
        session = factory()
        session.info["tenant_id"] = tenant_id
        company = Company(
            ticker=ticker, name=ticker, exchange="NASDAQ", currency="USD",
            sector="Tecnologia", company_type="operating", valuation_model="dcf",
        )
        session.add(company)
        session.commit()
        published = date(2026, 1, 1)
        _prices(session, company, published, 8, step_days=5, adjusted=True)
        _thesis(session, company, published, "attractive")
        thesis_stats.compute_hit_rate(session, as_of=TODAY, horizons=(HORIZON,))
        session.close()

    sembrar(1, "T-ONE")
    sembrar(2, "T-TWO")

    uno = factory()
    uno.info["tenant_id"] = 1
    filas_uno, total_uno = thesis_stats.cells_for(uno, as_of=TODAY)
    assert total_uno > 0
    assert {row.tenant_id for row in filas_uno} == {1}

    dos = factory()
    dos.info["tenant_id"] = 2
    filas_dos, total_dos = thesis_stats.cells_for(dos, as_of=TODAY)
    assert {row.tenant_id for row in filas_dos} == {2}
    assert filas_uno[0].hits == filas_dos[0].hits == 1


# --- paginacion y prometheus ------------------------------------------------


def test_la_paginacion_de_celdas_no_se_solapa():
    session = _session()
    companies = [_company(session, f"P{i}") for i in range(6)]
    published = date(2026, 1, 1)
    for company in companies:
        _prices(session, company, published, 8, step_days=5, adjusted=True)
        _thesis(session, company, published, "attractive")
    thesis_stats.compute_hit_rate(session, as_of=TODAY, horizons=(HORIZON, 90, 180))
    primera, total = thesis_stats.cells_for(session, as_of=TODAY, limit=3, offset=0)
    segunda, _ = thesis_stats.cells_for(session, as_of=TODAY, limit=3, offset=3)
    claves_una = {(r.horizon_days, r.decision, r.sector, r.evidence_bucket) for r in primera}
    claves_dos = {(r.horizon_days, r.decision, r.sector, r.evidence_bucket) for r in segunda}
    assert total > 6
    assert claves_una and claves_dos
    assert claves_una.isdisjoint(claves_dos)


def test_prometheus_expone_el_denominador_y_los_excluidos():
    session = _session()
    company = _company(session, "PROM")
    published = date(2026, 1, 1)
    _prices(session, company, published, 8, step_days=5, adjusted=True)
    _thesis(session, company, published, "attractive")
    _thesis(session, company, published, "watch")
    rows, _outcomes, _defs = thesis_stats.compute_hit_rate(
        session, as_of=TODAY, horizons=(HORIZON,)
    )
    cuerpo = prometheus.hit_rate_metrics(rows, tenant_id=1)
    texto = "\n".join(cuerpo)
    assert "cavaai_hit_rate_aciertos" in texto
    assert "cavaai_hit_rate_evaluados" in texto
    assert 'motivo="decision_neutra"' in texto
    assert "# TYPE cavaai_hit_rate_evaluados gauge" in texto
    # Las tres cosas en la misma METRICA: un Monitor solo lee un nombre de serie
    # y tiene que poder alertar sin saber nada del formato.
    bloque = [line for line in texto.splitlines() if line.startswith("cavaai_hit_rate")]
    assert any("decision_neutra" in line for line in bloque)


def test_prometheus_no_expone_un_ratio_sin_denominador():
    session = _session()
    company = _company(session, "NOPROM")
    _thesis(session, company, date(2026, 6, 20), "attractive")
    rows, _outcomes, _defs = thesis_stats.compute_hit_rate(
        session, as_of=TODAY, horizons=(HORIZON,)
    )
    texto = "\n".join(prometheus.hit_rate_metrics(rows, tenant_id=1))
    assert "cavaai_hit_rate{" not in texto
    assert "cavaai_hit_rate_no_medible{" in texto


def test_el_sector_en_blanco_cuenta_como_desconocido():
    # El sector se normaliza al indexar, no al evaluar: si se normalizara en el
    # handler, un espacio en blanco crearia su propia serie.
    session = _session()
    company = _company(session, "SINSEC", sector="   ")
    session.commit()
    session.info.pop("tenant_id", None)
    sectors, tickers = thesis_stats._company_index(session, {company.id})
    assert sectors[company.id] == thesis_stats.UNKNOWN_SECTOR
    assert tickers[company.id] == "SINSEC"


def test_una_tesis_sin_created_at_falla_de_forma_explicita():
    session = _session()
    company = _company(session, "SINFECHA")
    version = _thesis(session, company, date(2026, 1, 1), "attractive")
    object.__setattr__(version, "created_at", None)
    with pytest.raises(ValueError, match="created_at"):
        thesis_stats.published_date(version)


def test_la_fecha_de_publicacion_aware_se_convierte_a_utc():
    session = _session()
    company = _company(session, "AWARE")
    version = _thesis(session, company, date(2026, 1, 1), "attractive")
    version.created_at = datetime(2026, 3, 1, 23, 30, tzinfo=UTC)
    assert thesis_stats.published_date(version) == date(2026, 3, 1)

# --- API --------------------------------------------------------------------


_schema_ready = False


def _ensure_schema() -> None:
    """Crea el esquema en la SQLite de la sesion (la de conftest, no una propia)."""
    global _schema_ready
    if _schema_ready:
        return
    from app.core.database import init_db

    init_db()
    _schema_ready = True


def _api_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes.metrics import router as metrics_router

    _ensure_schema()
    app = FastAPI()
    app.include_router(metrics_router, prefix="/api/metrics")
    return TestClient(app)


def test_el_endpoint_de_hit_rate_sin_datos_no_inventa_un_cero():
    cuerpo = _api_client().get("/api/metrics/hit-rate").json()
    assert cuerpo["metrica"] == "hit_rate_de_tesis"
    assert cuerpo["precalculado"] is True
    assert cuerpo["celdas"] == []
    # Sin celdas tampoco hay hit-rate: elendpoint no devuelve un 0 global.
    assert "hit_rate" not in cuerpo



# --- API --------------------------------------------------------------------


_schema_ready = False


def _ensure_schema() -> None:
    """Crea el esquema en la SQLite de la sesion (la de conftest, no una propia)."""
    global _schema_ready
    if _schema_ready:
        return
    from app.core.database import init_db

    init_db()
    _schema_ready = True


def _api_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes.metrics import router as metrics_router

    _ensure_schema()
    app = FastAPI()
    app.include_router(metrics_router, prefix="/api/metrics")
    return TestClient(app)


def _celda(horizonte: int, **campos) -> ThesisHitRateCell:
    base = {
        "tenant_id": None,
        "as_of": date.today(),
        "horizon_days": horizonte,
        "decision": thesis_stats.ANY,
        "sector": thesis_stats.ANY,
        "evidence_bucket": thesis_stats.ANY,
        "definitions": {"version": 1},
    }
    base.update(campos)
    return ThesisHitRateCell(**base)


def test_el_endpoint_de_hit_rate_sin_datos_no_inventa_un_cero():
    cuerpo = _api_client().get("/api/metrics/hit-rate").json()
    assert cuerpo["metrica"] == "hit_rate_de_tesis"
    assert cuerpo["precalculado"] is True
    # Sin celdas tampoco hay hit-rate: el endpoint no devuelve un 0 global.
    assert "hit_rate" not in cuerpo


def test_el_endpoint_de_hit_rate_trae_las_celdas_con_denominador():
    from app.core.database import SessionLocal

    _ensure_schema()
    db = SessionLocal()
    db.info["tenant_id"] = None
    try:
        db.add(_celda(90, hits=3, misses=1, evaluated=4, hit_rate=0.75,
                      excluded_neutral=2, alpha=1.5, benchmark_status="ok"))
        db.add(_celda(180, hits=0, misses=0, evaluated=0, hit_rate=None,
                      excluded_too_early=7, benchmark_status="N/D",
                      benchmark_reason="sin precios del benchmark para las fechas"))
        db.commit()
    finally:
        db.close()

    cuerpo = _api_client().get("/api/metrics/hit-rate").json()
    celdas = {celda["horizonte_dias"]: celda for celda in cuerpo["celdas"]}
    assert celdas[90]["numerador_aciertos"] == 3
    assert celdas[90]["denominador_evaluados"] == 4
    assert celdas[90]["hit_rate"]["valor"] == pytest.approx(0.75)
    assert celdas[90]["excluidos"]["decision_neutra"] == 2
    assert celdas[90]["alpha_vs_benchmark"]["valor"] == pytest.approx(1.5)
    # La celda sin evaluados: N/D con el desglose de exclusiones al lado.
    assert celdas[180]["hit_rate"]["estado"] == "N/D"
    assert celdas[180]["hit_rate"]["valor"] is None
    assert celdas[180]["excluidos"]["demasiado_temprano"] == 7
    assert "7" in celdas[180]["hit_rate"]["motivo"]
    assert cuerpo["total_celdas"] == 2


def test_el_endpoint_filtra_por_horizonte():
    cuerpo = _api_client().get("/api/metrics/hit-rate", params={"horizonte": 90}).json()
    assert {celda["horizonte_dias"] for celda in cuerpo["celdas"]} == {90}


def test_el_endpoint_expone_la_definicion_aunque_no_haya_celdas():
    cuerpo = _api_client().get(
        "/api/metrics/hit-rate", params={"as_of": "2020-01-01"}
    ).json()
    # La regla se declara aunque el dia no tenga datos: quien lee tiene que saber
    # QUE se esta midiendo antes de preguntar CUANTO.
    assert cuerpo["definiciones"]["version"] == 1
    assert cuerpo["definiciones"]["direccion"]["+1"] == "rating == 'attractive'"
    assert "created_at" in cuerpo["definiciones"]["fecha_publicacion"]
    assert cuerpo["retencion_dias"] == config.retention_days("thesis_hit_rate_cells")
