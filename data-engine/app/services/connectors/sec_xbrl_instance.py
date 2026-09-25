"""Parser de instancias XBRL de EDGAR (fichero *_htm.xml de un filing).

La API companyfacts excluye hechos con dimensiones: los filers por clases
(Visa, Berkshire, ...) declaran EPS/acciones por clase y la API gratuita se
queda sin ellos. Este parser lee la instancia XBRL del filing y recupera
esos hechos CON su miembro dimensional, sin inventar nada: solo lo que el
emisor declaro, con su contexto (periodo + miembro).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

# Tags XBRL (nombre local) que alimentan cada metrica interna. Los "basic"
# solo se usan cuando el emisor no declara el diluido (Berkshire no tiene
# dilucion); el tag real usado queda en la procedencia.
METRIC_TAGS: dict[str, tuple[str, ...]] = {
    "eps_diluted": ("EarningsPerShareDiluted", "EarningsPerShareBasic"),
    "shares_diluted": (
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ),
}

_ALL_TAGS = {tag for tags in METRIC_TAGS.values() for tag in tags}


@dataclass(frozen=True)
class DimensionedFact:
    tag: str
    value: Decimal
    start: date | None
    end: date | None
    instant: date | None
    members: tuple[str, ...] = field(default_factory=tuple)

    @property
    def duration_days(self) -> int | None:
        if self.start is None or self.end is None:
            return None
        return (self.end - self.start).days


def _local(name: str) -> str:
    return name.split("}")[-1].split(":")[-1]


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def parse_instance_dimensioned_facts(
    stream,
    *,
    min_days: int = 300,
    max_days: int = 380,
) -> list[DimensionedFact]:
    """Hechos con dimension de miembro y duracion anual de una instancia XBRL.

    Solo devuelve hechos que llevan al menos un explicitMember (los sin
    dimension ya los cubre companyfacts) y con duracion dentro de
    [min_days, max_days] (anual; absorbe anos de 52/53 semanas). Valores no
    numericos o no finitos se descartan: nunca llegan a la BD.
    """
    contexts: dict[str, tuple[date | None, date | None, date | None, tuple[str, ...]]] = {}
    facts: list[DimensionedFact] = []
    for _event, el in ET.iterparse(stream):
        tag = _local(el.tag)
        if tag == "context":
            members = tuple(
                _local(m.text) for m in el.iter() if _local(m.tag) == "explicitMember" and m.text
            )
            start = end = instant = None
            for node in el.iter():
                node_tag = _local(node.tag)
                if node_tag == "startDate":
                    start = _parse_date(node.text)
                elif node_tag == "endDate":
                    end = _parse_date(node.text)
                elif node_tag == "instant":
                    instant = _parse_date(node.text)
            contexts[el.get("id") or ""] = (start, end, instant, members)
            el.clear()
        elif tag in _ALL_TAGS:
            raw = (el.text or "").strip()
            try:
                value = Decimal(raw)
            except (InvalidOperation, ValueError):
                el.clear()
                continue
            if not value.is_finite():
                el.clear()
                continue
            start, end, instant, members = contexts.get(
                el.get("contextRef") or "", (None, None, None, ())
            )
            if members:
                facts.append(
                    DimensionedFact(
                        tag=tag,
                        value=value,
                        start=start,
                        end=end,
                        instant=instant,
                        members=members,
                    )
                )
            el.clear()
    if min_days is not None or max_days is not None:
        facts = [
            f
            for f in facts
            if f.duration_days is not None
            and (min_days is None or f.duration_days >= min_days)
            and (max_days is None or f.duration_days <= max_days)
        ]
    return facts
