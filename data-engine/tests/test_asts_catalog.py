"""AST GP catalog contract, fail-closed ingestion and tenant isolation."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Tenant
from app.services.asts_catalog_service import persist_catalog, read_catalog
from app.services.connectors.celestrak_ast import SOURCE_URL, fetch_catalog, normalize_catalog

NOW = datetime(2026, 9, 27, 17, 30, tzinfo=UTC)


def sample(cat_id=53807, name="BLUEWALKER-3"):
    return {
        "OBJECT_NAME": name, "OBJECT_ID": "2022-111AL", "NORAD_CAT_ID": cat_id,
        "EPOCH": "2026-09-26T13:30:44.947008", "MEAN_MOTION": 15.39369987,
        "ECCENTRICITY": 0.00068366, "INCLINATION": 53.2276,
        "RA_OF_ASC_NODE": 277.6287, "ARG_OF_PERICENTER": 121.8551,
        "MEAN_ANOMALY": 238.3121, "BSTAR": 0.0001762875,
        "MEAN_MOTION_DOT": 6.602e-5, "MEAN_MOTION_DDOT": 0,
    }


def test_normalize_preserves_official_names_and_id():
    catalog = normalize_catalog([sample(61045, "SPACEMOBILE-003"), sample()], fetched_at=NOW)
    assert [s["norad_cat_id"] for s in catalog] == [53807, 61045]
    assert catalog[1]["object_name"] == "SPACEMOBILE-003"
    assert catalog[0]["epoch"].endswith("+00:00")
    assert catalog[0]["bstar"] == sample()["BSTAR"]


@pytest.mark.parametrize("payload", [[], [sample(), sample()], [dict(sample(), NORAD_CAT_ID="53807")],
                                     [dict(sample(), MEAN_MOTION=float("nan"))],
                                     [dict(sample(), OBJECT_NAME="BLUEBIRD-3")],
                                     [dict(sample(), EPOCH="2026-10-26T13:30:44")],
                                     [dict(sample(), ECCENTRICITY=1.5)]])
def test_bad_catalog_fails_whole_batch(payload):
    with pytest.raises(ValueError):
        normalize_catalog(payload, fetched_at=NOW)


@pytest.mark.anyio
async def test_fetch_uses_only_official_endpoint():
    async def handler(request):
        assert str(request.url) == SOURCE_URL
        return httpx.Response(200, json=[sample()])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        catalog = await fetch_catalog(client, fetched_at=NOW)
    assert len(catalog) == 1



def test_tenant_scoped_snapshot_and_stale_fail_closed():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as db:
        db.add_all([Tenant(id=1, external_id="one"), Tenant(id=2, external_id="two")])
        db.commit()
    with factory() as one:
        one.info["tenant_id"] = 1
        assert read_catalog(one, as_of=NOW)["status"] == "sin datos"
        catalog = normalize_catalog([sample()], fetched_at=NOW)
        assert persist_catalog(one, catalog, NOW) == 1
        assert persist_catalog(one, catalog, NOW) == 1
        data = read_catalog(one, as_of=NOW)
        assert data["count"] == 1
        # frescura = instante de descarga, no el EPOCH orbital de cada objeto
        assert data["freshness_basis"] == "download_time"
        assert "no para posiciones actuales" in data["usage_note"]
        old_epoch = normalize_catalog([dict(sample(), EPOCH="2026-08-28T13:30:44.947008")], fetched_at=NOW)
        assert persist_catalog(one, old_epoch, NOW) == 1
        assert read_catalog(one, as_of=NOW)["status"] == "disponible"
        later = read_catalog(one, as_of=NOW + timedelta(hours=31))
        assert later["status"] == "sin datos" and later["satellites"] == []
    with factory() as two:
        two.info["tenant_id"] = 2
        assert read_catalog(two, as_of=NOW)["count"] == 0
    with factory() as no_tenant:
        with pytest.raises(ValueError, match="Tenant"):
            read_catalog(no_tenant, as_of=NOW)
