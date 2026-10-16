"""Registro cerrado de lecturas. Preparación interna; todavía no conectado al chat.

El contexto y la autorización vienen del servidor, nunca del JSON del modelo.
No hay red, SQL, shell ni herramientas con efectos en este módulo.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.llm.contracts import ToolCall, ToolDefinition

_ALLOWED = frozenset({"company_facts", "company_thesis", "company_news", "company_documents"})
_MAX_RESULT_BYTES = 32_768


class ReadToolError(ValueError):
    """Error estable sin contenido privado ni argumentos crudos."""


class ReadArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    ticker: str = Field(min_length=1, max_length=24, pattern=r"^[A-Z0-9][A-Z0-9.^:-]*$")
    limit: int = Field(default=8, ge=1, le=100)


@dataclass(frozen=True, slots=True)
class ReadContext:
    principal_id: str
    tenant_id: str

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) and value.strip() for value in (self.principal_id, self.tenant_id)):
            raise ValueError("Se requiere identidad y tenant del servidor")


@dataclass(frozen=True, slots=True)
class ReadResult:
    source_id: str
    as_of: datetime
    data: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ReadToolError("Resultado sin fuente")
        if not isinstance(self.as_of, datetime) or self.as_of.utcoffset() is None:
            raise ReadToolError("Resultado sin fecha con zona horaria")
        if not isinstance(self.data, Mapping):
            raise ReadToolError("Resultado no estructurado")
        try:
            encoded = json.dumps(dict(self.data), allow_nan=False, ensure_ascii=False).encode("utf-8")
        except (ValueError, TypeError, RecursionError):
            raise ReadToolError("Resultado no serializable") from None
        if len(encoded) > _MAX_RESULT_BYTES:
            raise ReadToolError("Resultado excede el presupuesto")
        # Copia separada del objeto mutable que retiene el handler.
        object.__setattr__(self, "data", json.loads(encoded))


ReadHandler = Callable[[ReadContext, ReadArguments], Awaitable[ReadResult]]
Authorizer = Callable[[ReadContext, str, ReadArguments], bool]


class ReadRegistry:
    """Solo handlers internos registrados por código de confianza.

    El authorizer debe comprobar acceso al tenant y al recurso en CADA llamada.
    Este contrato no sustituye las comprobaciones de permisos del servicio.
    """

    def __init__(self, *, handlers: Mapping[str, ReadHandler], authorize: Authorizer) -> None:
        if set(handlers) - _ALLOWED or any(not callable(handler) for handler in handlers.values()):
            raise ValueError("Herramienta no permitida")
        if not callable(authorize):
            raise ValueError("Se requiere autorización del servidor")
        self._handlers = dict(handlers)
        self._authorize = authorize

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(
            ToolDefinition(
                name=name,
                description="Lectura acotada de datos existentes con fuente y fecha. No ejecuta acciones.",
                parameters=ReadArguments.model_json_schema(),
            )
            for name in sorted(self._handlers)
        )

    async def execute(self, context: ReadContext, call: ToolCall) -> ReadResult:
        handler = self._handlers.get(call.name)
        if handler is None:
            raise ReadToolError("Herramienta no disponible")
        try:
            arguments = ReadArguments.model_validate(dict(call.arguments))
        except ValidationError:
            raise ReadToolError("Argumentos inválidos") from None
        if self._authorize(context, call.name, arguments) is not True:
            raise ReadToolError("Lectura no autorizada")
        result = await handler(context, arguments)
        if not isinstance(result, ReadResult):
            raise ReadToolError("Resultado sin contrato")
        # Revalidar también tras la ejecución: un handler no puede mutar datos
        # después de construir el objeto y saltarse el límite o el JSON estricto.
        return ReadResult(source_id=result.source_id, as_of=result.as_of, data=result.data)
