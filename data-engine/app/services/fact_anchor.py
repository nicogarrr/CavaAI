"""Base para provenance a nivel dato: anclaje verificable a la frase exacta.

FASE A - cimiento restringido. Lo que este modulo SI garantiza:
- la cita existe literalmente y una sola vez en el documento aportado;
- el sha256 y el desplazamiento los calcula el builder, nunca el caller;
- OFICIAL significa "el valor aparece literal en la cita de ESTE documento";
  INFERIDO exige una derivacion trazable (metodo + inputs);
- verify_anchor revalida TODO el ancla contra el documento.

Lo que NO garantiza (limites declarados): el hash local no certifica emisor,
empresa ni URL primaria (eso es trabajo de sec_filing_evidence); OFICIAL no es
veracidad financiera; verify_anchor no entiende el significado del valor.
La ausencia de dato no produce ancla (nunca un 0 ni una cadena vacia).
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
    derivation: str | None


def _require_text(name: str, value: str) -> str:
    if not value or not value.strip():
        raise FactAnchorError(f"{name} no puede ser vacio")
    return value.strip()


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
    derivation: str | None = None,
) -> FactAnchorSpec:
    """Construye el ancla calculando sha256/offset/item desde el documento.

    OFICIAL exige que el valor aparezca literal en la cita; si el valor se
    deriva (normalizacion, calculo, otra parte del documento), la etiqueta
    correcta es INFERIDO y hay que aportar `derivation` (metodo + inputs).
    Un `item` aportado por el caller debe coincidir con la estructura real.
    """
    accession = _require_text("accession", accession)
    filename = _require_text("filename", filename)
    field = _require_text("field", field)
    extractor = _require_text("extractor", extractor)
    if not value_text or not value_text.strip():
        raise FactAnchorError(
            "El valor no puede ser vacio: sin dato no hay ancla (nunca 0)"
        )
    if label not in LABELS:
        raise FactAnchorError(f"Etiqueta desconocida: {label!r} (usa {LABELS})")
    offset = locate_unique(body, quote)
    computed_item = item_for_offset(body, offset)
    if item is not None and item != computed_item:
        raise FactAnchorError(
            f"El item declarado ({item!r}) contradice la estructura del documento "
            f"({computed_item!r})"
        )
    if label == LABEL_OFICIAL:
        if value_text not in quote:
            raise FactAnchorError(
                "OFICIAL exige el valor literal en la cita; si el valor se deriva, "
                "etiqueta INFERIDO y aporta derivation"
            )
    elif derivation is None or not derivation.strip():
        raise FactAnchorError(
            "INFERIDO exige derivation trazable (metodo + inputs del calculo)"
        )
    return FactAnchorSpec(
        accession=accession,
        filename=filename,
        body_sha256=sha256_text(body),
        field=field,
        value_text=value_text,
        label=label,
        quote=quote,
        quote_offset=offset,
        item=computed_item,
        extractor=extractor,
        derivation=derivation.strip() if derivation else None,
    )


def verify_anchor(body: str, anchor: FactAnchorSpec) -> bool:
    """Revalida TODO el ancla contra el documento. False ante cualquier duda."""
    try:
        if anchor.label not in LABELS:
            return False
        for value in (
            anchor.accession,
            anchor.filename,
            anchor.field,
            anchor.value_text,
            anchor.quote,
            anchor.extractor,
        ):
            if not value or not value.strip():
                return False
        if anchor.label == LABEL_INFERIDO and not (
            anchor.derivation and anchor.derivation.strip()
        ):
            return False
        if (
            not isinstance(anchor.quote_offset, int)
            or anchor.quote_offset < 0
            or anchor.quote_offset > len(body)
        ):
            return False
        if sha256_text(body) != anchor.body_sha256:
            return False
        end = anchor.quote_offset + len(anchor.quote)
        if body[anchor.quote_offset : end] != anchor.quote:
            return False
        if len(locate_quote(body, anchor.quote)) != 1:
            return False
        if anchor.item != item_for_offset(body, anchor.quote_offset):
            return False
        if anchor.label == LABEL_OFICIAL and anchor.value_text not in anchor.quote:
            return False
    except (FactAnchorError, TypeError):
        return False
    return True
