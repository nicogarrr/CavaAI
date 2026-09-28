"""SupGP is a separately attributed supplemental orbital fit, never GP telemetry."""
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Tenant
from app.services.asts_catalog_service import persist_catalog, read_orbit_overview
from app.services.connectors.celestrak_ast import normalize_catalog
from app.services.connectors.celestrak_ast_supgp import SUPGP_URL, fetch_supgp, normalize_supgp

NOW = datetime(2026, 9, 28, 14, tzinfo=UTC)


def gp_row(**overrides):
    return {
        "OBJECT_NAME": "SPACEMOBILE-011", "OBJECT_ID": "2026-179C", "NORAD_CAT_ID": 100242,
        "EPOCH": (NOW - timedelta(hours=2)).replace(tzinfo=None).isoformat(),
        "MEAN_MOTION": 15.13, "ECCENTRICITY": .0007, "INCLINATION": 52.99,
        "RA_OF_ASC_NODE": 82.56, "ARG_OF_PERICENTER": 134.91, "MEAN_ANOMALY": 257.9,
        "BSTAR": .00016, "MEAN_MOTION_DOT": .00003, "MEAN_MOTION_DDOT": 0,
        **overrides,
    }


def test_supgp_identity_and_provenance_are_fail_closed():
    gp = normalize_catalog([gp_row()], fetched_at=NOW)
    sup = gp_row(CLASSIFICATION_TYPE="C", DATA_SOURCE="AST-E", MEAN_MOTION=15.14)
    assert normalize_supgp([sup], fetched_at=NOW, gp_catalog=gp)[0]["norad_cat_id"] == 100242
    assert normalize_supgp([dict(sup, NORAD_CAT_ID=1)], fetched_at=NOW, gp_catalog=gp)[0]["norad_cat_id"] == 1
    for changed in [dict(sup, CLASSIFICATION_TYPE="U"), dict(sup, DATA_SOURCE="other"),
                    dict(sup, OBJECT_ID="wrong")]:
        with pytest.raises(ValueError):
            normalize_supgp([changed], fetched_at=NOW, gp_catalog=gp)


@pytest.mark.anyio
async def test_supgp_fetch_uses_only_ast_endpoint_and_raises_403():
    gp = normalize_catalog([gp_row()], fetched_at=NOW)
    async def handler(request):
        assert str(request.url) == SUPGP_URL
        return httpx.Response(403)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_supgp(gp, client, fetched_at=NOW)


def test_supgp_history_is_independent_and_older_snapshot_expires():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as db:
        db.add(Tenant(id=1, external_id="supgp-test")); db.commit()
        db.info["tenant_id"] = 1
        gp = normalize_catalog([gp_row()], fetched_at=NOW)
        sup = normalize_supgp([gp_row(CLASSIFICATION_TYPE="C", DATA_SOURCE="AST-E", MEAN_MOTION=15.14)], fetched_at=NOW, gp_catalog=gp)
        persist_catalog(db, gp, NOW, supgp=sup)
        view = read_orbit_overview(db, as_of=NOW)
        assert view["objects"][0]["history"][0]["sma_km"] != view["supgp"]["objects"][0]["history"][0]["sma_km"]
        assert view["supgp"]["source_url"] == SUPGP_URL
        persist_catalog(db, gp, NOW + timedelta(hours=29), supgp=None)
        assert read_orbit_overview(db, as_of=NOW + timedelta(hours=31))["supgp"]["status"] == "sin datos"
        assert read_orbit_overview(db, as_of=NOW + timedelta(hours=31))["objects"]
        persist_catalog(db, [], NOW + timedelta(hours=61), supgp=sup)
        independent = read_orbit_overview(db, as_of=NOW + timedelta(hours=61))
        assert independent["supgp"]["status"] == "disponible"
        assert independent["status"] == "sin datos"
    with factory() as other:
        other.info["tenant_id"] = 2
        assert read_orbit_overview(other, as_of=NOW)["objects"] == []


def test_supgp_history_bounded_and_source_failure_does_not_retimestamp():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as db:
        db.add(Tenant(id=1, external_id="bounded")); db.commit(); db.info["tenant_id"] = 1
        for hour in range(40):
            stamp = NOW + timedelta(hours=hour * 2)
            row = gp_row(EPOCH=(stamp - timedelta(hours=1)).replace(tzinfo=None).isoformat())
            gp = normalize_catalog([row], fetched_at=stamp)
            sup = normalize_supgp([dict(row, CLASSIFICATION_TYPE="C", DATA_SOURCE="AST-E")], fetched_at=stamp, gp_catalog=gp)
            persist_catalog(db, gp, stamp, supgp=sup)
        view = read_orbit_overview(db, as_of=stamp)
        assert len(view["objects"][0]["history"]) == 32
        assert len(view["supgp"]["objects"][0]["history"]) == 32
        last_supgp = view["supgp"]["fetched_at"]
        persist_catalog(db, gp, stamp + timedelta(hours=2), supgp=None)
        assert read_orbit_overview(db, as_of=stamp + timedelta(hours=2))["supgp"]["fetched_at"] == last_supgp


def test_failed_fetch_attempt_is_persisted_for_two_hour_guard():
    from app.services.asts_catalog_service import latest_download_at, record_download_attempt
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as db:
        db.add(Tenant(id=1, external_id="attempt")); db.commit(); db.info["tenant_id"] = 1
        assert latest_download_at(db) is None
        record_download_attempt(db, NOW)
        assert latest_download_at(db).replace(tzinfo=UTC) == NOW
        assert read_orbit_overview(db, as_of=NOW)["status"] == "sin datos"


def test_actor_skips_network_within_two_hours(monkeypatch):
    from app.services.asts_catalog_service import record_download_attempt
    from app.workers import dramatiq_app
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as db:
        db.add(Tenant(id=1, external_id="worker")); db.commit(); db.info["tenant_id"] = 1
        record_download_attempt(db, datetime.now(UTC))
    def open_db(*_args):
        db = sessionmaker(engine)()
        db.info["tenant_id"] = 1
        return db
    monkeypatch.setattr(dramatiq_app, "tenant_contexts", lambda: [(1, "user")])
    monkeypatch.setattr(dramatiq_app, "_session", open_db)
    monkeypatch.setattr(dramatiq_app, "_run", lambda *_args: pytest.fail("network must not run"))
    result = dramatiq_app.refresh_asts_catalog.fn()
    assert result["reason"] == "celestrak_2h_minimum"


def test_actor_fetches_sources_independently_after_failed_gp(monkeypatch):
    from app.services.asts_catalog_service import read_orbit_overview as read
    from app.workers import dramatiq_app
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as db:
        db.add(Tenant(id=1, external_id="partial")); db.commit()
    def open_db(*_args):
        db = sessionmaker(engine)(); db.info["tenant_id"] = 1
        return db
    monkeypatch.setattr(dramatiq_app, "tenant_contexts", lambda: [(1, "user")])
    monkeypatch.setattr(dramatiq_app, "_session", open_db)
    monkeypatch.setattr(dramatiq_app, "acquire_job_lease", lambda *a, **kw: "token")
    monkeypatch.setattr(dramatiq_app, "_lease_redis_url", lambda: None)
    monkeypatch.setattr(dramatiq_app, "_run", lambda coroutine: __import__('asyncio').run(coroutine))
    from app.services.connectors import celestrak_ast, celestrak_ast_supgp
    async def failed_gp(**_kw):
        raise RuntimeError("GP down")
    async def good_supgp(gp_catalog, *, fetched_at):
        assert gp_catalog is None
        return normalize_supgp([gp_row(EPOCH=(fetched_at - timedelta(hours=2)).replace(tzinfo=None).isoformat(),
                                        CLASSIFICATION_TYPE="C", DATA_SOURCE="AST-E")], fetched_at=fetched_at)
    monkeypatch.setattr(celestrak_ast, "fetch_catalog", failed_gp)
    monkeypatch.setattr(celestrak_ast_supgp, "fetch_supgp", good_supgp)
    result = dramatiq_app.refresh_asts_catalog.fn()
    assert result["status"] == "partial" and result["gp_error"] == "RuntimeError"
    with open_db() as db:
        result = read(db)
        assert result["status"] == "sin datos"
        assert result["supgp"]["status"] == "disponible"
        assert result["supgp"]["objects"][0]["object_name"] == "SPACEMOBILE-011"
