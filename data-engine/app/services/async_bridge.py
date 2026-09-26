"""Ejecuta una corrutina desde contexto sync o desde un event loop en marcha.

`asyncio.run()` lanza `RuntimeError: asyncio.run() cannot be called from a
running event loop` cuando ya hay un loop activo en el hilo. Todos los
`except Exception` de los callers se lo comian, asi que la funcion Jev
(urgencia, tipo documental, gates de noticias) no se ejecutaba nunca desde
ninguna ruta async -ingesta de documentos, ingesta de noticias, workers- y
ademas grababa el RuntimeError en los metadatos que se persisten.

Aqui no se puede hacer otra cosa que ejecutar la corrutina en un hilo propio
con su propio loop: la firma es sync (los callers son sync y hay muchos) y
bloquear el loop en curso seria peor que el bug original.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")

_BRIDGE = ThreadPoolExecutor(max_workers=4, thread_name_prefix="cavaai-jev-bridge")


def run_from_any_context(coro: Coroutine[Any, Any, T], timeout: float | None = None) -> T:
    """Ejecuta ``coro`` tanto en codigo sync como dentro de un loop activo.

    Sin loop en marcha es un ``asyncio.run`` normal. Con loop activo, la
    corrutina corre en un hilo del pool con su propio event loop, de forma que
    no choca con el loop del llamador ni lo bloquea.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No hay loop en este hilo: es el caso sync normal.
        return asyncio.run(coro)

    future = _BRIDGE.submit(lambda: asyncio.run(coro))
    return future.result(timeout=timeout)
