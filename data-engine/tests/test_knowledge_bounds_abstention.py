"""Abstencion point-in-time: sin fecha de publicacion no hay `known_on`.

Extraccion del auditor (11 oct): un hecho sin `published_on` no puede
acreditar cuando fue conocido; en un backtest, asumir el fin de periodo como
fecha de conocimiento es una fuga de futuro. `resolve_as_of` ademas acepta
`trace["snapshot"]["as_of]` como origen del corte.
"""

from __future__ import annotations

from datetime import date

from app.valuation.period_bounds import (
    AS_OF_SOURCE_TRACE,
    PRECISION_EXACT_DATE,
    KnowledgeBounds,
    PeriodBounds,
    resolve_as_of,
)


def _bounds(published_on: date | None) -> KnowledgeBounds:
    return KnowledgeBounds(
        period=PeriodBounds(
            raw="2025-12-31",
            end_date=date(2025, 12, 31),
            fiscal_year=2025,
            precision=PRECISION_EXACT_DATE,
        ),
        published_on=published_on,
    )


def test_sin_published_on_se_abstiene_en_vez_de_asumir_fin_de_periodo():
    bounds = _bounds(None)
    assert bounds.known_on is None
    assert bounds.unverifiable is True


def test_con_published_on_known_on_es_el_maximo_de_ambos_ejes():
    assert _bounds(date(2026, 3, 15)).known_on == date(2026, 3, 15)
    assert _bounds(date(2025, 1, 10)).known_on == date(2025, 12, 31)
    assert _bounds(date(2026, 3, 15)).unverifiable is False


def test_resolve_as_of_acepta_snapshot_as_of_del_trace():
    r = resolve_as_of(trace={"snapshot": {"as_of": "2026-09-30"}}, today=date(2026, 10, 11))
    assert r.cutoff == date(2026, 9, 30)
    assert r.source == AS_OF_SOURCE_TRACE
    assert r.inferred is False


def test_trace_as_of_directo_tiene_precedencia_sobre_snapshot():
    r = resolve_as_of(
        trace={"as_of": "2026-08-01", "snapshot": {"as_of": "2026-09-30"}},
        today=date(2026, 10, 11),
    )
    assert r.cutoff == date(2026, 8, 1)
    assert r.source == AS_OF_SOURCE_TRACE
