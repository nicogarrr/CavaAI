"""La descripcion de un split importado va en espanol y explica que hace Aplicar."""

from datetime import UTC, datetime

from app.services.split_ingestion_service import SplitIngestionService


def test_split_description_is_spanish_and_explains_apply():
    text = SplitIngestionService._description("yahoo_finance", 2.0, datetime(2026, 9, 25, tzinfo=UTC))
    assert text.startswith("División de acciones 2 por 1.")
    assert "Yahoo Finance" in text and "2026-09-25" in text
    assert "Aplicar ajusta" in text
    assert "Ingested" not in text


def test_reverse_split_description():
    text = SplitIngestionService._description("fmp", 0.1, datetime(2026, 9, 25, tzinfo=UTC))
    assert text.startswith("Agrupación de acciones 1 por 10.")
