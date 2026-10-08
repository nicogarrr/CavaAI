"""Cuota por tenant del LLM de explicacion de precio de entrada.

Mismo mecanismo que ``second_order_quota``: un namespace propio para que
ningun otro consumo LLM (catalogo ASTS, second-order) pueda dejar sin hueco
a esta funcion, ni al reves. La reserva cuenta los intentos, tambien los
fallidos; en produccion un fallo de Redis cierra el camino LLM. Los contadores
exactos se devuelven para que el endpoint los muestre.
"""

from __future__ import annotations

from app.services.asts_llm_quota import QuotaNamespace, reserve_quota

_ENTRY_PRICE_NAMESPACE = QuotaNamespace(
    key="entry-price",
    minute_setting="entry_price_llm_calls_per_minute",
    day_setting="entry_price_llm_calls_per_day",
    missing_tenant_error="Entry-price LLM needs a verified tenant",
)


def reserve_llm_call(tenant_id: int | str | None, settings) -> dict:
    """Reserva una llamada LLM de explicacion de precio de entrada."""
    return reserve_quota(tenant_id, settings, namespace=_ENTRY_PRICE_NAMESPACE)
