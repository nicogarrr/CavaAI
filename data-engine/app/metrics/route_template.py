"""Normalizacion de rutas para metricas (#E5).

El problema que resuelve: `/api/research/AAPL` y `/api/research/MSFT` son DOS
series para un store de time series (y dos para Prometheus) y UNA sola para un
humano. Y si se etiqueta con la URL cruda, un escaner que hitpee 10.000 rutas
crea 10.000 series y tumba el store. Aqui hay tres defences, en este orden:

1. **La plantilla del route.** FastAPI deja en `scope["route"]` el `APIRoute`
   que ha resuelto la peticion, y `.path` ya viene con los parametros como
   `{ticker}`. Es la fuente de verdad y no hay que adivinar nada.
2. **Un normalizador de segmentos** para cuando no hay route (404, sub-app
   montada, ruta de exception): sustituye ids, UUIDs, hashes, fechas y tickers
   por marcadores. Los literales de ruta del repo son minusculas, asi que un
   ticker (`AAPL`, `BRK-B`) solo aparece en mayusculas.
3. **Un techo de cardinalidad** (`config.MAX_ROUTE_SERIES`): a partir de ese
   numero de plantillas distintas, todo lo nuevo cae en `__overflow__`. Es una
   perdida de informacion DELIBERADA y visible: prefiero un `__overflow__` con
   contador a un store reventado.

Lo que NUNCA sale de aqui: la query string completa (los tokens viajan en ella),
el cuerpo, ni ningun otro valor del path que no sea el marcador de una plantilla
de route.
"""

from __future__ import annotations

import re
from collections import OrderedDict

from app.metrics import config

ID_PLACEHOLDER = "{id}"
TICKER_PLACEHOLDER = "{ticker}"
UUID_PLACEHOLDER = "{uuid}"
HASH_PLACEHOLDER = "{hash}"
DATE_PLACEHOLDER = "{date}"
OVERFLOW_ROUTE = "__overflow__"
UNMATCHED_ROUTE = "__unmatched__"

MAX_TEMPLATE_LENGTH = 200
MAX_SEGMENTS = 12

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_HASH_RE = re.compile(r"^[0-9a-f]{16,}$", re.I)
_DIGITS_RE = re.compile(r"^\d+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Ticker: 1-6 mayusculas, opcionalmente con sufijo de clase (BRK.B, BRK-B,
# VOD.L). Deliberadamente NO acepta minusculas: los literales de ruta del
# repo ("list", "news", "metrics") son minusculas y deben seguir siendo rutas
# distintas y no un {ticker} inflado.
_TICKER_RE = re.compile(r"^[A-Z]{1,6}(?:[.\-][A-Z0-9]{1,4})?$")


def normalize_segment(segment: str) -> str:
    """Un segmento de path -> marcador estable, o el propio literal."""
    if not segment:
        return segment
    if _UUID_RE.match(segment):
        return UUID_PLACEHOLDER
    if _DATE_RE.match(segment):
        return DATE_PLACEHOLDER
    if _DIGITS_RE.match(segment):
        return ID_PLACEHOLDER
    if _TICKER_RE.match(segment):
        return TICKER_PLACEHOLDER
    if _HASH_RE.match(segment):
        return HASH_PLACEHOLDER
    return segment


def normalize_path(path: str) -> str:
    """Plantilla de ruta a partir de un path crudo, sin query string.

    `/api/research/AAPL` -> `/api/research/{ticker}`. Los literales de ruta del
    repo sobreviven intactos, asi que la mayoria de las series son las mismas
    rutas que veria un humano.
    """
    if not path:
        return UNMATCHED_ROUTE
    # La query string nunca se propaga: es donde viajan los tokens.
    raw = path.split("?", 1)[0].split("#", 1)[0]
    if not raw.startswith("/"):
        raw = "/" + raw
    parts = [part for part in raw.split("/") if part]
    if not parts:
        return "/"
    if len(parts) > MAX_SEGMENTS:
        # Pathologically deep (escaneo de fuzzing): se trunca en vez de
        # inventar una serie por profundidad.
        normalized = [normalize_segment(part) for part in parts[:MAX_SEGMENTS]]
        template = "/" + "/".join(normalized) + "/__deep__"
    else:
        template = "/" + "/".join(normalize_segment(part) for part in parts)
    if len(template) > MAX_TEMPLATE_LENGTH:
        template = template[:MAX_TEMPLATE_LENGTH]
    return template


def template_from_scope(scope: dict) -> str | None:
    """Plantilla declarada por el route que resolvio la peticion, si la hay."""
    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path[:MAX_TEMPLATE_LENGTH]
    # Sub-app montada (`root_path`): el inner scope lleva el match final.
    inner = scope.get("inner_scope")
    if isinstance(inner, dict):
        return template_from_scope(inner)
    return None


def route_template(scope: dict, fallback_path: str) -> str:
    """Plantilla de ruta de una peticion, con degradacion explicita."""
    declared = template_from_scope(scope)
    if declared:
        return declared
    normalized = normalize_path(fallback_path)
    return normalized if normalized else UNMATCHED_ROUTE


class CardinalityGuard:
    """LRU de plantillas vistas por ventana, con techo de cardinalidad.

    Vive por proceso y es deliberadamente *lossy* a proposito: cuando se llena,
    `allow` deja de aceptar plantillas nuevas y el llamante las colapsa a
    `__overflow__`. Un tracker exacto seria una tabla de rutas ilimitada en
    memoria, que es el problema que estamos evitando.
    """

    def __init__(self, max_series: int | None = None) -> None:
        self._max = max_series or config.max_route_series()
        self._seen: OrderedDict[str, None] = OrderedDict()

    @property
    def max_series(self) -> int:
        return self._max

    @property
    def tracked(self) -> int:
        return len(self._seen)

    def allow(self, template: str) -> str:
        """La plantilla si cabe en la cardinalidad; `__overflow__` si no."""
        if template in self._seen:
            self._seen.move_to_end(template)
            return template
        if len(self._seen) >= self._max:
            return OVERFLOW_ROUTE
        self._seen[template] = None
        return template

    def reset(self) -> None:
        self._seen.clear()