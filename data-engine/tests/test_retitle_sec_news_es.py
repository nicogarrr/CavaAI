"""Lógica pura del script de saneado de titulares SEC (quick win UX 4)."""
from types import SimpleNamespace

from scripts.retitle_sec_news_es import (
    _english_pattern,
    _new_title,
    _strip_ticker_prefixes,
)


def _row(title: str, headline: str | None = None) -> SimpleNamespace:
    metadata = {"source_headline": headline} if headline else {}
    return SimpleNamespace(title=title, metadata_=metadata)


def test_patron_ingles_estricto():
    assert _english_pattern("COST 8-K (2026-09-24)")
    assert _english_pattern("8-K filed 2026-09-24")
    assert not _english_pattern("COST 8-K presentado ante la SEC")
    assert not _english_pattern("Apple anuncia resultados")


def test_quita_doble_prefijo_de_ticker():
    assert _strip_ticker_prefixes("COST COST 8-K (2026-09-24)", "COST") == "8-K (2026-09-24)"
    assert _strip_ticker_prefixes("COST 8-K (2026-09-24)", "COST") == "8-K (2026-09-24)"
    # Límite de palabra implícito: «COSTCO» no es el ticker «COST».
    assert _strip_ticker_prefixes("COSTCO sube", "COST") == "COSTCO sube"


def test_titulo_destino_con_form_y_prefijo_unico():
    row = _row("COST COST 8-K (2026-09-24)", "COST 8-K (2026-09-24)")
    assert _new_title(row, "COST") == "COST 8-K presentado ante la SEC"
    row = _row("8-K filed 2026-09-24")
    assert _new_title(row, "NFLX") == "NFLX 8-K presentado ante la SEC"


def test_form_desconocido_no_se_inventa():
    # Patrón inglés claro pero form irreconocible: «filing», nunca un form fabricado.
    row = _row("XYZ-9 weird (2026-09-24)")
    assert _new_title(row, "") == "filing presentado ante la SEC"


def test_sin_patron_ingles_no_se_toca():
    row = _row("Apple anuncia resultados trimestrales")
    assert _new_title(row, "AAPL") is None
