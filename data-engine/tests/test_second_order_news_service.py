from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company, NewsEvent
from app.services import second_order_news_service as service


def test_second_order_is_read_only_and_marks_source_claim_unverified(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.info["tenant_id"] = "tenant-test"
        db.add_all([
            Company(ticker="GRID", name="Grid Co", exchange="NYSE", currency="USD",
                    sector="Electric Utilities", industry="Power", company_type="holding",
                    valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[]),
            Company(ticker="OIL", name="Oil Co", exchange="NYSE", currency="USD",
                    sector="Oil & Gas", industry="Energy", company_type="holding",
                    valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[]),
            Company(ticker="UNR", name="Unknown Co", exchange="NYSE", currency="USD",
                    sector="Unknown", industry="Unknown", company_type="holding",
                    valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[]),
            NewsEvent(title="Electric trucks require 350 TWh of electrification",
                      summary="A claim about electric trucks", source="GDELT", url="https://example.test/story",
                      date=datetime(2026, 9, 27, tzinfo=UTC),
                      metadata_={"date_source": "source"}),
        ])
        db.commit()
        monkeypatch.setattr(service, "_jev_marker", lambda theme: {
            "direction": None, "confidence": None, "backend": None,
        })
        event = db.query(NewsEvent).one()
        result = service.analyze_second_order(db, event)
        assert result["status"] == "hipótesis_no_verificadas"
        assert result["source_verified"] is False
        assert "350 TWh" in result["source_claim"]
        assert result["source"]["published_at"] is not None
        assert {item["ticker"] for item in result["candidates"]} == {"GRID", "OIL"}
        assert all(item["status"] == "hipótesis_no_verificada" for item in result["candidates"])
        assert all(item["sources"][0]["url"] == "https://example.test/story" for item in result["candidates"])
        assert not db.dirty and not db.new


def test_unknown_or_unsourced_news_stays_without_candidates(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.info["tenant_id"] = "tenant-test"
        event = NewsEvent(title="Nothing relevant", summary="Generic update", source="manual",
                          metadata_={"date_source": "ingested_at_fallback"})
        db.add(event)
        db.commit()
        monkeypatch.setenv("SECOND_ORDER_LLM_ENABLED", "0")
        result = service.analyze_second_order(db, event, use_llm=True)
        assert result["status"] == "sin_datos"
        assert result["candidates"] == []
        assert result["source"]["published_at"] is None
        assert result["mode"] == "determinista"
        assert "desactivado" in result["note"]


def test_jev_absent_never_calls_old_ungated_client(monkeypatch):
    monkeypatch.setattr(service, "_normalized", lambda text: text.lower())
    marker = service._jev_marker(service.Theme(exposure="Power", direction="incierta", chain=[
        service.CausalStep(cause="A", effect="B")]))
    assert marker["direction"] is None


def test_llm_quota_is_tenant_scoped_and_reports_limit(monkeypatch):
    from types import SimpleNamespace

    from app.services import second_order_quota as quota

    monkeypatch.setattr(quota, "_LOCAL", {})
    config = SimpleNamespace(is_production=False, second_order_llm_calls_per_minute=2,
                             second_order_llm_calls_per_day=3)
    assert quota.reserve_llm_call("tenant-one", config)["allowed"] is True
    assert quota.reserve_llm_call("tenant-one", config)["minute_used"] == 2
    exceeded = quota.reserve_llm_call("tenant-one", config)
    assert exceeded["allowed"] is False
    assert exceeded["minute_used"] == 2
    assert quota.reserve_llm_call("tenant-two", config)["allowed"] is True
    from pytest import raises
    with raises(RuntimeError, match="verified tenant"):
        quota.reserve_llm_call(None, config)


def test_llm_cap_falls_back_honestly_without_call(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.info["tenant_id"] = "tenant-test"
        event = NewsEvent(title="Electric trucks", summary="Electrification", source="manual",
                          metadata_={"date_source": "source"})
        db.add(event)
        db.commit()
        monkeypatch.setenv("SECOND_ORDER_LLM_ENABLED", "1")
        monkeypatch.setattr(service, "reserve_llm_call", lambda *_args: {
            "allowed": False, "minute_used": 4, "minute_limit": 4,
            "day_used": 4, "day_limit": 100,
        })
        monkeypatch.setattr(service, "_extract_with_llm", lambda text: (_ for _ in ()).throw(
            AssertionError("LLM must not be called")))
        result = service.analyze_second_order(db, event, use_llm=True)
        assert result["mode"] == "determinista"
        assert "tope alcanzado" in result["note"]
        assert result["llm_quota"]["minute_used"] == 4


def test_candidate_query_prefilters_universe(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.info["tenant_id"] = "tenant-test"
        db.add_all([
            Company(ticker="COP", name="Copper Co", exchange="NYSE", currency="USD",
                    sector="Unknown", industry="Unknown", company_type="holding",
                    valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=["Copper"]),
            Company(ticker="XYZ", name="Other Co", exchange="NYSE", currency="USD",
                    sector="Energy", industry="Oil", company_type="holding",
                    valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[]),
        ])
        db.commit()
        matches = service._matching_companies(db, "copper")
        assert [company.ticker for company in matches] == ["COP"]


def test_llm_request_pins_free_model_even_with_paid_override(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    captured = []

    class Provider:
        name = "opencode-go"
        model_router = SimpleNamespace(resolve=lambda request: request.model)

        async def complete(self, request):
            captured.append(request)
            return SimpleNamespace(text='{"themes": []}')

    monkeypatch.setattr(service, "create_llm_provider", lambda: Provider())
    result, _ = asyncio.run(service._extract_with_llm("Una noticia general"))
    assert result.themes == []
    assert captured[0].model == "space-bunny-free"
