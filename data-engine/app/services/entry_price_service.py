"""Precio de entrada determinista: valor justo del modelo x (1 - margen objetivo).

El calculo es SIEMPRE determinista: precio de entrada = valor justo (escenarios
base y bear del motor de valoracion) x (1 - margen de seguridad objetivo), con
la distancia al precio actual. Sin valor justo el estado es N/D (sin_datos):
nunca se inventa una cifra para sustituirlo. Todo el resultado se etiqueta
como estimacion del modelo, nunca como dato oficial.

El LLM solo REDACTA la explicacion, y solo cuando el endpoint la pide
(``use_llm=true``) y el flag ENTRY_PRICE_LLM_ENABLED=1 esta activo. Recibe las
cifras ya verificadas por este servicio como DATOS; su salida pasa por
``complete_guarded`` (idioma e integridad de tokens, PR #933) y por un
validador de cifras que rechaza cualquier numero que no sea una de las cifras
verificadas. Ante cualquier fallo (proveedor, cuota, presupuesto, validacion)
la explicacion que se muestra es la determinista. Sin datos suficientes no hay
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
import re
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

_NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")

_SYSTEM_PROMPT = (
    "Redacta una explicación breve (máximo 80 palabras) del precio de entrada "
    "de una acción, en español profesional. Las cifras del mensaje son DATOS "
    "verificados: úsalas exactamente con el formato dado y no escribas ningún "
    "otro número (ni cantidades, ni ordinales, ni porcentajes nuevos). Di que "
    "es una estimación del modelo con sus supuestos, no un dato oficial ni "
    "una recomendación de inversión. No inventes noticias, fechas ni causas."
)


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


def _price_position(distance: float | None) -> str | None:
    if distance is None:
        return None
    return "alcanzado" if distance >= 0 else "descuento_requerido"


def compute_entry_prices(
    valuation: Mapping[str, Any], *, target_mos: float
) -> dict[str, Any]:
    """Nucleo determinista. Nunca llama al LLM ni toca la base de datos.

    precio de entrada = valor justo x (1 - margen objetivo), por escenario
    (base y bear). ``entry_vs_current_pct`` = entrada / precio actual - 1:
    positivo, el precio actual ya esta por debajo de la entrada; negativo, la
    entrada queda ese tramo por debajo del precio actual. Sin valor justo o
    sin precio actual los campos son None y el estado lo dice, nunca un
    numero inventado.
    """
    if (
        isinstance(target_mos, bool)
        or not isinstance(target_mos, (int, float))
        or not 0 < float(target_mos) <= MAX_TARGET_MOS
    ):
        raise ValueError(f"target_mos fuera de rango (0, {MAX_TARGET_MOS}]")
    target = float(target_mos)
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
    ticker: str, currency: str, report: Mapping[str, Any]
) -> str:
    """Explicacion de plantilla: siempre disponible, con las mismas cifras.

    Es el fallback cuando el LLM no corre o su salida se rechaza, y nunca
    empeora con la capa LLM: las relaciones cifra-campo-unidad ya salen
    verificadas del calculo.
    """
    target = float(report["target_margin_of_safety"])
    current = report["current_price"]
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
            f"{_fmt_price(item['fair_value'])} {currency} y un margen de "
            f"seguridad objetivo del {target:.0%}, el precio de entrada es "
            f"{_fmt_price(item['entry_price'])} {currency}"
        )
        distance = item["entry_vs_current_pct"]
        if distance is None:
            parts.append(f"{intro}; sin precio actual no hay distancia que medir.")
        elif distance >= 0:
            parts.append(
                f"{intro}; el precio actual ({_fmt_price(current)} {currency}) "
                "ya está en o por debajo de ese nivel."
            )
        else:
            parts.append(
                f"{intro}, un {abs(distance):.1%} por debajo del precio actual "
                f"({_fmt_price(current)} {currency})."
            )
    missing = [s["scenario"] for s in report["scenarios"] if s["entry_price"] is None]
    if missing:
        parts.append(
            f"Escenario {' y '.join(missing)} sin datos: el modelo no da valor justo."
        )
    return " ".join(parts)


def _verified_figure_values(report: Mapping[str, Any]) -> set[float]:
    """Cifras que el LLM puede citar, en todas sus formas redondeadas.

    Precios (valor justo, entrada, actual): solo su forma cruda redondeada a
    0, 1 y 2 decimales. Ratios (margen objetivo, distancia): ademas su forma
    porcentual (x100) con ambos signos — "-50.0%", "50 %", "0.5" y "0.50" son
    la misma distancia. Dar a los precios la forma x100 admitiria una cifra
    manipulada (90.00 -> "9000") y no darla a los ratios rechazaria el
    formato porcentual con que se pasan al modelo. Cualquier otro numero en
    la salida es una cifra manipulada o inventada y la invalida.
    """
    allowed: set[float] = set()

    def add_price(value: float) -> None:
        for ndigits in (0, 1, 2):
            allowed.add(round(value, ndigits))

    def add_ratio(value: float) -> None:
        for scaled in (value, value * 100):
            for ndigits in (0, 1, 2):
                allowed.add(round(scaled, ndigits))
                allowed.add(-round(scaled, ndigits))

    add_ratio(float(report["target_margin_of_safety"]))
    if report["current_price"] is not None:
        add_price(float(report["current_price"]))
    for item in report["scenarios"]:
        if item["fair_value"] is not None:
            add_price(float(item["fair_value"]))
        if item["entry_price"] is not None:
            add_price(float(item["entry_price"]))
        if item["entry_vs_current_pct"] is not None:
            add_ratio(float(item["entry_vs_current_pct"]))
    return allowed


def figures_verified(text: str, allowed: set[float]) -> bool:
    """Toda cifra del texto debe ser una de las verificadas (o su forma %).

    Fail-closed por construccion: el prompt prohibe escribir otros numeros,
    asi que un literal fuera del conjunto solo puede ser una cifra inventada
    o manipulada (o texto que no siguio el formato, que tampoco se publica).
    """
    for token in _NUMBER_RE.findall(text):
        value = float(token.replace(",", "."))
        if round(value, 2) not in allowed:
            return False
    return True


def _llm_prompt(company: Company, currency: str, report: Mapping[str, Any]) -> str:
    """Cifras verificadas como DATOS JSON; nunca instrucciones."""
    escenarios: list[dict[str, str]] = []
    for item in report["scenarios"]:
        if item["entry_price"] is None:
            continue
        entry = {
            "escenario": item["scenario"],
            "valor_justo": _fmt_price(item["fair_value"]),
            "precio_entrada": _fmt_price(item["entry_price"]),
        }
        if item["entry_vs_current_pct"] is not None:
            entry["entrada_vs_precio_actual"] = f"{item['entry_vs_current_pct']:+.1%}"
        escenarios.append(entry)
    payload: dict[str, Any] = {
        "empresa": company.name,
        "ticker": company.ticker,
        "moneda": currency,
        "margen_seguridad_objetivo": f"{float(report['target_margin_of_safety']):.0%}",
        "escenarios": escenarios,
    }
    if report["current_price"] is not None:
        payload["precio_actual"] = _fmt_price(report["current_price"])
    return json.dumps(payload, ensure_ascii=False)


async def _draft_explanation(provider, prompt: str, *, on_response, before_retry) -> str:
    """Una redaccion guardada: idioma e integridad via complete_guarded.

    El modelo fijado es el gratuito verificado; un override de entorno que lo
    mueva a un modelo de pago levanta y el llamador degrada al camino
    determinista, como en second_order_news_service.
    """
    request = LLMRequest(
        messages=[Message("system", _SYSTEM_PROMPT), Message("user", prompt)],
        task="entry_price_explanation",
        model="space-bunny-free",
        temperature=0.2,
        max_tokens=220,
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


def _try_llm_explanation(
    db: Session,
    company: Company,
    currency: str,
    report: Mapping[str, Any],
    *,
    provider=None,
) -> tuple[str | None, dict | None, str | None]:
    """Intenta la explicacion LLM. Devuelve (texto | None, quota | None, nota | None).

    Nunca lanza: cualquier fallo deja la explicacion determinista y una nota
    honesta de por que la LLM no se muestra. Nunca afirma que una llamada
    fallida funciono.
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
            return None, None, "Explicación LLM no disponible: presupuesto diario agotado."
        quota = reserve_llm_call(tenant_id, settings)
        if not quota["allowed"]:
            return None, quota, "Explicación LLM no disponible: tope de llamadas alcanzado."
    except Exception:  # noqa: BLE001 - config, tenant o cuota rotos: falla cerrado
        logger.warning("entry-price LLM: preparacion fallida, camino determinista", exc_info=True)
        return None, quota, "Explicación LLM no disponible; se muestra la determinista."

    prompt = _llm_prompt(company, currency, report)
    allowed = _verified_figure_values(report)
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
            _draft_explanation(
                provider, prompt, on_response=_record, before_retry=_before_retry
            )
        )
    except Exception as exc:  # noqa: BLE001 - el fallo del proveedor no rompe el endpoint
        logger.warning(
            "entry-price LLM: fallo (%s), camino determinista", type(exc).__name__
        )
        return None, quota, "Explicación LLM no disponible; se muestra la determinista."
    if not figures_verified(text, allowed):
        logger.warning(
            "entry-price LLM: cifra no verificada en la salida, camino determinista"
        )
        return (
            None,
            quota,
            "La explicación LLM fue rechazada por el validador de cifras; "
            "se muestra la determinista.",
        )
    return text, quota, None


def entry_price_report(
    db: Session,
    company: Company,
    *,
    target_mos: float = DEFAULT_TARGET_MOS,
    use_llm: bool = False,
    provider=None,
) -> dict[str, Any]:
    """Precio de entrada de una empresa: calculo determinista + explicacion.

    Lee la valoracion del motor (sin persistir nada) y compone el informe.
    Solo es candidato a explicacion LLM si hay al menos un precio de entrada
    calculado: sin cifras verificadas no hay llamada al modelo.
    """
    valuation = ValuationService().value_company(db, company)
    report = compute_entry_prices(valuation, target_mos=target_mos)
    currency = company.currency or "USD"
    explanation = _deterministic_explanation(company.ticker, currency, report)
    explanation_source = "determinista"
    note = None
    llm_quota = None
    if use_llm:
        if report["status"] != "ok":
            note = "Sin valor justo no se llama al LLM: no hay cifras que explicar."
        elif os.getenv("ENTRY_PRICE_LLM_ENABLED") != "1":
            note = "Explicación LLM desactivada por configuración."
        else:
            llm_text, llm_quota, note = _try_llm_explanation(
                db, company, currency, report, provider=provider
            )
            if llm_text is not None:
                explanation = llm_text
                explanation_source = "llm"
    return {
        "ticker": company.ticker,
        "status": report["status"],
        "etiqueta": "estimacion_modelo",
        "target_margin_of_safety": report["target_margin_of_safety"],
        "currency": currency,
        "current_price": report["current_price"],
        "current_price_as_of": report["current_price_as_of"],
        "scenarios": report["scenarios"],
        "valuation_status": valuation.get("status"),
        "valuation_publishable": bool(valuation.get("publishable")),
        "explicacion": explanation,
        "explicacion_fuente": explanation_source,
        "note": note,
        "llm_quota": llm_quota,
        "warning": WARNING,
    }
