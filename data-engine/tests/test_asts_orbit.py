"""SMA math, conservative signal, dedupe, tenancy and stale fail-closed."""
from datetime import UTC, datetime, timedelta
from math import pi

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Tenant
from app.services.asts_catalog_service import persist_catalog, read_orbit_history, read_orbit_overview
from app.services.asts_orbit_service import append_history, orbit_signal, sma_km
from app.services.connectors.celestrak_ast import normalize_catalog

NOW = datetime(2026, 9, 27, 17, 30, tzinfo=UTC)


def sample():
    return {
        "OBJECT_NAME": "BLUEWALKER-3", "OBJECT_ID": "2022-111AL", "NORAD_CAT_ID": 53807,
        "EPOCH": "2026-09-26T13:30:44.947008", "MEAN_MOTION": 15.39369987,
        "ECCENTRICITY": 0.00068366, "INCLINATION": 53.2276,
        "RA_OF_ASC_NODE": 277.6287, "ARG_OF_PERICENTER": 121.8551,
        "MEAN_ANOMALY": 238.3121, "BSTAR": 0.0001762875,
        "MEAN_MOTION_DOT": 6.602e-5, "MEAN_MOTION_DDOT": 0,
    }


def test_sma_known_circular_geostationary_mean_motion():
    n = 86400 / (2 * pi * (42164 ** 3 / 398600.4418) ** .5)
    assert abs(sma_km(n) - 42164) < .01
    assert 6700 < sma_km(15.4) < 7000


def test_drop_requires_three_separated_epochs_and_is_not_telemetry():
    start = datetime(2026, 9, 24, tzinfo=UTC)
    catalog = []
    history = None
    for hours, motion in [(0, 15.39), (12, 15.392), (30, 15.41)]:
        catalog = [{"norad_cat_id": 53807, "epoch": (start + timedelta(hours=hours)).isoformat(),
                    "mean_motion": motion, "bstar": 0.001, "mean_motion_dot": 0.01}]
        history = append_history(history, catalog)
    assert len(history["53807"]) == 3
    signal = orbit_signal(history["53807"])
    assert signal["delta_sma_km"] < -2
    assert signal["status"] == "firma compatible con variación orbital; revisar fuentes"
    assert len(append_history(history, catalog)["53807"]) == 3
    assert orbit_signal(history["53807"][:2])["delta_sma_km"] is None


def test_no_false_trend_from_identical_epoch_or_long_gap():
    start = datetime(2026, 9, 20, tzinfo=UTC)
    history = [{"epoch": (start + timedelta(hours=h)).isoformat(), "sma_km": sma}
               for h, sma in [(0, 6900), (12, 6890), (240, 6800)]]
    assert orbit_signal(history)["delta_sma_km"] is None


def test_history_is_tenant_scoped_and_fails_closed_when_stale():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as db:
        db.add_all([Tenant(id=1, external_id="orbit-one"), Tenant(id=2, external_id="orbit-two")])
        db.commit()
    with factory() as db:
        db.info["tenant_id"] = 1
        for hours, motion in [(0, 15.39), (12, 15.392), (30, 15.41)]:
            fetched = NOW + timedelta(hours=hours)
            data = dict(sample(), EPOCH=(fetched - timedelta(hours=1)).isoformat(), MEAN_MOTION=motion)
            persist_catalog(db, normalize_catalog([data], fetched_at=fetched), fetched)
        now = NOW + timedelta(hours=30)
        data = read_orbit_overview(db, as_of=now)
        assert data["status"] == "disponible"
        assert len(data["objects"][0]["history"]) == 3
        assert read_orbit_history(db, 53807, as_of=now)["signal"]["delta_sma_km"] < -2
        assert read_orbit_overview(db, as_of=now + timedelta(hours=31))["objects"] == []
    with factory() as db:
        db.info["tenant_id"] = 2
        assert read_orbit_overview(db, as_of=now)["objects"] == []
