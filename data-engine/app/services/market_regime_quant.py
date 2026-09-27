"""Point-in-time market diagnostics; absent inputs never become zeros."""
from __future__ import annotations

from datetime import date, timedelta
from math import isfinite

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, MarketObservation, MarketPrice, Position


def paired_beta(asset: dict[date, float], benchmark: dict[date, float], sessions: int) -> dict:
    """Exactly N matched daily return sessions; no forward filling or synthetic closes."""
    if sessions not in (63, 252):
        raise ValueError("Horizonte no soportado")
    dates = sorted(set(asset) & set(benchmark))
    pairs = []
    benchmark_dates = set(benchmark)
    for prior, current in zip(dates, dates[1:], strict=False):
        # The two series must each have a valid close at both endpoints.
        a0, a1, b0, b1 = asset[prior], asset[current], benchmark[prior], benchmark[current]
        # A benchmark session omitted by the asset is missing data, not a multi-day return.
        if any(prior < day < current for day in benchmark_dates):
            continue
        if all(isfinite(v) and v > 0 for v in (a0, a1, b0, b1)):
            pairs.append((current, a1 / a0 - 1, b1 / b0 - 1))
    if len(pairs) < sessions:
        return {"status": "sin datos", "required_sessions": sessions, "paired_sessions": len(pairs)}
    window = pairs[-sessions:]
    if any((b[0] - a[0]).days > 5 for a, b in zip(window, window[1:], strict=False)):
        return {"status": "sin datos", "reason": "sesiones discontinuas"}
    asset_returns, market_returns = np.array([(row[1], row[2]) for row in window]).T
    variance = np.var(market_returns, ddof=1)
    if variance <= 0:
        return {"status": "sin datos", "reason": "varianza de benchmark nula"}
    return {"status": "disponible", "beta": round(float(np.cov(asset_returns, market_returns, ddof=1)[0, 1] / variance), 4),
            "sessions": sessions, "from": window[0][0].isoformat(), "to": window[-1][0].isoformat(),
            "method": "cov(retorno activo, retorno S&P 500) / var(retorno S&P 500); cierres ajustados pareados"}


def top_ten_concentration(constituents: set[str], market_caps: dict[str, tuple[float, str, date]], as_of: date) -> dict:
    """Only complete dated, positive, sourced constituent market caps qualify."""
    if len(constituents) < 10:
        return {"status": "sin datos", "reason": "universo de constituyentes incompleto"}
    if set(market_caps) != constituents or any(
        not isfinite(cap) or cap <= 0 or not source or dated != as_of
        for cap, source, dated in market_caps.values()
    ):
        return {"status": "sin datos", "reason": "capitalizaciones positivas y fechadas incompletas"}
    total = sum(value[0] for value in market_caps.values())
    leaders = sorted(market_caps, key=lambda symbol: market_caps[symbol][0], reverse=True)[:10]
    return {"status": "disponible", "fraction": sum(market_caps[symbol][0] for symbol in leaders) / total,
            "leaders": leaders, "constituents": len(constituents), "date": as_of.isoformat()}


def filtered_hmm(points: list[tuple[date, float, float]], *, min_training: int = 126) -> dict:
    """Train on observations before t and filter through t, never smooth from future t+1."""
    if len(points) < min_training + 1 or points != sorted(points, key=lambda row: row[0]) or len({row[0] for row in points}) != len(points):
        return {"status": "sin datos", "reason": "historial insuficiente"}
    try:
        from hmmlearn.hmm import GaussianHMM

        data = np.asarray([row[1:] for row in points], dtype=float)
        if not np.isfinite(data).all():
            return {"status": "sin datos", "reason": "valores inválidos"}
        train = data[:-1]
        mean, std = train.mean(axis=0), train.std(axis=0)
        if np.any(std <= 0):
            return {"status": "sin datos", "reason": "serie constante"}
        normalized = (data - mean) / std
        model = GaussianHMM(n_components=2, covariance_type="diag", n_iter=100, random_state=29)
        model.fit(normalized[:-1])
        if not model.monitor_.converged:
            return {"status": "sin datos", "reason": "ajuste no convergente"}
        # Last row's backward probability is one; posterior there is filtered.
        _, posteriors = model.score_samples(normalized)
        probabilities = posteriors[-1]
        if not np.isfinite(probabilities).all():
            return {"status": "sin datos", "reason": "probabilidad inválida"}
        return {"status": "disponible", "date": points[-1][0].isoformat(),
                "trained_through": points[-2][0].isoformat(), "training_sessions": len(train),
                "probabilities": {f"state_{idx}": round(float(prob), 6) for idx, prob in enumerate(probabilities)},
                "method": "HMM gaussiano de 2 estados; filtro hacia adelante; estados sin etiqueta económica"}
    except (ValueError, FloatingPointError, ImportError):
        return {"status": "sin datos", "reason": "modelo no disponible"}


def observed_hmm(db: Session, as_of: date, generated_at) -> dict:
    rows = db.scalars(select(MarketObservation).where(
        MarketObservation.metric_key.in_(("vix_us", "high_yield_spread_us")),
        MarketObservation.status == "observed", MarketObservation.observation_date <= as_of,
        MarketObservation.fetched_at <= generated_at,
    ).order_by(MarketObservation.observation_date, MarketObservation.fetched_at, MarketObservation.id)).all()
    series: dict[str, dict[date, float]] = {"vix_us": {}, "high_yield_spread_us": {}}
    for row in rows:
        series[row.metric_key][row.observation_date] = float(row.value)
    paired_days = sorted(set(series["vix_us"]) & set(series["high_yield_spread_us"]))
    if not paired_days or paired_days[-1] < as_of - timedelta(days=5):
        return {"status": "sin datos", "reason": "observaciones recientes ausentes"}
    return filtered_hmm([(day, series["vix_us"][day], series["high_yield_spread_us"][day]) for day in paired_days])


def portfolio_beta(db: Session, as_of: date) -> dict:
    """Per-symbol betas for CURRENT tenant holdings; not a portfolio beta."""
    benchmark = db.scalar(select(Company).where(Company.ticker == "^GSPC"))
    positions = db.scalars(select(Position).where(Position.quantity > 0)).all()
    company_ids = {p.company_id for p in positions}
    if not benchmark or not positions:
        return {"status": "sin datos", "reason": "sin posiciones o benchmark S&P 500", "positions": {},
                "scope": "betas individuales de las posiciones actuales; no beta agregada"}
    rows = db.scalars(select(MarketPrice).where(
        MarketPrice.company_id.in_(company_ids | {benchmark.id}), MarketPrice.date <= as_of,
        MarketPrice.date >= as_of - timedelta(days=550),
    ).order_by(MarketPrice.date.desc())).all()
    prices: dict[int, dict[date, float]] = {i: {} for i in company_ids | {benchmark.id}}
    for row in rows:
        if row.adj_close and row.adj_close > 0:
            prices[row.company_id][row.date] = float(row.adj_close)
    results = {}
    if not prices[benchmark.id]:
        return {"status": "sin datos", "reason": "benchmark S&P 500 sin cierres ajustados", "positions": {},
                "scope": "betas individuales de las posiciones actuales; no beta agregada"}
    for company_id in sorted(company_ids):
        if company_id == benchmark.id:
            continue  # S&P 500 vs itself is not a useful portfolio diagnostic.
        results[str(company_id)] = {str(n): paired_beta(prices[company_id], prices[benchmark.id], n) for n in (63, 252)}
    return {"scope": "posiciones actuales al consultar, beta individual por compañía; no beta agregada de cartera",
            "status": "disponible" if results and any(v["63"]["status"] == "disponible" for v in results.values()) else "sin datos",
            "benchmark": "^GSPC", "positions": results}
