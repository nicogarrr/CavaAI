from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes.paper_trading import router
from app.core.database import Base, get_db
from app.models import Tenant
from app.models.paper_trading import PaperTrade
from app.schemas.paper_trading import PaperProposal
from app.services.paper_trading_service import (
    apply_quote,
    create_proposal,
    deadline,
    pnl,
    refresh_trades,
    scoreboard,
    trade_out,
)

NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)


def body(**kwargs):
    return {"proposal_key": "run-1-ASTS", "ticker": "ASTS", "direction": "long",
            "horizon": "short", "thesis": "Una tesis simulada con fuente y riesgos", "conviction": "0.8",
            "proposed_entry": "100", "stop": "90", "target": "120", "quantity": "2",
            "inference_basis": "Inferido a partir de los documentos oficiales", **kwargs}


def trade(**kwargs):
    return PaperTrade(**PaperProposal(**body()).model_dump(), author="LLM", inference_label="inferencia", status="pending", created_at=NOW-timedelta(seconds=1), **kwargs)


def quote(price=100, at=NOW, currency="USD"):
    return {"live_c": price, "live_t": at.timestamp(), "currency": currency}


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add_all([Tenant(id=1, external_id="paper-1"), Tenant(id=2, external_id="paper-2")])
        session.commit()
        session.info["tenant_id"] = 1
        yield session
    engine.dispose()


@pytest.mark.parametrize("override", [{"conviction": "nan"}, {"target": "Infinity"}, {"quantity": 0}, {"stop": 110}, {"direction": "invalid"}, {"author": "human"}, {"ticker": "../../x"}, {"horizon": "future"}])
def test_invalid_proposals(override):
    with pytest.raises(ValidationError):
        PaperProposal(**body(**override))


def test_real_fill_not_llm_entry_and_gap_stop():
    row = trade()
    assert apply_quote(row, quote(98), NOW)
    assert row.entry_price == Decimal(98)
    assert row.entry_price != row.proposed_entry
    assert row.entry_at == NOW
    later = NOW + timedelta(minutes=30)
    assert apply_quote(row, quote(85, later), later)
    assert row.exit_price == Decimal(85)  # not the ideal stop 90
    assert row.close_reason == "stop"
    assert pnl(row, row.exit_price) == Decimal(-26)
    assert not apply_quote(row, quote(130, later + timedelta(minutes=30)), later + timedelta(minutes=30))


@pytest.mark.parametrize("bad_quote", [{}, {"c": 100, "ct": NOW.timestamp()}, quote(0), quote(float("nan")), quote(at=NOW-timedelta(days=2)), quote(at=NOW+timedelta(seconds=1)), quote(currency=""), {"live_c": 100, "live_t": True, "currency": "USD"}])
def test_missing_stale_future_quote_does_not_fill(bad_quote):
    row = trade()
    assert not apply_quote(row, bad_quote, NOW)
    assert row.entry_price is None
    assert row.status == "pending"


@pytest.mark.parametrize("price", [105, 89, 125])
def test_limit_or_invalid_gap_not_filled(price):
    row = trade()
    assert not apply_quote(row, quote(price), NOW)


def test_short_pnl_and_target():
    row = PaperTrade(**PaperProposal(**body(direction="short", stop=110, target=80)).model_dump(), status="pending", created_at=NOW-timedelta(seconds=1))
    assert apply_quote(row, quote(102), NOW)
    later = NOW + timedelta(hours=1)
    assert apply_quote(row, quote(75, later), later)
    assert row.close_reason == "target"
    assert pnl(row, row.exit_price) == 54


def test_repeated_out_of_order_and_currency_change():
    row = trade()
    apply_quote(row, quote(), NOW)
    assert not apply_quote(row, quote(110), NOW)
    assert not apply_quote(row, quote(110, NOW-timedelta(minutes=1)), NOW)
    assert not apply_quote(row, quote(110, NOW+timedelta(minutes=1), "EUR"), NOW+timedelta(minutes=1))
    assert row.mark_price == 100


def test_stale_mark_not_reported_as_current():
    row = trade()
    apply_quote(row, quote(), NOW)
    out = trade_out(row, NOW+timedelta(days=2))
    assert out["mark_price"] is None
    assert out["unrealized_pnl"] is None
    assert out["quote_status"] == "sin_datos"


def test_time_horizon_and_leap_day():
    row = trade()
    apply_quote(row, quote(), NOW)
    later = NOW + timedelta(days=30)
    apply_quote(row, quote(110, later), later)
    assert row.close_reason == "horizon"
    row.horizon = "five_years"
    row.entry_at = datetime(2024, 2, 29, tzinfo=UTC)
    assert deadline(row) == datetime(2029, 2, 28, tzinfo=UTC)


def test_idempotence_conflict_and_tenant_isolation(db):
    proposal = PaperProposal(**body())
    row = create_proposal(db, proposal)
    assert row.author == "LLM" and row.inference_label == "inferencia"
    assert create_proposal(db, proposal).id == row.id
    with pytest.raises(ValueError):
        create_proposal(db, PaperProposal(**body(target=130)))
    db.info["tenant_id"] = 2
    assert db.scalar(select(PaperTrade).where(PaperTrade.id == row.id)) is None
    other = create_proposal(db, proposal)
    assert other.id != row.id
    assert other.tenant_id == 2


def test_worker_deduplicates_and_never_fabricates(db):
    create_proposal(db, PaperProposal(**body()))
    create_proposal(db, PaperProposal(**body(proposal_key="run-2-ASTS")))
    calls = []
    def fetch(ticker):
        calls.append(ticker)
        return {}
    result = refresh_trades(db, fetch)
    assert result["updated"] == 0
    assert calls == ["ASTS"]
    assert all(r.entry_price is None for r in db.scalars(select(PaperTrade)).all())


def test_score_separates_currency_horizon_and_empty_samples():
    assert scoreboard([])["groups"] == []
    rows = []
    for direction, currency, horizon, exit_price in [("long", "USD", "short", 110), ("long", "EUR", "short", 85), ("long", "USD", "five_years", 100)]:
        row = trade()
        row.direction, row.currency, row.horizon = direction, currency, horizon
        row.status, row.entry_price, row.exit_price = "closed", Decimal(100), Decimal(exit_price)
        rows.append(row)
    result = scoreboard(rows)
    assert len(result["groups"]) == 3
    assert {g["realized_pnl"] for g in result["groups"]} == {Decimal(20), Decimal(-30), Decimal(0)}
    assert sum(g["flat"] for g in result["groups"]) == 1


def test_rest_is_scoped_and_rejects_client_prices(db):
    app = FastAPI()
    app.include_router(router, prefix="/paper-trading")
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        response = client.post("/paper-trading/proposals", json=body())
        assert response.status_code == 201
        proposal_id = response.json()["id"]
        assert response.json()["entry_price"] is None
        assert "tenant_id" not in response.json()
        assert client.post("/paper-trading/proposals", json=body(entry_price=100)).status_code == 422
        assert len(client.get("/paper-trading/proposals").json()) == 1
        db.info["tenant_id"] = 2
        assert client.get("/paper-trading/proposals").json() == []
        assert client.get("/paper-trading/scoreboard").json()["groups"] == []
        # Avoid network call while testing a foreign id.
        from unittest.mock import patch

        import app.api.routes.paper_trading as routes
        with patch.object(routes, "refresh_trades"):
            assert client.post(f"/paper-trading/proposals/{proposal_id}/close").status_code == 404


def test_quote_at_proposal_time_is_not_forward():
    row = trade()
    row.created_at = NOW
    assert not apply_quote(row, quote(), NOW)


def test_conviction_bins_do_not_invent_samples():
    bins = scoreboard([])["conviction_bins"]
    assert all(b["hit_rate"] is None and b["closed"] == 0 for b in bins)
