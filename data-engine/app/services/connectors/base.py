"""Contratos y utilidades compartidas por los connectors de ingesta."""


from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Tope de reintentos por llamada y espera maxima por uno. El presupuesto
# acota el tiempo total en el peor caso.
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BASE_SECONDS = 0.5
DEFAULT_RETRY_CAP_SECONDS = 30.0


class UpstreamRateLimited(RuntimeError):
    """El proveedor respondio 429 y se agotaron los reintentos con presupuesto."""


def retry_after_seconds(response: Any, cap: float = DEFAULT_RETRY_CAP_SECONDS) -> float:
    """Respeta la cabecera Retry-After del proveedor, acotada.

    Ignorarla y reintentar con backoff propio es lo que convierte un 429 en un
    baneo de la clave: el proveedor dice explicitamente cuando puede volver a
    intentarse.
    """
    header = None
    try:
        header = response.headers.get("retry-after")
    except AttributeError:
        return 0.0
    if not header:
        return 0.0
    try:
        return max(0.0, min(float(header), cap))
    except (TypeError, ValueError):
        return 0.0


async def get_with_retry(
    fetch: Any,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_seconds: float = DEFAULT_RETRY_BASE_SECONDS,
    cap_seconds: float = DEFAULT_RETRY_CAP_SECONDS,
) -> Any:
    """Ejecuta ``fetch()`` reintentando 429 y 5xx con backoff y presupuesto.

Los tres proveedores con clave (FMP, Finnhub, FRED) clasifican sus planes por
llamadas por minuto. Antes sus clients hacian ``raise_for_status()`` y nada
mas: un 429 era un fallo definitivo, el llamante lo tragaba como
``status="unavailable"`` y el barrido de precios perdia la cobertura sin
reintentar nunca. Con 6 peticiones concurrentes sobre un tier de 60/min, un
unico reflejo de trafico agotaba la cuota y no habia forma de recuperarse
dentro de la misma corrida.

    Reintenta solo 429 y 5xx: un 401/403/404 es un problema de configuracion o
    de entitlement y reintentar solo gasta cuota.
    """
    import httpx

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = await fetch()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            if attempt >= max_retries:
                raise
            await asyncio.sleep(min(base_seconds * (2**attempt), cap_seconds))
            continue

        status = getattr(response, "status_code", 200)
        if status == 429 and attempt < max_retries:
            await asyncio.sleep(
                max(retry_after_seconds(response), base_seconds * (2**attempt))
            )
            continue
        if status >= 500 and attempt < max_retries:
            await asyncio.sleep(min(base_seconds * (2**attempt), cap_seconds))
            continue
        if status == 429:
            raise UpstreamRateLimited(
                f"upstream rate limited after {max_retries} retries"
            )
        response.raise_for_status()
        return response

    if last_exc is not None:  # pragma: no cover - solo por tipos
        raise last_exc
    raise RuntimeError("unreachable")  # pragma: no cover


@dataclass(slots=True)
class ConnectorItem:
    """Provider-neutral item returned by every polling connector."""

    source: str
    title: str
    url: str | None = None
    summary: str = ""
    published_at: datetime | None = None
    ticker: str | None = None
    item_type: str = "news"
    external_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "ticker": self.ticker,
            "item_type": self.item_type,
            "external_id": self.external_id,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class ConnectorResult:
    """Shared polling result that preserves partial failures and diagnostics."""

    source: str
    items: list[ConnectorItem] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def connector(self) -> str:
        return self.source

    @property
    def status(self) -> str:
        if self.errors and self.items:
            return "partial"
        if self.errors:
            return "error"
        return "ok"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat(),
            "items": [item.as_dict() for item in self.items],
            "errors": list(self.errors),
            "metadata": self.metadata,
        }

    @classmethod
    def failed(
        cls,
        source: str,
        error: Exception | str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> ConnectorResult:
        return cls(source=source, errors=[str(error)], metadata=metadata or {})
