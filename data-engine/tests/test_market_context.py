from datetime import UTC, date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, MarketObservation
from app.services.market_observation_service import parse_points, store_series
from app.services.market_snapshot_service import build_snapshot, latest_snapshot


def test_missing_nonfinite_and_revision_retained():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as db:
        assert (
            parse_points([{"date": "2026-09-24", "value": "."}, {"date": "2026-09-24", "value": "NaN"}]) == []
        )
        clock = datetime(2026, 9, 25, tzinfo=UTC)
        rows = [{"date": "2026-09-24", "value": "6.25"}]
        assert store_series(db, "mortgage_30y_us", rows, clock)["added"] == 1
        assert store_series(db, "mortgage_30y_us", rows, clock)["added"] == 0
        assert (
            store_series(db, "mortgage_30y_us", [{"date": "2026-09-24", "value": "6.5"}], clock)[
                "revisions_pending"
            ]
            == 1
        )
        snap = build_snapshot(db, date(2026, 9, 25), clock)
        assert snap.metrics["mortgage_30y_us"]["value"] == 6.25
        assert snap.probabilities == {}
        assert db.query(MarketObservation).count() == 2
        assert build_snapshot(db, date(2026, 9, 25), clock).id == snap.id
        assert latest_snapshot(db)["status"] in ("disponible", "obsoleto")


def test_unavailable_is_not_zero():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as db:
        snap = build_snapshot(db, date(2026, 9, 25), datetime(2026, 9, 25, tzinfo=UTC))
        assert snap.coverage == "unavailable"
        assert snap.metrics == {}
        assert latest_snapshot(db)["status"] == "sin datos"
