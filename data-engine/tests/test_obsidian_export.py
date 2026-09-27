"""El ZIP es portable, sin fuentes sintéticas, y no mezcla tesis de tenants."""

import io
from zipfile import ZipFile

from app.services.obsidian_export import Note, Source, build_obsidian_zip


def test_zip_frontmatter_links_and_source_dates():
    payload = build_obsidian_zip(
        "SAN",
        [
            Note(
                "Tesis SAN v3",
                version=3,
                date="2026-09-23",
                status="draft",
                body="# Análisis",
                sources=[
                    Source(url="https://example.org/report(1)", date="2026-09-20", statement="Margen"),
                    Source(statement="Afirmación sin fuente"),
                ],
            ),
            Note("Tesis SAN v9", version=9, status="insufficient_data"),
        ],
    )
    with ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == {
            "CavaAI/SAN/SAN - Índice.md",
            "CavaAI/SAN/Tesis SAN v3.md",
            "CavaAI/SAN/Tesis SAN v9.md",
        }
        index = archive.read("CavaAI/SAN/SAN - Índice.md").decode()
        assert "[[Tesis SAN v9]]" in index and "[[Tesis SAN v3]]" in index
        v3 = archive.read("CavaAI/SAN/Tesis SAN v3.md").decode()
        assert 'fecha: "2026-09-23"' in v3
        assert 'fuentes:\n  - "https://example.org/report(1)"' in v3
        assert "[Fuente](<https://example.org/report(1)>) (2026-09-20)" in v3
        assert "Afirmación sin fuente: Sin datos de URL" in v3
        v9 = archive.read("CavaAI/SAN/Tesis SAN v9.md").decode()
        assert 'fecha: ""' in v9 and "Sin datos" in v9
        assert "fuentes: []" in v9


def test_invalid_ticker_does_not_escape_archive():
    import pytest

    with pytest.raises(ValueError):
        build_obsidian_zip("../evil", [Note("Unsafe")])
