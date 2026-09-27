from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, MarketObservation
from app.services.market_regime_quant import filtered_hmm, paired_beta, top_ten_concentration
from app.services.market_snapshot_service import build_snapshot


def test_beta_requires_paired_sessions_and_ignores_missing_closes():
    start = date(2026, 1, 5)
    days = [start + timedelta(days=i) for i in range(253)]
    market = {day: 100 * 1.001**i for i, day in enumerate(days)}
    asset = {day: 80 * 1.002**i for i, day in enumerate(days)}
    assert paired_beta(asset, market, 63)["status"] == "disponible"
    assert paired_beta(asset, market, 252)["status"] == "disponible"
    asset.pop(days[-3])
    assert paired_beta(asset, market, 252)["status"] == "sin datos"
    assert paired_beta({}, market, 63)["status"] == "sin datos"


def test_top_ten_needs_complete_same_day_caps():
    day = date(2026, 9, 25)
    constituents = {f"T{i}" for i in range(11)}
    caps = {symbol: (float(i + 1), "vendor citation", day) for i, symbol in enumerate(sorted(constituents))}
    assert top_ten_concentration(constituents, caps, day)["status"] == "disponible"
    caps.pop("T0")
    assert top_ten_concentration(constituents, caps, day)["status"] == "sin datos"


def test_hmm_no_future_lookahead_and_snapshot_exposes_probability():
    pytest.importorskip("hmmlearn")
    start = date(2026, 1, 1)
    points = [(start + timedelta(days=i), 15 + (i % 9) / 3 + (i % 4) / 5,
               3 + (i % 7) / 9 + (i % 5) / 4) for i in range(130)]
    baseline = filtered_hmm(points)
    assert baseline["status"] == "disponible"
    assert baseline["trained_through"] == points[-2][0].isoformat()
    future = points + [(points[-1][0] + timedelta(days=1), 100, 100)]
    assert filtered_hmm(future[:-1])["probabilities"] == baseline["probabilities"]
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as db:
        generated = datetime(2026, 9, 25, tzinfo=UTC)
        for day, vix, spread in points:
            for key, value in (("vix_us", vix), ("high_yield_spread_us", spread)):
                db.add(MarketObservation(metric_key=key, geography="US", observation_date=day,
                    value=Decimal(str(value)), unit="index", source="FRED", source_url="https://fred.stlouisfed.org/",
                    fetched_at=generated, vintage="initial", status="observed"))
        db.commit()
        snap = build_snapshot(db, points[-1][0], generated)
        assert snap.probabilities == baseline["probabilities"]
        assert snap.metrics["hmm"]["status"] == "disponible"
