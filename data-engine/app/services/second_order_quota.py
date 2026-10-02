"""Atomic per-tenant rate and daily request budget for news second-order LLM.

A reservation counts attempted calls, including upstream failures. In production,
Redis failure blocks the LLM path. No expense or money is recorded for a free
provider model. Exact counts are shown in the endpoint response.

The accounting itself lives in ``app.services.asts_llm_quota``; only the
namespace is this feature's, so the ASTS catalog budget cannot starve it.
"""

from __future__ import annotations

from app.services.asts_llm_quota import QuotaNamespace, reserve_quota

_SECOND_ORDER_NAMESPACE = QuotaNamespace(
    key="second-order",
    minute_setting="second_order_llm_calls_per_minute",
    day_setting="second_order_llm_calls_per_day",
    missing_tenant_error="Second-order LLM needs a verified tenant",
)


def reserve_llm_call(tenant_id: int | str | None, settings) -> dict:
    """Reserve one second-order LLM call for ``tenant_id``."""
    return reserve_quota(tenant_id, settings, namespace=_SECOND_ORDER_NAMESPACE)
