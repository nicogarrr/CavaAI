"""Precio de entrada y contexto, ambos deterministas.

Casos del diseno y de la auditoria (#946): sin valor justo el estado es N/D;
toda cifra la produce la plantilla determinista; el contexto cualitativo solo
se renderiza cuando la valoracion aporta evidencia real que lo sostiene
(caja neta, foso con evidencia primaria, motor de sector regulado o ciclico)
y sin evidencia no hay contexto — este endpoint no llama al LLM; sin moneda
en la fuente ningun importe se atribuye a una divisa inventada; y el margen
objetivo cuantizado es coherente al decimal entre texto y calculo.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import Base, Company
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

# Fixtures de evidencia para la seleccion determinista del contexto. Cada una
# sostiene exactamente una clave; VALUATION_OK (sin net_debt, foso ni motor
# especial) es el fixture ASTS del auditor: sin evidencia, sin contexto.
VALUATION_CAJA_NETA = {
    **VALUATION_OK,
    "trace": {"engine": "standard_dcf", "net_debt": -120.0},
}
VALUATION_FOSO = {
    **VALUATION_OK,
    "trace": {"engine": "standard_dcf"},
    "moat": {"status": "evidence_backed", "aggregate_strength": 72},
}
VALUATION_REGULADO = {**VALUATION_OK, "trace": {"resolved_engine": "bank"}}
VALUATION_CICLICA = {**VALUATION_OK, "trace": {"engine": "commodity"}}


@pytest.fixture()
def db_session():
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


def _company_transitoria(**overrides) -> Company:
    """Empresa sin tocar la base de datos, para las reglas de seleccion."""
    base = dict(
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
    base.update(overrides)
    return Company(**base)


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
# Seleccion determinista del contexto: cada clave exige su evidencia
# --------------------------------------------------------------------------


def test_caja_neta_con_net_debt_negativo():
    clave, plantilla = service._selecciona_contexto(_company_transitoria(), VALUATION_CAJA_NETA)
    assert clave == "caja_neta"
    # La plantilla afirma SOLO el hecho demostrado: caja neta. net_debt < 0 no
    # prueba "balance solido" ni "poco apalancamiento".
    assert plantilla == "El snapshot financiero muestra caja neta."


@pytest.mark.parametrize("net_debt", [None, 0.0, 50.0])
def test_caja_neta_exige_net_debt_negativo(net_debt):
    # Sin net_debt en el trace, o con deuda neta positiva o cero, no hay caja
    # neta que afirmar (net_debt None NO es deuda cero).
    valuation = {**VALUATION_OK, "trace": {"engine": "standard_dcf", "net_debt": net_debt}}
    clave, _ = service._selecciona_contexto(_company_transitoria(), valuation)
    assert clave is None


def test_foso_ancho_con_evidencia_primaria():
    clave, plantilla = service._selecciona_contexto(_company_transitoria(), VALUATION_FOSO)
    assert clave == "foso_competitivo"
    assert plantilla == service._CONTEXTO_PLANTILLAS["foso_competitivo"]


@pytest.mark.parametrize(
    "moat",
    [
        {"status": "evidence_backed", "aggregate_strength": 59},  # bajo el umbral
        {"status": "partial_evidence", "aggregate_strength": 80},  # sin fuente primaria
        {"status": "evidence_backed", "aggregate_strength": None},  # nada evaluable
        {"status": "not_evaluable"},
    ],
)
def test_foso_exige_umbral_y_evidencia(moat):
    valuation = {**VALUATION_OK, "trace": {"engine": "standard_dcf"}, "moat": moat}
    clave, _ = service._selecciona_contexto(_company_transitoria(), valuation)
    assert clave is None


@pytest.mark.parametrize("engine", ["bank", "insurer"])
def test_sector_regulado_por_motor(engine):
    valuation = {**VALUATION_OK, "trace": {"engine": engine}}
    clave, plantilla = service._selecciona_contexto(_company_transitoria(), valuation)
    assert clave == "sector_regulado"
    # El dato prueba sector regulado; el GRADO del riesgo no lo mide nada.
    assert plantilla == "El negocio opera en un sector regulado."


def test_sector_regulado_por_etiqueta_tipada():
    # La via de la ficha usa coincidencia EXACTA con la etiqueta del catalogo
    # maestro, nunca substring sobre texto libre.
    company = _company_transitoria(special_risks=["regulation"])
    clave, _ = service._selecciona_contexto(company, VALUATION_OK)
    assert clave == "sector_regulado"


def test_negacion_regulatoria_no_es_evidencia():
    # Repro exacto del auditor: un substring "regulat" casaria esta frase y
    # publicaria precisamente lo contrario.
    company = _company_transitoria(
        special_risks=["No presenta riesgo regulatorio elevado"]
    )
    clave, _ = service._selecciona_contexto(company, VALUATION_OK)
    assert clave is None


def test_sector_regulado_por_motor_resuelto():
    # El trace del servicio rotula el motor como resolved_engine.
    clave, _ = service._selecciona_contexto(_company_transitoria(), VALUATION_REGULADO)
    assert clave == "sector_regulado"


def test_ciclicidad_por_motor_de_materias_primas():
    clave, plantilla = service._selecciona_contexto(_company_transitoria(), VALUATION_CICLICA)
    assert clave == "ciclicidad"
    assert plantilla == service._CONTEXTO_PLANTILLAS["ciclicidad"]


def test_prioridad_caja_neta_sobre_foso():
    valuation = {**VALUATION_FOSO, "trace": {"engine": "standard_dcf", "net_debt": -1.0}}
    clave, _ = service._selecciona_contexto(_company_transitoria(), valuation)
    assert clave == "caja_neta"


def test_sin_evidencia_no_hay_contexto():
    # El fixture ASTS del auditor: sin caja/deuda, foso ni motor especial.
    clave, plantilla = service._selecciona_contexto(_company_transitoria(), VALUATION_OK)
    assert clave is None
    assert plantilla is None


def test_catalogo_sin_claves_sin_fuente_de_datos():
    # direccion_prudente se retiro: ningun dato disponible evalua a la
    # direccion, y afirmarlo sin fuente seria inventarlo. Las claves que
    # sobreafirmaban (balance_solido, riesgo_regulatorio) se renombraron al
    # hecho demostrado (caja_neta, sector_regulado).
    assert "direccion_prudente" not in service._CONTEXTO_PLANTILLAS
    assert "balance_solido" not in service._CONTEXTO_PLANTILLAS
    assert "riesgo_regulatorio" not in service._CONTEXTO_PLANTILLAS


# --------------------------------------------------------------------------
# Informe: contexto determinista con y sin evidencia
# --------------------------------------------------------------------------


def test_camino_feliz_determinista(monkeypatch, db_session):
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_FOSO)
    result = service.entry_price_report(db_session, company, target_mos=0.25)
    assert result["status"] == "ok"
    assert result["etiqueta"] == "estimacion_modelo"
    # Las cifras SOLO salen de la plantilla determinista.
    assert "90.00 USD" in result["explicacion"]
    assert "margen de seguridad objetivo del 25%" in result["explicacion"]
    # El contexto es la plantilla sostenida por la evidencia del foso.
    assert result["contexto"] == service._CONTEXTO_PLANTILLAS["foso_competitivo"]
    assert result["contexto_fuente"] == "determinista"
    # Sin LLM no hay cuota ni notas de degradacion.
    assert "llm_quota" not in result
    assert "note" not in result
    # El informe es de solo lectura: la valoracion no se persiste aqui.
    assert not db_session.new


def test_contexto_determinista_con_evidencia_de_caja_neta(monkeypatch, db_session):
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_CAJA_NETA)
    result = service.entry_price_report(db_session, company, target_mos=0.25)
    assert result["contexto"] == service._CONTEXTO_PLANTILLAS["caja_neta"]
    assert result["contexto_fuente"] == "determinista"


def test_sin_evidencia_sin_contexto_ni_fuente(monkeypatch, db_session):
    # El fixture ASTS del auditor: sin caja/deuda, foso ni motor especial.
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_OK)
    result = service.entry_price_report(db_session, company, target_mos=0.25)
    assert result["contexto"] is None
    assert result["contexto_fuente"] is None
    # La explicacion determinista con sus cifras siempre esta.
    assert "90.00 USD" in result["explicacion"]


def test_sin_fair_value_nd(monkeypatch, db_session):
    company = _company(db_session)
    _patch_valuation(monkeypatch, VALUATION_SIN_DATOS)
    result = service.entry_price_report(db_session, company, target_mos=0.25)
    assert result["status"] == "sin_datos"
    assert all(s["entry_price"] is None for s in result["scenarios"])
    assert result["contexto"] is None
    assert result["contexto_fuente"] is None
    assert "sin datos" in result["explicacion"]


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
    result = service.entry_price_report(db_session, company, target_mos=0.25)
    assert result["currency"] is None
    assert result["currency_estado"] == "sin_datos"
    assert "USD" not in result["explicacion"]
    assert "no declara la moneda" in result["explicacion"]
    # Los importes siguen calculandose; lo que falta es la etiqueta de moneda.
    assert "90.00" in result["explicacion"]


def test_moneda_en_blanco_tampoco_se_inventa(monkeypatch, db_session):
    company = _company_sin_moneda()
    company.currency = "   "
    _patch_valuation(monkeypatch, VALUATION_OK)
    result = service.entry_price_report(db_session, company, target_mos=0.25)
    assert result["currency"] is None
    assert result["currency_estado"] == "sin_datos"
    assert "USD" not in result["explicacion"]

