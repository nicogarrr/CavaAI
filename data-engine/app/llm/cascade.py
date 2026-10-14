from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from app.llm.base import LLMProvider
from app.llm.contracts import LLMRequest, LLMResponse
from app.llm.errors import (
    LLMError,
    ProviderDisabledError,
    ProviderHTTPError,
    ProviderResponseError,
    ProviderTransportError,
)
from app.llm.routing import TaskModelRouter

logger = logging.getLogger(__name__)

#: Errores del PROVEEDOR (caida, cuota, clave, respuesta ilegible): se pasa al
#: siguiente. Un `ProviderRequestError` es un fallo NUESTRO (peticion mal
#: construida) y se propaga: otro proveedor recibiria la misma peticion mala.
_FALL_THROUGH = (ProviderHTTPError, ProviderTransportError, ProviderResponseError, ProviderDisabledError)


class CascadeProvider(LLMProvider):
    """Prueba varios proveedores en orden y devuelve la primera respuesta valida.

    Pensado para la cascada gratuita (Gemini AI Studio, OpenRouter :free,
    OpenCode): los topes diarios y las caidas puntuales de un proveedor no
    paran la aplicacion. Cada miembro lleva sus propios reintentos, modelo y
    cache; aqui solo se decide el orden y el tope total.

    - Cada intento fallido deja un aviso con el nombre del proveedor y la CLASE
      de error (nunca el mensaje, la URL ni cabeceras).
    - `total_timeout_seconds` acota TODA la cascada; al agotarse se lanza
      `ProviderTransportError` en lugar de seguir probando.
    - Si todos fallan se relanza el ultimo error y los anteriores quedan en el
      log; no se inventa una respuesta.
    """

    name = "cascade"

    def __init__(self, members: Sequence[LLMProvider], *, total_timeout_seconds: float = 60.0) -> None:
        if not members:
            raise ValueError("CascadeProvider needs at least one member")
        if total_timeout_seconds <= 0:
            raise ValueError("total_timeout_seconds must be positive")
        self.members = tuple(members)
        self._total_timeout_seconds = total_timeout_seconds
        # Solo lo que TODOS los miembros saben hacer: una peticion con tools o
        # response_format no puede caer en un miembro que no lo envie.
        capabilities = frozenset.intersection(*(m.supported_capabilities for m in self.members))
        self.supported_capabilities = capabilities
        super().__init__(
            model_router=TaskModelRouter(default_model="cascade"),
            timeout_seconds=total_timeout_seconds,
            max_retries=0,
        )

    @property
    def member_names(self) -> list[str]:
        return [m.name for m in self.members]

    async def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            return await asyncio.wait_for(self._run(request), timeout=self._total_timeout_seconds)
        except TimeoutError:
            raise ProviderTransportError(self.name, "timeout", 1) from None

    async def _run(self, request: LLMRequest) -> LLMResponse:
        last: Exception | None = None
        for index, member in enumerate(self.members):
            try:
                return await member.complete(request)
            except _FALL_THROUGH as exc:
                last = exc
                logger.warning(
                    "LLM cascade: %s failed (%s); %s",
                    member.name,
                    type(exc).__name__,
                    "trying next provider" if index + 1 < len(self.members) else "no providers left",
                )
        assert last is not None
        if isinstance(last, LLMError):
            raise last
        raise ProviderResponseError("cascade: all providers failed")  # pragma: no cover

    def __repr__(self) -> str:
        return f"CascadeProvider(members={self.member_names!r})"
