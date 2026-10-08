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

El LLM, como mucho, ELIGE UNA CLAVE de un conjunto cerrado de contextos
cualitativos (flag ENTRY_PRICE_LLM_ENABLED=1 y use_llm=true en el endpoint):
el backend renderiza la plantilla asociada a la clave y NINGUN texto libre
del modelo llega al output. complete_guarded (idioma e integridad, PR #933)
sigue delante de la seleccion, y una respuesta que no sea una clave exacta se
rechaza. Ante cualquier fallo (proveedor, cuota, presupuesto, clave invalida)
se publica solo la explicacion determinista. Sin datos suficientes no hay
llamada al LLM.

La sesion se confirma (commit) ANTES de cualquier llamada al LLM, siguiendo a
llm_proposal_runner y second_order_news_service: ninguna conexion queda
abierta durante la espera. Cada respuesta del proveedor (tambien la que la
validacion descarta) registra su coste en el presupuesto, y la cuota diaria
por tenant se reserva antes de cada llamada, reintento incluido.
"""

from __future__ import annotations

import json
import logging
import math
import os
from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm import LLMRequest, Message, create_llm_provider
from app.llm.model_aliases import VERIFIED_FREE_MODELS
from app.models import Company
from app.services.async_bridge import run_from_any_context
from app.services.budget import BudgetController, BudgetExceededError
from app.services.entry_price_quota import reserve_llm_call
from app.services.llm_output_guard import complete_guarded
from app.services.valuation_service import ValuationService

logger = logging.getLogger(__name__)

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
_BUDGET_ESTIMATE_EUR = 0.02

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
# Contexto LLM por PLANTILLA CONTROLADA: el modelo solo elige una clave.
# ---------------------------------------------------------------------------

_CLAVE_NINGUNO = "ninguno"

# Conjunto cerrado de contextos. El LLM devuelve UNA clave; el backend
# renderiza la plantilla asociada. Ningun texto libre del modelo llega al
# output, asi que no hay validador de vocabulario que pueda perder una
# variante: lo que no es una clave exacta no existe para el usuario.
_CONTEXTO_PLANTILLAS = {
    "foso_competitivo": (
        "El modelo ve un negocio con foso competitivo ancho, difícil de replicar."
    ),
    "balance_solido": (
        "El modelo ve un balance sólido, con caja neta y poco apalancamiento."
    ),
    "direccion_prudente": (
        "El modelo ve una dirección prudente en la asignación del capital."
    ),
    "riesgo_regulatorio": (
        "El modelo ve riesgo regulatorio elevado en el sector."
    ),
    "ciclicidad": (
        "El modelo ve un negocio cíclico: los supuestos pesan más de lo habitual."
    ),
}


def _render_contexto(respuesta: str) -> str | None:
    """Plantilla renderizada si la respuesta es una clave valida; None si no.

    Hermetico por construccion: el unico camino del texto LLM hacia el output
    pasa por el dict de plantillas. Texto libre, claves con puntuacion extra
    o claves inexistentes devuelven None y degradan al camino determinista.
    """
    return _CONTEXTO_PLANTILLAS.get(respuesta.strip().lower())


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
    el LLM nunca lo reescribe. Sin moneda en la fuente, los importes se
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


# ---------------------------------------------------------------------------
# Contexto LLM (opcional, sin cifras)
# ---------------------------------------------------------------------------


def _context_prompt(company: Company) -> str:
    """Datos NO numericos para situar la redaccion; nunca cifras ni moneda."""
    return json.dumps(
        {"empresa": company.name, "ticker": company.ticker}, ensure_ascii=False
    )


async def _draft_context(provider, prompt: str, *, on_response, before_retry) -> str:
    """Una clave guardada: idioma e integridad via complete_guarded.

    El modelo fijado es el gratuito verificado; un override de entorno que lo
    mueva a un modelo de pago levanta y el llamador degrada al camino
    determinista, como en second_order_news_service.
    """
    request = LLMRequest(
        messages=[Message("system", _SYSTEM_PROMPT), Message("user", prompt)],
        task="entry_price_explanation",
        model="space-bunny-free",
        temperature=0.0,
        max_tokens=32,
    )
    if provider.model_router.resolve(request) not in VERIFIED_FREE_MODELS:
        raise RuntimeError("Entry-price model is not the verified free model")
    guarded = await complete_guarded(
        provider,
        request,
        source="entry_price",
        on_response=on_response,
        before_retry=before_retry,
    )
    return str(guarded.response.text).strip()


def _try_llm_context(
    db: Session,
    company: Company,
    *,
    provider=None,
) -> tuple[str | None, dict | None, str | None]:
    """Intenta el contexto LLM. Devuelve (texto | None, quota | None, nota | None).

    El texto devuelto es SIEMPRE una plantilla del conjunto cerrado renderizada
    por el backend; el modelo solo eligio la clave. Nunca lanza: cualquier
    fallo deja solo la explicacion determinista y una nota honesta de por que
    el contexto no se muestra. Nunca afirma que una llamada fallida funciono.
    """
    tenant_id = db.info.get("tenant_id")
    quota: dict | None = None
    try:
        provider = provider or create_llm_provider()
        if provider.name == "disabled":
            return None, None, "Proveedor LLM no configurado."
        budget = BudgetController()
        settings = get_settings()
        if not budget.can_spend(db, _BUDGET_ESTIMATE_EUR):
            return None, None, "Contexto LLM no disponible: presupuesto diario agotado."
        quota = reserve_llm_call(tenant_id, settings)
        if not quota["allowed"]:
            return None, quota, "Contexto LLM no disponible: tope de llamadas alcanzado."
    except Exception:  # noqa: BLE001 - config, tenant o cuota rotos: falla cerrado
        logger.warning("entry-price LLM: preparacion fallida, camino determinista", exc_info=True)
        return None, quota, "Contexto LLM no disponible; se muestra solo la explicación determinista."

    prompt = _context_prompt(company)
    db.commit()  # sin conexion ni transaccion abiertas durante la espera del LLM

    def _record(resp) -> None:
        # Cada respuesta del proveedor, tambien la que la validacion descarta,
        # consume presupuesto.
        cost = budget.estimate_cost_eur(
            resp.model, resp.usage.input_tokens, resp.usage.output_tokens
        )
        budget.record(db, resp.model, "entry_price", cost, resp.usage.total_tokens)

    def _before_retry() -> None:
        nonlocal quota
        retry_quota = reserve_llm_call(tenant_id, settings)
        quota = retry_quota
        if not retry_quota["allowed"]:
            raise BudgetExceededError("entry-price LLM quota exhausted before retry")
        try:
            allowed_budget = budget.can_spend(db, _BUDGET_ESTIMATE_EUR)
        finally:
            db.commit()  # el SELECT del tope abre transaccion: se libera antes del 2o LLM
        if not allowed_budget:
            raise BudgetExceededError("LLM budget exhausted")

    try:
        text = run_from_any_context(
            _draft_context(provider, prompt, on_response=_record, before_retry=_before_retry)
        )
    except Exception as exc:  # noqa: BLE001 - el fallo del proveedor no rompe el endpoint
        logger.warning(
            "entry-price LLM: fallo (%s), camino determinista", type(exc).__name__
        )
        return None, quota, "Contexto LLM no disponible; se muestra solo la explicación determinista."
    if text.strip().lower() == _CLAVE_NINGUNO:
        # Respuesta valida: el modelo no ve contexto que aportar. Ausencia,
        # no fallo: sin contexto y sin nota de degradacion.
        return None, quota, None
    contexto = _render_contexto(text)
    if contexto is None:
        logger.warning(
            "entry-price LLM: respuesta fuera del conjunto cerrado, camino determinista"
        )
        return (
            None,
            quota,
            "El contexto LLM no era una clave de plantilla válida y fue "
            "rechazado; se muestra solo la explicación determinista.",
        )
    return contexto, quota, None


def entry_price_report(
    db: Session,
    company: Company,
    *,
    target_mos: float = DEFAULT_TARGET_MOS,
    use_llm: bool = False,
    provider=None,
) -> dict[str, Any]:
    """Precio de entrada de una empresa: calculo determinista + contexto LLM opcional.

    Lee la valoracion del motor (sin persistir nada) y compone el informe. La
    explicacion con cifras es siempre la plantilla determinista; el LLM solo
    puede anadir un contexto cualitativo validado. Solo es candidato si hay
    al menos un precio de entrada calculado: sin cifras verificadas no hay
    llamada al modelo.
    """
    valuation = ValuationService().value_company(db, company)
    report = compute_entry_prices(valuation, target_mos=target_mos)
    currency = (
        company.currency.strip()
        if isinstance(company.currency, str) and company.currency.strip()
        else None
    )
    explanation = _deterministic_explanation(company.ticker, currency, report)
    contexto = None
    contexto_fuente = None
    note = None
    llm_quota = None
    if use_llm:
        if report["status"] != "ok":
            note = "Sin valor justo no se llama al LLM: no hay cifras que explicar."
        elif os.getenv("ENTRY_PRICE_LLM_ENABLED") != "1":
            note = "Contexto LLM desactivado por configuración."
        else:
            contexto, llm_quota, note = _try_llm_context(db, company, provider=provider)
            if contexto is not None:
                contexto_fuente = "llm"
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
        "contexto_fuente": contexto_fuente,
        "note": note,
        "llm_quota": llm_quota,
        "warning": WARNING,
    }
