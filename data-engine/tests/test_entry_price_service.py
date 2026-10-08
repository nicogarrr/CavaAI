"""Precio de entrada determinista + explicacion LLM guardada.

Casos del diseno: sin valor justo el estado es N/D y no hay llamada LLM; una
cifra manipulada por el modelo la rechaza el validador y se publica la
explicacion determinista; y el camino feliz (cifras verificadas, cuota y
presupuesto registrados).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.llm import LLMResponse, Message, Usage
from app.models.entities import Base, BudgetUsage, Company
from app.services import asts_llm_quota as quota_store
from app.services import entry_price_service as service

VALUATION_OK = {
    "status": "ok",
    "publishable": True,
    "current_price": 90.0,
    "base_value": 120.0,
    "bear_value": 60.0,
    "trace": {"price_as_of": "2026-10-07"},
}

VALUATION_SIN_DATOS = {
    "status": "insufficient_data",
    "publishable": False,
    "current_price": 90.0,
    "base_value": None,
    "bear_value": None,
    "trace": {},
}

LLM_TEXTO_VALIDO = (
    "Con un valor justo base de 120.00 USD y un margen de seguridad objetivo "
    "del 25%, el precio de entrada estimado es 90.00 USD, igual que el precio "
    "actual. En el escenario bear el valor justo es 60.00 USD y la entrada "
    "45.00 USD, un -50.0% frente al precio actual. Es una estimación del "
    "modelo con sus supuestos, no una recomendación de inversión."
)


def _resp(text: str) -> LLMResponse:
    return LLMResponse(
        message=Message("assistant", text),
        usage=Usage(input_tokens=10, output_tokens=20, total_tokens=30),
        model="space-bunny-free",
        provider="fake",
    )


class _FakeRouter:
    def resolve(self, request) -> str:
        return "space-bunny-free"


class FakeProvider:
    """Proveedor minimo con el contrato que exige el servicio (nombre, router)."""

    name = "fake"

    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)
        self.calls: list = []
        self.model_router = _FakeRouter()

    async def complete(self, request):
        self.calls.append(request)
        return _resp(self.texts.pop(0))


@pytest.fixture()
def db_session(monkeypatch):
    # Contador de cuota local limpio por test: vive en asts_llm_quota._LOCAL.
    monkeypatch.setattr(quota_store, "_LOCAL", {})
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.info["tenant_id"] = "tenant-test"
        yield db


def _company(db: Session) -> Company:
    company = Company(
        ticker="ASTS",
        name="AST SpaceMobile",
        exchange="NASDAQ",
        currency="USD",
        sector="Telecommunications",
        industry="Satellites",
        company_type="holding",
        valuation_model="dcf",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _patch_valuation(monkeypatch, valuation: dict) -> None:
    monkeypatch.setattr(
        service.ValuationService,
        "value_company",
        lambda self, db, company, **kwargs: dict(valuation),
    )


# --------------------------------------------------------------------------
# Calculo determinista
# --------------------------------------------------------------------------


def test_calculo_determinista_escenarios_base_y_bear():
    report = service.compute_entry_prices(VALUATION_OK, target_mos=0.25)
    assert report["status"] == "ok"
    base, bear = report["scenarios"]
    assert base["scenario"] == "base" and base["fair_value"] == 120.0
    assert base["entry_price"] == pytest.approx(90.0)
    assert base["entry_vs_current_pct"] == pytest.approx(0.0)
    assert base["posicion_precio"] == "alcanzado"
    assert bear["scenario"] == "bear" and bear["entry_price"] == pytest.approx(45.0)
    assert bear["entry_vs_current_pct"] == pytest.approx(-0.5)
    assert bear["posicion_precio"] == "descuento_requerido"
    assert report["current_price"] == 90.0
    assert report["current_price_as_of"] == "2026-10-07"


def test_sin_precio_actual_no_hay_distancia():
    valuation = {**VALUATION_OK, "current_price": None}
    report = service.compute_entry_prices(valuation, target_mos=0.25)
    assert report["status"] == "ok"
    base = report["scenarios"][0]
    assert base["entry_price"] == pytest.approx(90.0)
    assert base["entry_vs_current_pct"] is None
    assert base["posicion_precio"] is None
    texto = service._deterministic_explanation("ASTS", "USD", report)
    assert "sin precio actual" in texto


def test_valor_justo_no_positivo_es_sin_datos():
    valuation = {**VALUATION_OK, "base_value": -5.0, "bear_value": "n/a"}
    report = service.compute_entry_prices(valuation, target_mos=0.25)
    assert report["status"] == "sin_datos"
    assert all(s["estado"] == "sin_datos" for s in report["scenarios"])
    assert all(s["entry_price"] is None for s in report["scenarios"])


@pytest.mark.parametrize("bad", [0, -0.1, 1.5, True, "0.25"])
def test_target_mos_invalido_rechazado(bad):
    with pytest.raises(ValueError, match="target_mos"):
        service.compute_entry_prices(VALUATION_OK, target_mos=bad)


# --------------------------------------------------------------------------
# Validador de cifras
# --------------------------------------------------------------------------


def test_validador_acepta_las_cifras_verificadas_en_sus_formas():
    report = service.compute_entry_prices(VALUATION_OK, target_mos=0.25)
    allowed = service._verified_figure_values(report)
    assert service.figures_verified(LLM_TEXTO_VALIDO, allowed)


def test_validador_rechaza_cifra_manipulada():
    report = service.compute_entry_prices(VALUATION_OK, target_mos=0.25)
    allowed = service._verified_figure_values(report)
    manipulado = LLM_TEXTO_VALIDO.replace("90.00 USD, igual", "800.00 USD, igual")
    assert not service.figures_verified(manipulado, allowed)
    # Un margen distinto del verificado tambien es una cifra inventada.
    assert not service.figures_verified("Margen objetivo del 40%.", allowed)
    # Los precios no admiten la forma x100: 9000 no es "90.00 en otra unidad".
    assert not service.figures_verified("El precio de entrada es 9000.00 USD.", allowed)


# --------------------------------------------------------------------------
# Camino feliz con LLM (proveedor falso, cuota y presupuesto reales)
# --------------------------------------------------------------------------


def test_camino_feliz_llm(monkeypatch, db_session):
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_OK)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "1")
    provider = FakeProvider(LLM_TEXTO_VALIDO)
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    assert result["status"] == "ok"
    assert result["etiqueta"] == "estimacion_modelo"
    assert result["explicacion"] == LLM_TEXTO_VALIDO
    assert result["explicacion_fuente"] == "llm"
    assert result["note"] is None
    assert len(provider.calls) == 1
    # Cuota por tenant reservada y visible para el endpoint.
    assert result["llm_quota"]["allowed"] is True
    assert result["llm_quota"]["day_used"] == 1
    # Presupuesto registrado tambien para el modelo gratuito (conteo de tokens).
    rows = db_session.scalar(
        select(func.count(BudgetUsage.id)).execution_options(include_all_tenants=True)
    )
    assert rows == 1
    usage = db_session.scalar(
        select(BudgetUsage).execution_options(include_all_tenants=True)
    )
    assert usage.workflow == "entry_price"
    assert usage.token_count == 30
    # El informe es de solo lectura: la valoracion no se persiste aqui.
    assert not db_session.new


def test_sin_fair_value_nd_y_sin_llamada_llm(monkeypatch, db_session):
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_SIN_DATOS)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "1")
    provider = FakeProvider(LLM_TEXTO_VALIDO)
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    assert result["status"] == "sin_datos"
    assert all(s["entry_price"] is None for s in result["scenarios"])
    assert provider.calls == []
    assert result["explicacion_fuente"] == "determinista"
    assert "sin datos" in result["explicacion"]
    assert "no se llama al LLM" in result["note"]
    assert result["llm_quota"] is None


def test_cifra_manipulada_degrada_a_determinista(monkeypatch, db_session):
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_OK)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "1")
    manipulado = LLM_TEXTO_VALIDO.replace("90.00 USD, igual", "800.00 USD, igual")
    provider = FakeProvider(manipulado)
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    assert result["explicacion_fuente"] == "determinista"
    assert "800.00" not in result["explicacion"]
    assert "validador de cifras" in result["note"]
    # La llamada se hizo y su coste quedo registrado aunque se rechace la salida.
    assert len(provider.calls) == 1
    rows = db_session.scalar(
        select(func.count(BudgetUsage.id)).execution_options(include_all_tenants=True)
    )
    assert rows == 1


def test_flag_desactivado_no_llama_llm(monkeypatch, db_session):
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_OK)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "0")
    provider = FakeProvider(LLM_TEXTO_VALIDO)
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    assert provider.calls == []
    assert result["explicacion_fuente"] == "determinista"
    assert "desactivada" in result["note"]


def test_cuota_agotada_no_llama_llm(monkeypatch, db_session):
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_OK)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "1")
    fake_settings = SimpleNamespace(
        is_production=False,
        entry_price_llm_calls_per_minute=0,
        entry_price_llm_calls_per_day=20,
    )
    monkeypatch.setattr(service, "get_settings", lambda: fake_settings)
    provider = FakeProvider(LLM_TEXTO_VALIDO)
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    assert provider.calls == []
    assert result["explicacion_fuente"] == "determinista"
    assert result["llm_quota"]["allowed"] is False
    assert "tope" in result["note"]


def test_salida_llm_con_cjk_reintenta_y_degrada(monkeypatch, db_session):
    """El guard de idioma (PR #933) tambien protege esta explicacion."""
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_OK)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "1")
    provider = FakeProvider("El precio es 90.00 문화 USD", "Tambien 문화 roto")
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    # Un reintento (las dos respuestas registran coste) y, al seguir roto,
    # la explicacion que se muestra es la determinista.
    assert len(provider.calls) == 2
    assert result["explicacion_fuente"] == "determinista"
    rows = db_session.scalar(
        select(func.count(BudgetUsage.id)).execution_options(include_all_tenants=True)
    )
    assert rows == 2
