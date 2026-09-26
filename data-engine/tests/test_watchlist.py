import time
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

import main
from app.core import auth as auth_module
from app.core.database import SessionLocal, init_db
from app.models import Tenant, WatchItem
from app.seed import seed

from tests.auth_helpers import auth_settings, signed_request


def _cleanup(watch_symbols: list[str], tenant_external_ids: list[str] | None = None) -> None:
    db = SessionLocal()
    try:
        items = db.scalars(
            select(WatchItem).where(WatchItem.symbol.in_(watch_symbols))
        ).all()
        for item in items:
            db.delete(item)
        if tenant_external_ids:
            tenant_ids = db.scalars(
                select(Tenant.id).where(Tenant.external_id.in_(tenant_external_ids))
            ).all()
            if tenant_ids:
                db.execute(delete(WatchItem).where(WatchItem.tenant_id.in_(tenant_ids)))
                db.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
        db.commit()
    finally:
        db.close()


def test_watchlist_crud_and_deduplication():
    init_db()
    symbols = ["MSFT", "AAPL", "WLTEST", "WLTEST2"]
    _cleanup(symbols)
    client = TestClient(main.app)

    created = client.post(
        "/api/watchlist", json={"symbol": "msft", "company": "Microsoft"}
    )
    assert created.status_code == 201
    assert created.json()["symbol"] == "MSFT"
    assert created.json()["company"] == "Microsoft"
    first_id = created.json()["id"]

    # Dedup: same symbol upserts instead of duplicating.
    duplicated = client.post(
        "/api/watchlist", json={"symbol": "MSFT", "company": "Microsoft Corp."}
    )
    assert duplicated.status_code == 201
    assert duplicated.json()["id"] == first_id
    assert duplicated.json()["company"] == "Microsoft Corp."

    client.post("/api/watchlist", json={"symbol": "aapl"})
    time.sleep(0.02)  # ensure created_at ordering is stable at second granularity
    client.post("/api/watchlist", json={"symbol": "WLTEST2"})

    listed = client.get("/api/watchlist")
    assert listed.status_code == 200
    items = {item["symbol"]: item for item in listed.json()}
    assert {"MSFT", "AAPL", "WLTEST2"} <= set(items)
    assert items["AAPL"]["company"] is None
    # Most recently added first.
    assert listed.json()[0]["symbol"] == "WLTEST2"

    with SessionLocal() as db:
        count = len(
            db.scalars(
                select(WatchItem).where(WatchItem.symbol == "MSFT")
            ).all()
        )
        assert count == 1

    deleted = client.delete("/api/watchlist/msft")
    assert deleted.status_code == 204
    remaining = {item["symbol"] for item in client.get("/api/watchlist").json()}
    assert "MSFT" not in remaining

    missing = client.delete("/api/watchlist/MSFT")
    assert missing.status_code == 404

    invalid = client.post("/api/watchlist", json={"symbol": "bad symbol!"})
    assert invalid.status_code == 422

    _cleanup(symbols)


def test_watchlist_is_isolated_per_tenant(monkeypatch):
    init_db()
    seed()
    secret = "watchlist-test-secret-with-at-least-32-characters"
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: auth_settings(strict=True, secret=secret, app_env="local"),
    )
    suffix = uuid4().hex[:8]
    tenant_a = f"watch-a-{suffix}"
    tenant_b = f"watch-b-{suffix}"
    client = TestClient(main.app)

    try:
        unauthorized = client.get("/api/watchlist")
        assert unauthorized.status_code == 401

        created_a = signed_request(
            client, secret, tenant_a, f"user-a-{suffix}", "POST", "/api/watchlist",
            json_body={"symbol": "TENA"},
        )
        created_b = signed_request(
            client, secret, tenant_b, f"user-b-{suffix}", "POST", "/api/watchlist",
            json_body={"symbol": "TENB"},
        )
        assert created_a.status_code == 201
        assert created_b.status_code == 201

        list_a = signed_request(
            client, secret, tenant_a, f"user-a-{suffix}", "GET", "/api/watchlist"
        ).json()
        list_b = signed_request(
            client, secret, tenant_b, f"user-b-{suffix}", "GET", "/api/watchlist"
        ).json()
        assert {item["symbol"] for item in list_a} == {"TENA"}
        assert {item["symbol"] for item in list_b} == {"TENB"}

        cross_delete = signed_request(
            client, secret, tenant_b, f"user-b-{suffix}", "DELETE", "/api/watchlist/TENA"
        )
        assert cross_delete.status_code == 404

        own_delete = signed_request(
            client, secret, tenant_a, f"user-a-{suffix}", "DELETE", "/api/watchlist/TENA"
        )
        assert own_delete.status_code == 204
    finally:
        _cleanup(["TENA", "TENB"], [tenant_a, tenant_b])