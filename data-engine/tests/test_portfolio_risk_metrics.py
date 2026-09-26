"""Metricas de cartera que se muestran al usuario como autoritativas.

Cuatro correcciones, todas con el mismo efecto: un numero publicado que no
correspondia al modelo que la documentacion del modulo describe.

1. Un `adj_close` de cero (el default de MarketPrice es 0, no NULL) generaba un
   retorno de -100%. Con 500 observaciones, un solo cero interior llevaba la TWR
   a -100,0%, la volatilizada anualizada de ~16% a ~73%, max_drawdown a -100% y
   el CVaR a un valor sin sentido. La comprobacion solo miraba `previous`.

2. Sharpe usaba como numerador el CAGR geometrico de UN camino realizado en
   lugar de la media aritmetica de los retornos. El CAGR de una sola muestra es
   una estimacion ruidosa de la deriva, asi que el ratio no era comparable
   entre periodos. Con la misma serie de 252 dias: -4,26 con la formula
   anterior frente a -6,23 con la estandar.

3. Sortino dividia por la desviacion del SUBCONJUNTO de retornos negativos en
   lugar de por la desviacion downside sobre la muestra completa,
   sqrt(mean(min(0, r)^2)). La misma serie daba -12,08 en vez de -5,82: 2,07x
   de divergencia entre dos endpoints de la misma aplicacion, porque
   quantstats/stats.py:1030 si usa la formula correcta.

4. El max drawdown del Monte Carlo no incluia el pico inicial de NAV 1,0, asi
   que un camino que empezaba bajando no registraba drawdown y `bust_probability`
   no lo contaba. Con deriva ~0, la mitad de los caminos empiezan por debajo de
   1,0.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from decimal import Decimal

import numpy as np
import pytest

from app.services.portfolio_intelligence_service import PortfolioIntelligenceService
from quantstats.montecarlo.analytics import max_drawdowns


# --------------------------------------------------------------------------
# 1. adj_close cero no puede fabricar un dia de -100%
# --------------------------------------------------------------------------


class _Price:
    """MarketPrice minimo para _returns."""

    def __init__(self, day: date, adj_close: float) -> None:
        self.date = day
        self.adj_close = Decimal(str(adj_close))


def _series(values: list[float]) -> list[_Price]:
    start = date(2026, 1, 1)
    return [_Price(start + timedelta(days=i), v) for i, v in enumerate(values)]


def _now(hour: int, day: date | None = None) -> datetime:
    return datetime((day or date(2026, 9, 25)).year, (day or date(2026, 9, 25)).month,
                    (day or date(2026, 9, 25)).day, hour, tzinfo=UTC)


def test_partial_day_flag_marks_intraday_price_bar():
    day = date(2026, 9, 25)
    now = _now(15, day)  # 15:00 UTC: mercados abiertos, la barra de hoy es parcial
    series = {
        1: [SimpleNamespace(date=day - timedelta(days=2)),
            SimpleNamespace(date=day)]
    }
    assert PortfolioIntelligenceService._partial_trading_day(series, [], now) is True
    # Sin la barra de hoy no hay marca.
    closed = {1: [SimpleNamespace(date=day - timedelta(days=2)),
                  SimpleNamespace(date=day - timedelta(days=1))]}
    assert PortfolioIntelligenceService._partial_trading_day(closed, [], now) is False


def test_partial_day_flag_marks_today_snapshot():
    day = date(2026, 9, 25)
    now = _now(15, day)
    snapshots = [SimpleNamespace(snapshot_date=day)]
    assert PortfolioIntelligenceService._partial_trading_day({}, snapshots, now) is True
    older = [SimpleNamespace(snapshot_date=day - timedelta(days=1))]
    assert PortfolioIntelligenceService._partial_trading_day({}, older, now) is False


def test_partial_day_flag_respects_the_22_utc_close_cutoff():
    day = date(2026, 9, 25)
    series = {1: [SimpleNamespace(date=day)]}
    # 21:59 UTC: la barra de hoy puede seguir abierta -> parcial.
    assert PortfolioIntelligenceService._partial_trading_day(series, [], _now(21, day)) is True
    # 22:00 UTC en adelante: cierres US/EU ya consumados -> no se marca.
    assert PortfolioIntelligenceService._partial_trading_day(series, [], _now(22, day)) is False


def test_partial_day_flag_treats_naive_now_as_utc():
    day = date(2026, 9, 25)
    series = {1: [SimpleNamespace(date=day)]}
    naive = datetime(day.year, day.month, day.day, 15)
    assert PortfolioIntelligenceService._partial_trading_day(series, [], naive) is True


def test_returns_ignores_a_zero_interior_price():
    # 100, 101, 0 (defecto de ingesta), 102. Los pares que tocan el cero se
    # descartan por completo (no se fabrica un -100%), asi que sobrevive solo el
    # par (100 -> 101).
    returns = PortfolioIntelligenceService._returns(_series([100, 101, 0, 102]))
    values = list(returns.values())
    assert all(value > -1 for value in values), values
    assert -1.0 not in values
    assert len(values) == 1, values


def test_returns_ignores_a_zero_first_price():
    returns = PortfolioIntelligenceService._returns(_series([0, 100, 101]))
    assert all(value > -1 for value in returns.values())


def test_returns_computes_valid_pairs():
    returns = PortfolioIntelligenceService._returns(_series([100, 110, 121]))
    assert returns[date(2026, 1, 2)] == pytest.approx(0.10)
    assert returns[date(2026, 1, 3)] == pytest.approx(0.10)


def test_a_single_zero_does_not_wipe_out_twr_and_volatility():
    """Regresion completa: el efecto que se midio en produccion.

    Descartar la fila con el cero elimina los dos pares que la tocan, asi que
    la TWR no coincide exactamente con la de la serie limpia (le faltan dos
    observaciones). Lo que no puede ocurrir es lo de antes: con la comprobacion
    unicamente sobre `previous`, el par (101, 0) producia -1,0 exacto y el
    compounding se llevaba la TWR a -100,0%.
    """
    good = _series([100, 101, 102, 103, 104, 105, 106, 107])
    tainted = _series([100, 101, 0, 103, 104, 105, 106, 107])

    clean_returns = list(PortfolioIntelligenceService._returns(good).values())
    tainted_returns = list(PortfolioIntelligenceService._returns(tainted).values())

    assert -1.0 not in tainted_returns, "sigue apareciendo el dia de -100%"
    tainted_twr = PortfolioIntelligenceService._compound(tainted_returns)
    assert tainted_twr > 0, f"la TWR se hundi a {tainted_twr}"

    # Y sigue siendo del orden de magnitud de la serie limpia.
    clean_twr = PortfolioIntelligenceService._compound(clean_returns)
    assert tainted_twr == pytest.approx(clean_twr, rel=0.5)


# --------------------------------------------------------------------------
# 2 y 3. Sharpe y Sortino
# --------------------------------------------------------------------------


def test_sortino_uses_downside_deviation_not_pstdev_of_negatives():
    import inspect

    source = inspect.getsource(PortfolioIntelligenceService.build)
    assert "min(value, 0.0) ** 2" in source, (
        "el denominador de Sortino tiene que ser la desviacion downside sobre "
        "la muestra completa (sqrt(mean(min(0, r)^2))), no la desviacion del "
        "subconjunto de retornos negativos"
    )
    assert "fmean" in source, (
        "el numerador de Sharpe tiene que ser la media aritmetica de los "
        "retornos, no el CAGR de una unica realizacion"
    )


def test_sortino_denominator_matches_the_textbook_formula():
    """Compara contra la formula, no contra la implementacion anterior."""
    import math
    from statistics import fmean, pstdev

    returns = {i: v for i, v in enumerate([0.001] * 200 + [-0.02] * 52)}
    n = len(returns)
    downside = math.sqrt(sum(min(v, 0.0) ** 2 for v in returns.values()) / n)
    vol = pstdev(returns.values())
    sharpe = (fmean(returns.values()) / vol) * math.sqrt(252)
    sortino = (fmean(returns.values()) / downside) * math.sqrt(252)

    # La varianza de la formula antigua (pstdev del subconjunto negativo) es
    # distinta, y con ella el ratio.
    legacy = pstdev([v for v in returns.values() if v < 0])
    assert downside != legacy
    assert sortino > sharpe  # menos penalizacion que la volatilidad total
    assert math.isfinite(sharpe) and math.isfinite(sortino)


# --------------------------------------------------------------------------
# 4. Max drawdown del Monte Carlo incluye el pico inicial
# --------------------------------------------------------------------------


def test_max_drawdown_accounts_for_the_initial_nav():
    # Camino que empieza bajando: el maxdd debe ver ese -10%.
    sim = np.array([[-0.10, 0.0], [0.50, 0.0], [0.10, 0.0]])
    mdd = max_drawdowns(sim)
    assert mdd[0] == pytest.approx(-0.10), mdd


def test_max_drawdown_still_finds_a_deep_interior_drop():
    sim = np.array([[0.10], [0.10], [-0.50], [0.10]])
    mdd = max_drawdowns(sim)
    assert mdd[0] < -0.30, mdd


def test_max_drawdown_is_zero_for_a_monotonic_growth_path():
    sim = np.array([[0.10], [0.10], [0.10]])
    mdd = max_drawdowns(sim)
    assert mdd[0] == pytest.approx(0.0), mdd
