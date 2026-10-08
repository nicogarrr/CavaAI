"""Precio de entrada determinista: valor justo del modelo x (1 - margen objetivo).

El calculo es SIEMPRE determinista: precio de entrada = valor justo (escenarios
base y bear del motor de valoracion) x (1 - margen de seguridad objetivo), con
la distancia al precio actual. Sin valor justo el estado es N/D (sin_datos):
nunca se inventa una cifra para sustituirlo. Sin moneda en la fuente, los
importes se muestran sin atribuirle ninguna divisa (nunca un USD inventado) y
``currency_estado`` lo declara. Todo el resultado se etiqueta como estimacion
del modelo, nunca como dato oficial.

Toda cifra que ve el usuario sale de la PLANTILLA DETERMINISTA: cada numero va
en su campo, con su unidad y su escenario, por construccion. El margen objetivo
se cuantiza a resolucion de 0.1 punto porcentual y se muestra con esa misma
precision (25%, 25.4%, 0.5%): el porcentaje declarado siempre reproduce el
precio de entrada calculado, sin redondeos que lo contradigan.

El contexto cualitativo tambien es DETERMINISTA: el backend evalua la
valoracion y solo renderiza una plantilla del conjunto cerrado cuando los
datos reales la sostienen (caja neta del snapshot, foso con evidencia
primaria, motor de sector regulado o ciclico). Sin evidencia para ninguna
clave no hay contexto. Este endpoint no llama al LLM: una plantilla elegida
por un modelo sin evidencia seria una afirmacion financiera sin fuente.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import Company
from app.services.valuation_service import ValuationService

DEFAULT_TARGET_MOS = 0.25
# Resolucion autorizada del margen objetivo: decimas de punto porcentual. El
# parametro se cuantiza a multiplos de 0.001 y se responde cuantizado, de modo
# que el porcentaje mostrado SIEMPRE reproduce el precio de entrada calculado
# (con 0.254 la entrada es 89.52 y el texto dice 25.4%, no 25%).
RESOLUTION_MOS = 0.001
MIN_TARGET_MOS = 0.001
MAX_TARGET_MOS = 0.9
# Estimacion de planificacion para el cortacircuitos de presupuesto: el modelo
# fijado es gratuito, pero el tope protege de overrides de configuracion.

WARNING = (
    "Estimación del modelo con sus propios supuestos: no es un dato oficial "
    "ni una recomendación de inversión."
)

# Solo base y bear: un precio de entrada derivado del escenario bull no seria
# conservador y sugeriria pagar de mas.
_SCENARIO_KEYS = (("base", "base_value"), ("bear", "bear_value"))

_SYSTEM_PROMPT = (
    "Elige UNA clave que describa la tesis cualitativa de la entrada de una "
    "acción y responde SOLO con la clave, tal cual, sin explicación, sin "
    "puntuación y sin ningún otro texto. Claves permitidas: "
    "foso_competitivo (ventajas competitivas duraderas difíciles de "
    "replicar), balance_solido (caja neta y poco apalancamiento), "
    "direccion_prudente (asignación de capital prudente), riesgo_regulatorio "
    "(riesgo regulatorio elevado en el sector), ciclicidad (negocio cíclico: "
    "los supuestos del modelo pesan más de lo habitual), ninguno (ninguna "
    "clave encaja o no hay base para elegir). Nunca escribas cifras, "
    "porcentajes ni divisas."
)

# ---------------------------------------------------------------------------
# Contexto por PLANTILLA CONTROLADA con seleccion DETERMINISTA.
# ---------------------------------------------------------------------------
# Cada clave solo es elegible cuando la valoracion aporta evidencia REAL que
# la sostiene; sin evidencia para ninguna clave no hay contexto. Las
# plantillas son afirmativas porque solo se renderizan cuando la evidencia
# existe. "direccion_prudente" se retiro del catalogo: ningun dato disponible
# evalua a la direccion, y afirmarlo sin fuente seria inventarlo.
_CONTEXTO_PLANTILLAS = {
    "balance_solido": (
        "El modelo ve un balance sólido, con caja neta y poco apalancamiento."
    ),
    "foso_competitivo": (
        "El modelo ve un negocio con foso competitivo ancho, difícil de replicar."
    ),
    "riesgo_regulatorio": (
        "El modelo ve riesgo regulatorio elevado en el sector."
    ),
    "ciclicidad": (
        "El modelo ve un negocio cíclico: los supuestos pesan más de lo habitual."
    ),
}

# Fuerza agregada minima (0-100) para rotular el foso como "ancho". El
# agregado del marco de fosos es None cuando no hay categorias evaluables y
# solo es evidence_backed con fuentes primarias detras.
_MIN_FORTALEZA_FOSO = 60

# Motores cuya resolucion ya es evidencia: el resolvedor los elige a partir
# del tipo y los datos de la empresa, asi que un banco/aseguradora ES un
# sector regulado y un motor de ciclo de materias primas ES un negocio
# ciclico.
_MOTORES_REGULADOS = ("bank", "insurer")
_MOTORES_CICLICOS = ("commodity",)


def _trace_number(valuation: Mapping[str, Any], key: str) -> float | None:
    trace = valuation.get("trace")
    if not isinstance(trace, Mapping):
        return None
    value = trace.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _engine_key(valuation: Mapping[str, Any]) -> str | None:
    trace = valuation.get("trace")
    if isinstance(trace, Mapping):
        engine = trace.get("resolved_engine") or trace.get("engine")
        if isinstance(engine, str) and engine.strip():
            return engine.strip()
    return None


def _tiene_foso_ancho(valuation: Mapping[str, Any]) -> bool:
    moat = valuation.get("moat")
    if not isinstance(moat, Mapping):
        return False
    if moat.get("status") != "evidence_backed":
        return False
    aggregate = moat.get("aggregate_strength")
    if isinstance(aggregate, bool) or not isinstance(aggregate, (int, float)):
        return False
    return float(aggregate) >= _MIN_FORTALEZA_FOSO


def _riesgo_regulatorio_evidenciado(company: Company, valuation: Mapping[str, Any]) -> bool:
    if _engine_key(valuation) in _MOTORES_REGULADOS:
        return True
    return any(
        "regulat" in risk.lower()
        for risk in (company.special_risks or [])
        if isinstance(risk, str)
    )


def _selecciona_contexto(
    company: Company, valuation: Mapping[str, Any]
) -> tuple[str | None, str | None]:
    """(clave, plantilla) sostenida por evidencia real; (None, None) si no hay.

    Primera regla que casa, de mas especifica a mas general: balance_solido
    (caja neta del snapshot: net_debt < 0 en el trace del motor), luego
    foso_competitivo (agregado del marco de fosos evidence_backed por encima
    del umbral), luego riesgo_regulatorio (motor de banco/aseguradora o
    riesgo regulatorio declarado en la ficha) y por ultimo ciclicidad (motor
    de ciclo de materias primas).
    """
    net_debt = _trace_number(valuation, "net_debt")
    if net_debt is not None and net_debt < 0:
        clave = "balance_solido"
    elif _tiene_foso_ancho(valuation):
        clave = "foso_competitivo"
    elif _riesgo_regulatorio_evidenciado(company, valuation):
        clave = "riesgo_regulatorio"
    elif _engine_key(valuation) in _MOTORES_CICLICOS:
        clave = "ciclicidad"
    else:
        return None, None
    return clave, _CONTEXTO_PLANTILLAS[clave]


# ---------------------------------------------------------------------------
# Nucleo determinista
# ---------------------------------------------------------------------------


def quantize_target_mos(target_mos: float) -> float:
    """Cuantiza el margen objetivo a la resolucion autorizada (0.1%).

    Devuelve el valor cuantizado que se usa en el calculo y se muestra en los
    textos, o levanta ValueError si queda fuera de [0.001, 0.9]. Asi la cifra
    declarada y el precio de entrada son coherentes al decimal.
    """
    if isinstance(target_mos, bool) or not isinstance(target_mos, (int, float)):
        raise ValueError(f"target_mos fuera de rango [{MIN_TARGET_MOS}, {MAX_TARGET_MOS}]")
    target = round(float(target_mos), 3)
    if not MIN_TARGET_MOS <= target <= MAX_TARGET_MOS:
        raise ValueError(f"target_mos fuera de rango [{MIN_TARGET_MOS}, {MAX_TARGET_MOS}]")
    return target


def _positive_finite(value: Any) -> float | None:
    """float positivo y finito, o None. Los bool se rechazan (True es int)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _fmt_price(value: float) -> str:
    return f"{value:.2f}"


def _fmt_pct(value: float, *, signed: bool = False) -> str:
    """Porcentaje con a lo sumo 1 decimal, sin ceros de relleno.

    A la resolucion autorizada del margen (0.1%) la forma es exacta:
    25%, 25.4%, 0.5%, 0.1%, 90%. Para la distancia (derivada) es la
    presentacion; el valor exacto va en el campo JSON.
    """
    text = f"{abs(value) * 100:.1f}".rstrip("0").rstrip(".")
    sign = "-" if value < 0 else ("+" if signed else "")
    return f"{sign}{text}%"


def _price_position(distance: float | None) -> str | None:
    if distance is None:
        return None
    return "alcanzado" if distance >= 0 else "descuento_requerido"


def compute_entry_prices(
    valuation: Mapping[str, Any], *, target_mos: float
) -> dict[str, Any]:
    """Nucleo determinista. Nunca llama al LLM ni toca la base de datos.

    precio de entrada = valor justo x (1 - margen objetivo cuantizado), por
    escenario (base y bear). ``entry_vs_current_pct`` = entrada / precio
    actual - 1: positivo, el precio actual ya esta en o por debajo de la
    entrada; negativo, la entrada queda ese tramo por debajo del precio
    actual. Sin valor justo o sin precio actual los campos son None y el
    estado lo dice, nunca un numero inventado.
    """
    target = quantize_target_mos(target_mos)
    current_price = _positive_finite(valuation.get("current_price"))
    trace = valuation.get("trace")
    price_as_of = trace.get("price_as_of") if isinstance(trace, Mapping) else None
    scenarios: list[dict[str, Any]] = []
    for scenario, key in _SCENARIO_KEYS:
        fair_value = _positive_finite(valuation.get(key))
        entry_price = round(fair_value * (1 - target), 4) if fair_value is not None else None
        distance = (
            round(entry_price / current_price - 1, 4)
            if entry_price is not None and current_price is not None
            else None
        )
        scenarios.append(
            {
                "scenario": scenario,
                "estado": "ok" if entry_price is not None else "sin_datos",
                "fair_value": fair_value,
                "entry_price": entry_price,
                "entry_vs_current_pct": distance,
                "posicion_precio": _price_position(distance),
            }
        )
    computed = any(s["entry_price"] is not None for s in scenarios)
    return {
        "status": "ok" if computed else "sin_datos",
        "target_margin_of_safety": target,
        "current_price": current_price,
        "current_price_as_of": price_as_of if isinstance(price_as_of, str) else None,
        "scenarios": scenarios,
    }


def _deterministic_explanation(
    ticker: str, currency: str | None, report: Mapping[str, Any]
) -> str:
    """Explicacion de plantilla: siempre disponible y unica fuente de cifras.

    Cada numero va en su campo con su unidad y su escenario por construccion;
    nada externo lo reescribe. Sin moneda en la fuente, los importes se
    muestran sin divisa y se declara — nunca se atribuye una inventada.
    """
    target = float(report["target_margin_of_safety"])
    current = report["current_price"]
    unit = f" {currency}" if currency else ""
    computed = [s for s in report["scenarios"] if s["entry_price"] is not None]
    if not computed:
        return (
            f"Precio de entrada de {ticker}: sin datos. El modelo no ofrece un "
            "valor justo en los escenarios base ni bear, así que no hay precio "
            "de entrada que mostrar; ninguna cifra se ha inventado para "
            "sustituirlo."
        )
    parts: list[str] = []
    for item in computed:
        intro = (
            f"Escenario {item['scenario']}: con un valor justo de "
            f"{_fmt_price(item['fair_value'])}{unit} y un margen de "
            f"seguridad objetivo del {_fmt_pct(target)}, el precio de entrada es "
            f"{_fmt_price(item['entry_price'])}{unit}"
        )
        distance = item["entry_vs_current_pct"]
        if distance is None:
            parts.append(f"{intro}; sin precio actual no hay distancia que medir.")
        elif distance >= 0:
            parts.append(
                f"{intro}; el precio actual ({_fmt_price(current)}{unit}) "
                "ya está en o por debajo de ese nivel."
            )
        else:
            parts.append(
                f"{intro}, un {_fmt_pct(abs(distance))} por debajo del precio actual "
                f"({_fmt_price(current)}{unit})."
            )
    missing = [s["scenario"] for s in report["scenarios"] if s["entry_price"] is None]
    if missing:
        parts.append(
            f"Escenario {' y '.join(missing)} sin datos: el modelo no da valor justo."
        )
    if currency is None:
        parts.append("La fuente no declara la moneda de estos importes.")
    return " ".join(parts)


def entry_price_report(
    db: Session,
    company: Company,
    *,
    target_mos: float = DEFAULT_TARGET_MOS,
) -> dict[str, Any]:
    """Precio de entrada de una empresa: calculo y contexto deterministas.

    Lee la valoracion del motor (sin persistir nada) y compone el informe. La
    explicacion con cifras es siempre la plantilla determinista; el contexto
    cualitativo tambien lo es: solo se renderiza cuando la valoracion aporta
    evidencia real que lo sostiene (_selecciona_contexto). Este endpoint no
    llama al LLM.
    """
    valuation = ValuationService().value_company(db, company)
    report = compute_entry_prices(valuation, target_mos=target_mos)
    currency = (
        company.currency.strip()
        if isinstance(company.currency, str) and company.currency.strip()
        else None
    )
    explanation = _deterministic_explanation(company.ticker, currency, report)
    _, contexto = _selecciona_contexto(company, valuation)
    return {
        "ticker": company.ticker,
        "status": report["status"],
        "etiqueta": "estimacion_modelo",
        "target_margin_of_safety": report["target_margin_of_safety"],
        "currency": currency,
        "currency_estado": "ok" if currency is not None else "sin_datos",
        "current_price": report["current_price"],
        "current_price_as_of": report["current_price_as_of"],
        "scenarios": report["scenarios"],
        "valuation_status": valuation.get("status"),
        "valuation_publishable": bool(valuation.get("publishable")),
        "explicacion": explanation,
        "contexto": contexto,
        "contexto_fuente": "determinista" if contexto is not None else None,
        "warning": WARNING,
    }
