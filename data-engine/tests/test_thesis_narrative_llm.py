"""Capa 2 de la tesis: narrativa por seleccion de plantillas, correcta por construccion."""

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


HYPOTHESIS = "hipotesis determinista"
NEWS = [
    {"source_headline": "Meta presenta Muse, su nuevo modelo", "title": "resumen interno",
     "source": "TechCrunch", "date": "2026-09-25T10:00:00", "date_source": "source"},
]
VALUATION = {
    "status": "ok", "current_price": 336.56, "base_value": 106.85,
    "margin_of_safety": -0.68, "missing_inputs": [],
    "reverse_dcf": {"required_revenue_growth": 0.35},
}
FRAGMENTS = narrative._fragment_templates(_company(), VALUATION, NEWS)


class _FakeUsage:
    input_tokens = 100
    output_tokens = 40
    total_tokens = 140


class _FakeResponse:
    model = "test-model"
    usage = _FakeUsage()

    def __init__(self, text: str):
        self.text = text


class _FakeProvider:
    name = "fake"

    def __init__(self, fragment_ids=None, raw_text: str | None = None, raises: bool = False):
        self._ids = fragment_ids
        self._raw = raw_text
        self._raises = raises
        self.calls = 0

    async def complete(self, request):
        self.calls += 1
        if self._raises:
            raise RuntimeError("provider down")
        if self._raw is not None:
            return _FakeResponse(self._raw)
        return _FakeResponse(json.dumps({"fragment_ids": self._ids}))


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _spy_budget(monkeypatch):
    calls = []

    class _SpyBudget:
        def can_spend(self, db, amount):
            return True

        def record(self, db, model, workflow, cost, tokens, *, commit=True):
            calls.append({"workflow": workflow, "commit": commit})

        @staticmethod
        def estimate_cost_eur(model, input_tokens, output_tokens):
            return 0.01

    monkeypatch.setattr(narrative, "BudgetController", _SpyBudget)
    return calls


def test_templates_are_correct_by_construction():
    # MoS = base/price - 1: se nombra explicitamente, sin distancia
    # precio/base (que usaria el denominador equivocado: 215%, no 68%).
    assert FRAGMENTS["valoracion_posicion"] == (
        "Meta Platforms cotiza a 336.56 USD frente a un escenario base de "
        "106.85 USD (margen de seguridad del -68%)."
    )
    assert FRAGMENTS["expectativas_mercado"] == (
        "El mercado descuenta un crecimiento de ingresos del 35.0% anual."
    )
    assert FRAGMENTS["titular_0"] == (
        'TechCrunch publico el 2026-09-25 "Meta presenta Muse, su nuevo modelo".'
    )
    assert "caveat_titulares" in FRAGMENTS
    assert "caveat_parcial" not in FRAGMENTS
    assert "caveat_insufficient" not in FRAGMENTS


def test_flag_off_returns_baseline(db, monkeypatch):
    monkeypatch.delenv("THESIS_NARRATIVE_LLM_ENABLED", raising=False)
    provider = _FakeProvider(list(FRAGMENTS))
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base", provider=provider)
    assert result == "base"
    assert provider.calls == 0


def test_provider_disabled_returns_baseline(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=SimpleNamespace(name="disabled"))
    assert result == "base"


def test_valid_selection_composes_narrative(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    order = ["valoracion_posicion", "expectativas_mercado", "titular_0", "caveat_titulares"]
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(order))
    assert result == " ".join(FRAGMENTS[fid] for fid in order)
    assert result.startswith("Meta Platforms cotiza a 336.56 USD")


def test_selection_with_unknown_id_falls_back(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(["valoracion_posicion", "inventado"]))
    assert result == "base"


def test_selection_with_duplicates_falls_back(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(["valoracion_posicion", "valoracion_posicion"]))
    assert result == "base"


def test_titular_without_caveat_falls_back(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(["valoracion_posicion", "titular_0"]))
    assert result == "base"


def test_caveat_without_titular_falls_back(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(["valoracion_posicion", "caveat_titulares"]))
    assert result == "base"


def test_partial_requires_caveat_fragment(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    valuation = dict(VALUATION, status="partial", missing_inputs=["beta"])
    frags = narrative._fragment_templates(_company(), valuation, NEWS)
    assert "caveat_parcial" in frags
    # Sin el fragmento obligatorio de parcialidad: capa 1.
    result = narrative.maybe_narrative(
        db, _company(), valuation, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(["valoracion_posicion"]))
    assert result == "base"
    order = ["valoracion_posicion", "caveat_parcial", "titular_0", "caveat_titulares"]
    result = narrative.maybe_narrative(
        db, _company(), valuation, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(order))
    assert "parcial-indicativa" in result
    assert "beta" in result


def test_insufficient_data_only_offers_caveat(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    valuation = {"status": "insufficient_data", "missing_inputs": ["revenue"],
                 "current_price": None, "base_value": None, "margin_of_safety": None}
    frags = narrative._fragment_templates(_company(), valuation, [])
    assert list(frags) == ["caveat_insufficient"]
    assert "revenue" in frags["caveat_insufficient"]
    result = narrative.maybe_narrative(
        db, _company(), valuation, HYPOTHESIS, [], "base",
        provider=_FakeProvider(["caveat_insufficient"]))
    assert result == frags["caveat_insufficient"]
    # El modelo no puede "olvidar" la salvedad: sin ella no hay seleccion valida.
    result = narrative.maybe_narrative(
        db, _company(), valuation, HYPOTHESIS, [], "base",
        provider=_FakeProvider([]))
    assert result == "base"


def test_provider_error_falls_back(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(raises=True))
    assert result == "base"


def test_invalid_json_falls_back(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(raw_text="no es json"))
    assert result == "base"


def test_budget_recorded_even_when_selection_discarded(db, monkeypatch):
    # La llamada consumio tokens: se cobra con commit=False aunque la
    # seleccion se descarte; aceptar/rechazar solo decide que se persiste.
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    calls = _spy_budget(monkeypatch)
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(["inventado"]))
    assert result == "base"
    assert calls == [{"workflow": "thesis_narrative", "commit": False}]


def test_valuation_core_is_mandatory(db, monkeypatch):
    # Sin el nucleo de valoracion (precio/base/MoS), la seleccion no puede
    # sustituir el executive_summary: noticias o expectativas no bastan.
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    for ids in (["titular_0", "caveat_titulares"], ["expectativas_mercado"]):
        result = narrative.maybe_narrative(
            db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
            provider=_FakeProvider(ids))
        assert result == "base"


def test_caveat_titulares_must_come_after_headlines(db, monkeypatch):
    monkeypatch.setenv("THESIS_NARRATIVE_LLM_ENABLED", "1")
    result = narrative.maybe_narrative(
        db, _company(), VALUATION, HYPOTHESIS, NEWS, "base",
        provider=_FakeProvider(
            ["valoracion_posicion", "caveat_titulares", "titular_0"]))
    assert result == "base"
