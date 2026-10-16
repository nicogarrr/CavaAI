"""Closed public-concept boundary for Groq. No raw user/context forwarding."""
from __future__ import annotations

import re
import unicodedata

# A closed vocabulary deliberately favors false negatives over private disclosure.
_CONCEPTS = {
    "per": "PER", "ebitda": "EBITDA", "etf": "ETF", "dividendo": "dividendo",
    "dividendos": "dividendo", "deuda": "deuda", "ingresos": "ingresos",
    "revenue": "ingresos", "rentabilidad": "rentabilidad", "beneficio": "beneficio",
    "beneficios": "beneficio", "margen": "margen", "inflacion": "inflación",
    "interes compuesto": "interés compuesto", "diversificacion": "diversificación",
    "precio de mercado": "precio de mercado", "capitalizacion bursatil": "capitalización bursátil",
}
_PREFIX = r"(?:que es|que son|que significa|como funciona|como se calcula|explica|explicame|define|what is|how does) "


def canonical_concept(question: str) -> str | None:
    value = "".join(c for c in unicodedata.normalize("NFKD", question.lower()) if not unicodedata.combining(c))
    value = re.sub(r"^[¿¡\s]+|[?!.\s]+$", "", value)
    value = re.sub(r"\s+", " ", value)
    match = re.fullmatch(_PREFIX + r"(?:(?:el|la|los|las|un|una|the|an|a) )?(.+?)(?: work)?", value)
    return _CONCEPTS.get(match.group(1)) if match else None


def educational_output(text: str) -> bool:
    value = "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))
    # No individualized language, transactions, trade/allocation advice or links.
    forbidden = r"\b(?:tu|tus|usted|ustedes|your|you|cartera|portfolio|recom\w*|aconsej\w*|invert\w*|invest\w*|aument\w*|reduc\w*|debes|deberia\w*|conviene|mejor|ought|must|favor\w*|compr\w*|vend\w*|vender|buy\w*|sell\w*|should|deberias|asign\w*|allocat\w*)\b|https?://"
    return bool(text.strip()) and re.search(forbidden, value) is None
