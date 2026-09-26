"""F132: el memo de tesis no puede exponer rutas internas ni nombres de servicio.

El «Memorando completo» renderizaba líneas «Accion: ...» con rutas internas
(POST /api/news/ingest, GET /api/calendar/earnings, /documents/ingest-url) y
servicios (ManualTranscriptImportService.import_text): texto de operador que
el lector podía tomar por instrucciones. Las acciones pendientes ahora son
copy honesto orientado al lector.
"""

import re
from pathlib import Path

SERVICE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "thesis_evidence_service.py"
)

# Patrones que delatan texto de operador: rutas HTTP, verbos de API y
# nombres internos de servicio/metodo.
LEAK = re.compile(r"(/api/|\bPOST\b|\bGET\b|\bPUT\b|\bDELETE\b|\w+Service\.\w+|import_text)")


def _action_literals() -> list[str]:
    source = SERVICE.read_text(encoding="utf-8")
    return re.findall(r'action="([^"]+)"', source) + re.findall(
        r'action=([A-Z_]+)', source
    )


def test_pending_actions_are_reader_facing():
    actions = _action_literals()
    assert actions, "el escaner debe encontrar las acciones pendientes"
    for action in actions:
        if action.isupper():  # constante: se valida su valor aparte
            continue
        assert not LEAK.search(action), f"accion con texto interno: {action}"


# Promesas operativas que el sistema no cumple: el copy pendiente describe
# el hueco y la capacidad real (presente), nunca acciones futuras inventadas.
FALSE_PROMISE = re.compile(
    r"se (ampliar|añadir|incorporar|reintentar|actualizar|podr)[a-záéíóú]*"
    r"|próxima actualización automática",
    re.IGNORECASE,
)


def test_pending_actions_make_no_false_promises():
    for action in _action_literals():
        if action.isupper():
            continue
        assert not FALSE_PROMISE.search(action), f"promesa inventada: {action}"


def test_external_thesis_howto_has_no_routes():
    from app.services.thesis_evidence_service import EXTERNAL_THESIS_HOWTO

    assert not LEAK.search(EXTERNAL_THESIS_HOWTO), EXTERNAL_THESIS_HOWTO
