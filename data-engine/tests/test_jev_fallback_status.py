"""Estados y clasificaciones herméticos, sin peticiones externas."""
import asyncio

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.llm.jev import JevCreditExhausted, JevDecisionClient
from app.models import ResearchAlert, Tenant
from app.services import jev_availability, jev_gates


def test_billing_402_no_retry():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(402, json={"error": "credit exhausted"})
    client = JevDecisionClient("fake", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        asyncio.run(client.classify("x", "q", "?", {"yes": "yes", "no": "no"}))
        assert False, "Debe detectar falta de crédito"
    except JevCreditExhausted:
        assert len(calls) == 1


def test_transition_persists_once_and_alerts_once(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Tenant(external_id="t", name="Test", status="active"))
        db.commit()
    from sqlalchemy.orm import sessionmaker
    monkeypatch.setattr(jev_availability, "SessionLocal", sessionmaker(engine))
    jev_availability.mark_credit_exhausted()
    jev_availability.mark_credit_exhausted()
    with Session(engine) as db:
        assert len(db.scalars(select(ResearchAlert).where(ResearchAlert.alert_type == "typesafe_credit_exhausted")).all()) == 1
    assert jev_availability.credit_status()["last_billing_failure_at"]


def test_fallback_only_marks_tier_one(monkeypatch):
    monkeypatch.setattr(jev_gates, "credit_status", lambda: {"status": "fallback_modelo_gratuito"})
    class Decision:
        label = "observed"
        confidence = .91
        backend = "jev_fallback_free"
    async def free(*args, **kwargs):
        return Decision()
    monkeypatch.setattr(jev_gates, "classify_free", free)
    assert asyncio.run(jev_gates.jev_choice_or_none(name="claim_routing", text="x", instructions="?", criteria={"observed": "x"})) is None
    mark = jev_gates.mark_only("copilot_ticket", "x", "?", {"observed": "x"})
    assert mark["backend"] == "jev_fallback_free"
