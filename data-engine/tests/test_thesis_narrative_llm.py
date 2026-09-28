"""Capa 2 de la tesis: narrativa LLM verificada, fail-closed sobre la capa 1."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company
from app.services import thesis_narrative_llm as narrative


def _company() -> Company:
    return Company(
        ticker="META", name="Meta Platforms", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Internet", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )


HYPOTHESIS = (
    "Meta cotiza a 336.56 USD, un 68% por encima del escenario base (106.85 USD). "
    "El mercado descuenta un crecimiento de ingresos del 35% anual."
)
NEWS = [
    {"source_headline": "Meta presenta Muse, su nuevo modelo", "title": "resumen interno",
     "source": "TechCrunch", "date": "2026-09-25", "date_source": "source"},
]
VALUATION = {
    "status": "ok", "current_price": 336.56, "base_value": 106.85,
    "margin_of_safety": -0.68, "missing_inputs": [],
    "reverse_dcf": {"required_revenue_growth": 0.35},
}
GOOD_SUMMARY = (
    'Meta cotiza a 336.56 USD, un 68% por encima de su escenario base de 106.85 USD, '
    'lo que implica que el mercado ya descuenta un crecimiento de ingresos del 35% anual. '
    'En este contexto, TechCrunch publicó el 2026-09-25 "Meta presenta Muse, su nuevo modelo", '
    'un titular que acredita la noticia, no su impacto en valor.'
)


class _FakeUsage:
    input_tokens = 100
    output_tokens = 80
    total_tokens = 180


class _FakeResponse:
    model = "test-model"
    usage = _FakeUsage()

    def __init__(self, text: str):
        self.text = text


class _FakeProvider:
    name = "fake"

    def __init__(self, summary: str | None = None, raises: bool = False):
        self._summary = summary
        self._raises = raises
        self.calls = 0

    async def complete(self, request):
        self.calls += 1
        if self._raises:
            raise RuntimeError("provider down")
        return _FakeResponse(json.dumps({"summary": self._summary}, ensure_ascii=False))


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def test_flag_off_returns_baseline(db, monkeypatch):
    monkeypatch.delenv("THESIS_NARRATIVE_LLM_ENABLED", raising=False)
    provider = _FakeProvider(GOOD_SUMMARY)
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base", provider=provider)
    assert result == "base"
    assert provider.calls == 0


def test_provider_disabled_returns_baseline(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    disabled = SimpleNamespace(name="disabled")
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base", provider=disabled)
    assert result == "base"


def test_verified_narrative_is_used(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(GOOD_SUMMARY))
    assert result == GOOD_SUMMARY


def test_hallucinated_number_falls_back(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    bad = GOOD_SUMMARY.replace("336.56 USD", "999.99 USD")
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(bad))
    assert result == "base"


def test_misquoted_headline_falls_back(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    bad = GOOD_SUMMARY.replace(
        '"Meta presenta Muse, su nuevo modelo"', '"Meta lanza Muse al mercado"')
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(bad))
    assert result == "base"


def test_advice_language_falls_back(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    bad = GOOD_SUMMARY + " Recomendamos comprar."
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(bad))
    assert result == "base"


def test_provider_error_falls_back(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(raises=True))
    assert result == "base"


def test_invalid_json_falls_back(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")

    class _BadJsonProvider(_FakeProvider):
        async def complete(self, request):
            return _FakeResponse("no es json")

    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_BadJsonProvider())
    assert result == "base"


def test_short_or_empty_summary_falls_back(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider("corto"))
    assert result == "base"
