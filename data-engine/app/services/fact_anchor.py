"""Anclaje verificable de un dato extraido a la frase exacta del filing.

Regla de la casa: ningun dato extraido se presenta sin su ancla (filing,
documento, sha256 del cuerpo, cita literal y desplazamiento). "Found word for
word" o no se publica. Lo inferido se etiqueta INFERIDO; la ausencia de dato
no produce ancla (nunca un 0 ni una cadena vacia).

El ancla la construye `build_anchor` y solo desde el documento: el extractor
aporta la cita y el valor, pero el sha256 y el desplazamiento se calculan
aqui, de modo que ningun caller puede declarar una procedencia falsa.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

LABEL_OFICIAL = "OFICIAL"
LABEL_INFERIDO = "INFERIDO"
LABELS = (LABEL_OFICIAL, LABEL_INFERIDO)


class FactAnchorError(ValueError):
    """El ancla no es verificable contra el documento."""


def sha256_text(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def locate_quote(body: str, quote: str) -> list[int]:
    """Todos los desplazamientos donde aparece la cita, literal y exacta."""
    if not quote:
        raise FactAnchorError("La cita no puede ser vacia")
    offsets: list[int] = []
    start = 0
    while True:
        idx = body.find(quote, start)
        if idx < 0:
            return offsets
        offsets.append(idx)
        start = idx + 1


def locate_unique(body: str, quote: str) -> int:
    """El desplazamiento de la cita, exigiendo que sea unica en el documento."""
    offsets = locate_quote(body, quote)
    if not offsets:
        raise FactAnchorError("La cita no aparece literalmente en el documento")
    if len(offsets) > 1:
        raise FactAnchorError(
            f"La cita aparece {len(offsets)} veces; amplia el contexto para que sea unica"
        )
    return offsets[0]


_ITEM_RE = re.compile(r"(?im)^[ \t]*item[ \t]+(\d+\.\d{2}[a-z]?)[\s.:]")


def item_for_offset(body: str, offset: int) -> str | None:
    """Ultimo encabezado "Item X.YZ" estrictamente anterior; None si no hay.

    Best effort estructural: nunca inventa un item. El offset del propio
    encabezado no cuenta como contenido de ese item.
    """
    if not 0 <= offset <= len(body):
        raise FactAnchorError("Desplazamiento fuera del documento")
    found: str | None = None
    for match in _ITEM_RE.finditer(body, 0, offset):
        found = match.group(1)
    return f"Item {found}" if found else None


@dataclass(frozen=True)
class FactAnchorSpec:
    """Provenance de un dato: donde esta, literalmente, y con que etiqueta."""

    accession: str
    filename: str
    body_sha256: str
    field: str
    value_text: str
    label: str
    quote: str
    quote_offset: int
    item: str | None
    extractor: str


def build_anchor(
    *,
    body: str,
    accession: str,
    filename: str,
    field: str,
    value_text: str,
    label: str,
    quote: str,
    extractor: str,
    item: str | None = None,
) -> FactAnchorSpec:
    """Construye el ancla calculando sha256/offset desde el documento."""
    if label not in LABELS:
        raise FactAnchorError(f"Etiqueta desconocida: {label!r} (usa {LABELS})")
    if not field.strip():
        raise FactAnchorError("El campo no puede ser vacio")
    if not value_text.strip():
        raise FactAnchorError(
            "El valor no puede ser vacio: sin dato no hay ancla (nunca 0)"
        )
    offset = locate_unique(body, quote)
    return FactAnchorSpec(
        accession=accession,
        filename=filename,
        body_sha256=sha256_text(body),
        field=field.strip(),
        value_text=value_text,
        label=label,
        quote=quote,
        quote_offset=offset,
        item=item if item is not None else item_for_offset(body, offset),
        extractor=extractor,
    )


def verify_anchor(body: str, anchor: FactAnchorSpec) -> bool:
    """Re-verifica un ancla contra el documento: sha y cita en su sitio."""
    if sha256_text(body) != anchor.body_sha256:
        return False
    end = anchor.quote_offset + len(anchor.quote)
    return body[anchor.quote_offset : end] == anchor.quote
