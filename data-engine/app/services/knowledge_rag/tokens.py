"""Conteo de wordpieces del embedder (all-MiniLM-L6-v2 trunca a 256)."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

# Incluye [CLS] y [SEP]: el limite de 256 del modelo los cuenta.
MODEL_MAX_WORDPIECES = 256

TokenCounter = Callable[[str], int]

_WORDISH = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def heuristic_counter(text: str) -> int:
    """Cota CONSERVADORA sin modelo: palabras+signos x1.3 (subwords) + 2 especiales.

    Solo fallback: sobrestima a proposito para que un chunk nunca se trunque en
    silencio. Con el tokenizer real (``wordpiece_counter``) el conteo es exacto.
    """
    return int(len(_WORDISH.findall(text)) * 1.3) + 2


def wordpiece_counter(model: str = "sentence-transformers/all-MiniLM-L6-v2") -> TokenCounter:
    """Contador exacto con el tokenizer que fastembed ya descargo para el modelo.

    No descarga nada extra: reutiliza el tokenizer.json del modelo denso (el
    mismo que usa la ingesta). Si no esta disponible cae al heuristico.
    """
    try:
        from fastembed import TextEmbedding  # noqa: I001
        from tokenizers import Tokenizer

        from app.services.hybrid_retrieval import _cached_model

        embedder: Any = _cached_model("dense", TextEmbedding, model)
        shared = embedder.model.tokenizer
        # Copia: nunca mutar el tokenizer compartido con el embedder.
        tokenizer = Tokenizer.from_str(shared.to_str())
        tokenizer.no_truncation()
        tokenizer.no_padding()

        def count(text: str) -> int:
            return len(tokenizer.encode(text, add_special_tokens=True).ids)

        count("warmup")
        return count
    except Exception:  # noqa: BLE001 - degradacion explicita al heuristico
        return heuristic_counter
