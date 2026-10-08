"""Precio de entrada determinista + contexto LLM por plantilla controlada.

Casos del diseno y de la auditoria (#946): sin valor justo el estado es N/D y
no hay llamada LLM; toda cifra la produce la plantilla determinista; el LLM
solo elige UNA clave de un conjunto cerrado y el backend renderiza la
plantilla (ningun texto libre del modelo llega al output: cualquier repro
historico de la auditoria degrada porque no es una clave); sin moneda en la
fuente ningun importe se atribuye a una divisa inventada; y el margen
objetivo cuantizado es coherente al decimal entre texto y calculo.
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

# Figuras del repro de la auditoria (#946).
VALUATION_AUDIT = {
    "status": "ok",
    "publishable": True,
    "current_price": 100.0,
    "base_value": 120.0,
    "bear_value": 80.0,
    "trace": {},
}

VALUATION_SIN_DATOS = {
    "status": "insufficient_data",
    "publishable": False,
    "current_price": 90.0,
    "base_value": None,
    "bear_value": None,
    "trace": {},
}

# Salida valida del LLM: UNA clave del conjunto cerrado. Lo que llega al
# usuario es la plantilla que el backend renderiza para esa clave.
CONTEXTO_CLAVE = "foso_competitivo"
CONTEXTO_PLANTILLA = service._CONTEXTO_PLANTILLAS[CONTEXTO_CLAVE]

# Las 3 cadenas exactas del repro de la auditoria: el validador global las
# aceptaba como verificadas; ahora deben degradar a la explicacion determinista.
REPRO_AUDITORIA = [
    "El precio de entrada es 25 USD y el margen de seguridad es 90%.",
    "El precio de entrada es 0 USD.",
    "El modelo estima 90 millones USD.",
]

# Segunda ronda (#946): importes en palabras que la lista parcial dejaba pasar.
REPRO_AUDITORIA_CANTIDADES = [
    "El precio de entrada es cero.",
    "El precio de entrada es uno.",
    "El precio de entrada es medio.",
    "El precio de entrada es un cuarto.",
]

# Tercera ronda (#946): cierre estructural, sin inventario numerico. La
# morfologia caza variantes que la lista no conocia (doscientas, tresmil,
# millones, ninety-five) y el vocabulario de importes esta prohibido en
# cualquier forma, no solo en afirmaciones copulativas.
REPRO_AUDITORIA_ESTRUCTURAL = [
    "El precio de entrada es doscientas unidades.",
    "El modelo estima veinte millones de beneficio.",
    "El precio objetivo es tres mil.",
    "El precio de entrada es noventa y cinco.",
    "The entry price is ninety-five.",
    "The entry price is ninety five.",
]

# Aceptado por diseno (nota del auditor): el contexto no habla de importes en
# ninguna forma, asi que estas frases cualitativas tambien se rechazan.
RECHAZOS_ACEPTADOS = [
    "El margen de seguridad protege.",
    "Las barreras de entrada son altas.",
]

# Cuarta ronda (#946): afirmaciones de importe sin sustantivo prohibido ni
# simbolo. Refutan la premisa de que toda afirmacion financiera nombra el
# importe; con la plantilla controlada dejan de ser un problema de vocabulario.
REPRO_AUDITORIA_CIFRAS_SUELTAS = [
    "Se puede comprar a noventa y cinco.",
    "Pagar noventa por título deja colchón.",
    "El negocio crece cuarenta por cien cada año.",
]

# Repros historicos del validador de vocabulario (rondas 1-3): textos con
# cifras en digitos, palabras, escalas, porcentajes o divisas. Ninguno es una
# clave valida, asi que todos degradan por el mismo camino cerrado.
REPRO_AUDITORIA_HISTORICOS = [
    "La entrada ronda los noventa millones.",
    "El precio cayó noventa dólares.",
    "El precio cayó ninety dollars.",
    "Subió un cuarenta por ciento.",
    "Subió un 40%.",
    "El descuento es del 25 %.",
    "El precio es 90€.",
    "Son unos mil títulos.",
    "La empresa vale millones.",
    "Cotiza en USD.",
    "Versión 2 del modelo.",
]


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


def _company(db: Session, *, currency: str | None = "USD") -> Company:
    company = Company(
        ticker="ASTS",
        name="AST SpaceMobile",
        exchange="NASDAQ",
        currency=currency,
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


def _budget_rows(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count(BudgetUsage.id)).execution_options(include_all_tenants=True)
        )
        or 0
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


@pytest.mark.parametrize("bad", [0, 0.0004, -0.1, 1.5, True, "0.25"])
def test_target_mos_invalido_rechazado(bad):
    with pytest.raises(ValueError, match="target_mos"):
        service.compute_entry_prices(VALUATION_OK, target_mos=bad)


# --------------------------------------------------------------------------
# Precision del margen: texto y calculo coherentes al decimal
# --------------------------------------------------------------------------


def test_mos_fraccional_texto_y_calculo_coherentes():
    report = service.compute_entry_prices(VALUATION_OK, target_mos=0.254)
    assert report["target_margin_of_safety"] == pytest.approx(0.254)
    base = report["scenarios"][0]
    assert base["entry_price"] == pytest.approx(120.0 * (1 - 0.254))  # 89.52
    texto = service._deterministic_explanation("ASTS", "USD", report)
    assert "25.4%" in texto and "89.52" in texto
    assert "del 25%" not in texto


def test_mos_minimo_no_se_muestra_como_cero():
    report = service.compute_entry_prices(VALUATION_OK, target_mos=0.005)
    assert report["target_margin_of_safety"] == pytest.approx(0.005)
    assert report["scenarios"][0]["entry_price"] == pytest.approx(119.4)
    texto = service._deterministic_explanation("ASTS", "USD", report)
    assert "0.5%" in texto and "del 0%" not in texto


def test_mos_se_cuantiza_a_resolucion_autorizada_y_se_responde_cuantizado():
    report = service.compute_entry_prices(VALUATION_OK, target_mos=0.2545)
    target = report["target_margin_of_safety"]
    assert target in (0.254, 0.255)
    assert report["scenarios"][0]["entry_price"] == pytest.approx(120.0 * (1 - target))
    texto = service._deterministic_explanation("ASTS", "USD", report)
    # El porcentaje mostrado es el del valor cuantizado, nunca el pedido en crudo.
    esperado = f"{target * 100:.1f}".rstrip("0").rstrip(".")
    assert f"del {esperado}%" in texto


# --------------------------------------------------------------------------
# Conjunto cerrado de claves: la unica via de texto LLM hacia el output
# --------------------------------------------------------------------------


def test_clave_valida_renderiza_su_plantilla():
    for clave, plantilla in service._CONTEXTO_PLANTILLAS.items():
        assert service._render_contexto(clave) == plantilla
        assert service._render_contexto(f"  {clave.upper()}\n") == plantilla


def test_respuesta_fuera_del_conjunto_cerrado_no_renderiza():
    assert service._render_contexto("tesis libre con foso ancho") is None
    assert service._render_contexto("foso_competitivo.") is None  # puntuacion
    assert service._render_contexto("foso_amplio") is None  # clave inexistente
    assert service._render_contexto("") is None
    # "ninguno" tampoco renderiza: el llamador la trata como ausencia valida.
    assert service._render_contexto(service._CLAVE_NINGUNO) is None


# --------------------------------------------------------------------------
# Camino feliz con LLM (proveedor falso, cuota y presupuesto reales)
# --------------------------------------------------------------------------


def test_camino_feliz_llm(monkeypatch, db_session):
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_OK)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "1")
    provider = FakeProvider(CONTEXTO_CLAVE)
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    assert result["status"] == "ok"
    assert result["etiqueta"] == "estimacion_modelo"
    # Las cifras SOLO salen de la plantilla determinista; el LLM elige clave.
    assert "90.00 USD" in result["explicacion"]
    assert "margen de seguridad objetivo del 25%" in result["explicacion"]
    assert result["contexto"] == CONTEXTO_PLANTILLA
    assert result["contexto_fuente"] == "llm"
    assert result["note"] is None
    assert len(provider.calls) == 1
    # Cuota por tenant reservada y visible para el endpoint.
    assert result["llm_quota"]["allowed"] is True
    assert result["llm_quota"]["day_used"] == 1
    # Presupuesto registrado tambien para el modelo gratuito (conteo de tokens).
    assert _budget_rows(db_session) == 1
    usage = db_session.scalar(
        select(BudgetUsage).execution_options(include_all_tenants=True)
    )
    assert usage.workflow == "entry_price"
    assert usage.token_count == 30
    # El informe es de solo lectura: la valoracion no se persiste aqui.
    assert not db_session.new


def test_clave_ninguno_es_ausencia_valida_sin_nota(monkeypatch, db_session):
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_OK)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "1")
    provider = FakeProvider("ninguno")
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    assert result["contexto"] is None
    assert result["contexto_fuente"] is None
    # No es un fallo: sin nota de degradacion, con la cuota consumida visible.
    assert result["note"] is None
    assert len(provider.calls) == 1
    assert result["llm_quota"]["allowed"] is True


def test_sin_fair_value_nd_y_sin_llamada_llm(monkeypatch, db_session):
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_SIN_DATOS)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "1")
    provider = FakeProvider(CONTEXTO_CLAVE)
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    assert result["status"] == "sin_datos"
    assert all(s["entry_price"] is None for s in result["scenarios"])
    assert provider.calls == []
    assert result["contexto"] is None
    assert "sin datos" in result["explicacion"]
    assert "no se llama al LLM" in result["note"]
    assert result["llm_quota"] is None


@pytest.mark.parametrize(
    "texto",
    REPRO_AUDITORIA
    + REPRO_AUDITORIA_CANTIDADES
    + REPRO_AUDITORIA_ESTRUCTURAL
    + REPRO_AUDITORIA_CIFRAS_SUELTAS
    + REPRO_AUDITORIA_HISTORICOS
    + RECHAZOS_ACEPTADOS,
)
def test_repros_auditoria_degradan_a_determinista(monkeypatch, db_session, texto):
    """Ningun texto libre llega al output: lo que no es una clave, degrada.

    Las cadenas en espanol llegan a la seleccion de clave y se rechazan como
    clave invalida (nota "rechazado", una llamada); las que el guard de
    idioma (PR #933) intercepta antes degradan con la nota generica. En ambos
    casos el usuario solo ve la explicacion determinista con SUS cifras.
    """
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_AUDIT)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "1")
    provider = FakeProvider(texto, texto)
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    assert result["contexto"] is None
    assert result["contexto_fuente"] is None
    assert result["note"] is not None
    assert "90.00 USD" in result["explicacion"]  # base: 120 x 0.75
    assert "60.00 USD" in result["explicacion"]  # bear: 80 x 0.75
    assert texto not in result["explicacion"]
    assert 1 <= len(provider.calls) <= 2
    assert _budget_rows(db_session) == len(provider.calls)


def test_flag_desactivado_no_llama_llm(monkeypatch, db_session):
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_OK)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "0")
    provider = FakeProvider(CONTEXTO_CLAVE)
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    assert provider.calls == []
    assert result["contexto"] is None
    assert "desactivado" in result["note"]


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
    provider = FakeProvider(CONTEXTO_CLAVE)
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    assert provider.calls == []
    assert result["contexto"] is None
    assert result["llm_quota"]["allowed"] is False
    assert "tope" in result["note"]


def test_salida_llm_con_cjk_reintenta_y_degrada(monkeypatch, db_session):
    """El guard de idioma (PR #933) tambien protege este contexto."""
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_OK)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "1")
    provider = FakeProvider("Comprar con margen 문화 ayuda", "Tambien 문화 roto")
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    # Un reintento (las dos respuestas registran coste) y, al seguir roto,
    # lo que se muestra es solo la explicacion determinista.
    assert len(provider.calls) == 2
    assert result["contexto"] is None
    assert _budget_rows(db_session) == 2


# --------------------------------------------------------------------------
# Moneda: sin moneda en la fuente nunca se inventa una
# --------------------------------------------------------------------------


def _company_sin_moneda() -> Company:
    """Company.currency es NOT NULL con default USD: la fuente sin moneda se
    representa como instancia sin currency asignada (None) o en blanco."""
    return Company(
        ticker="ASTS",
        name="AST SpaceMobile",
        exchange="NASDAQ",
        currency=None,
        sector="Telecommunications",
        industry="Satellites",
        company_type="holding",
        valuation_model="dcf",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )


def test_sin_moneda_no_se_atribuye_divisa_inventada(monkeypatch, db_session):
    company = _company_sin_moneda()
    _patch_valuation(monkeypatch, VALUATION_OK)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "1")
    provider = FakeProvider(CONTEXTO_CLAVE)
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    assert result["currency"] is None
    assert result["currency_estado"] == "sin_datos"
    assert "USD" not in result["explicacion"]
    assert "no declara la moneda" in result["explicacion"]
    # Los importes siguen calculandose; lo que falta es la etiqueta de moneda.
    assert "90.00" in result["explicacion"]
    # El contexto LLM tampoco puede nombrar divisas (conjunto cerrado).
    assert result["contexto"] == CONTEXTO_PLANTILLA


def test_moneda_en_blanco_tampoco_se_inventa(monkeypatch, db_session):
    company = _company_sin_moneda()
    company.currency = "   "
    _patch_valuation(monkeypatch, VALUATION_OK)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "1")
    provider = FakeProvider(CONTEXTO_CLAVE)
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    assert result["currency"] is None
    assert result["currency_estado"] == "sin_datos"
    assert "USD" not in result["explicacion"]


def test_contexto_que_nombra_divisa_rechazado_aunque_haya_moneda(monkeypatch, db_session):
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_OK)
    monkeypatch.setenv("ENTRY_PRICE_LLM_ENABLED", "1")
    provider = FakeProvider("El precio en USD ya descontaba la subida.")
    result = service.entry_price_report(
        db_session, company, target_mos=0.25, use_llm=True, provider=provider
    )
    assert result["contexto"] is None
    assert "rechazado" in result["note"]
