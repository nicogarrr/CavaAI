"""Cadenas visibles de revisiones, hallazgos y alertas (UI en español).

Estos textos se persisten como títulos/resúmenes de ResearchReview y como
títulos/mensajes de alertas disparadas: los lee el usuario final en /inicio y
/alerts. Los códigos internos (review_type, change_type, status) siguen en
inglés canónico; lo que cambia es SOLO la representación legible.
"""

from __future__ import annotations

CHANGE_TYPE_LABELS: dict[str, str] = {
    "earnings_update": "actualización de resultados",
    "news_material_positive": "noticia material positiva",
    "news_material_update": "actualización material de noticias",
    "news_potential_invalidation": "posible invalidación por noticias",
    "claim_contradiction": "afirmación contradicha",
    "claim_superseded": "afirmación sustituida",
    "claim_stale": "afirmación desactualizada",
    "claim_uncertain": "afirmación incierta",
}

CLAIM_STATUS_LABELS: dict[str, str] = {
    "contradicted": "contradicha",
    "superseded": "sustituida",
    "stale": "desactualizada",
    "uncertain": "incierta",
    "supported": "respaldada",
}


def change_type_label(change_type: str) -> str:
    """Etiqueta legible del tipo de cambio; nunca expone el código crudo."""
    return CHANGE_TYPE_LABELS.get(change_type, "cambio en la tesis")


def claim_status_label(status: str) -> str:
    """Etiqueta legible del estado de una afirmación."""
    return CLAIM_STATUS_LABELS.get(status, "con estado desconocido")
