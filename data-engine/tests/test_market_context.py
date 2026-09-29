from datetime import UTC, date, datetime, timedelta

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
                "revisions_applied"
            ]
            == 1
        )
        snap = build_snapshot(db, date(2026, 9, 25), clock)
        assert snap.metrics["mortgage_30y_us"]["value"] == 6.5
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
        assert snap.metrics["hmm"]["status"] == "sin datos"
        assert latest_snapshot(db)["status"] == "sin datos"


def test_revision_is_append_only_and_time_bounded():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as db:
        earlier = datetime(2026, 9, 24, 10, tzinfo=UTC)
        later = datetime(2026, 9, 25, 10, tzinfo=UTC)
        old = [{"date": "2026-09-23", "value": "6.25"}]
        revised = [{"date": "2026-09-23", "value": "6.50"}]
        store_series(db, "mortgage_30y_us", old, earlier)
        before = build_snapshot(db, date(2026, 9, 24), earlier)
        old_id = before.metrics["mortgage_30y_us"]["evidence_id"]
        assert store_series(db, "mortgage_30y_us", revised, later)["revisions_applied"] == 1
        assert store_series(db, "mortgage_30y_us", revised, later)["revisions_applied"] == 0
        after = build_snapshot(db, date(2026, 9, 24), later)
        assert after.metrics["mortgage_30y_us"]["value"] == 6.5
        assert after.metrics["mortgage_30y_us"]["evidence_id"] != old_id
        assert before.metrics["mortgage_30y_us"]["value"] == 6.25
        assert build_snapshot(db, date(2026, 9, 24), earlier).id == before.id


def test_all_six_series_ingest_and_actor(monkeypatch):
    from app.services.market_observation_service import FRED_SERIES, refresh_fred
    from app.workers import dramatiq_app

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    seen = []

    class StubFRED:
        async def series_csv(self, series_id, limit=20):
            seen.append((series_id, limit))
            # Fecha dinamica: una fecha fija queda fuera de la tolerancia de
            # frescura de build_snapshot (max_age de cada serie) al avanzar el
            # calendario real y rompe el test con el tiempo.
            ayer = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
            return {"observations": [{"date": ayer, "value": "3.5"}]}

    async def stub_refresh(db):
        return await refresh_fred(db, StubFRED())

    monkeypatch.setattr("app.services.market_observation_service.refresh_fred", stub_refresh)
    monkeypatch.setattr("app.core.database.SessionLocal", factory)
    outcome = dramatiq_app.refresh_macro_context.fn()
    assert outcome["coverage"] == "ok"
    assert {series_id for series_id, _ in seen} == {row[0] for row in FRED_SERIES.values()}
    assert all(limit >= 252 for _, limit in seen)
    with factory() as db:
        assert db.query(MarketObservation).count() == 6


def test_market_migration_upgrade_and_downgrade():
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    from sqlalchemy import inspect

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0037_market_observations.py"
    spec = spec_from_file_location("market_migration_0037", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    scratch = create_engine("sqlite:///:memory:")
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    with scratch.begin() as conn:
        proxy = Operations(MigrationContext.configure(conn))
        original = migration.op
        migration.op = proxy
        try:
            migration.upgrade()
            assert "market_observations" in inspect(conn).get_table_names()
            assert "market_regime_snapshots" in inspect(conn).get_table_names()
            migration.downgrade()
            assert "market_observations" not in inspect(conn).get_table_names()
            assert "market_regime_snapshots" not in inspect(conn).get_table_names()
        finally:
            migration.op = original
