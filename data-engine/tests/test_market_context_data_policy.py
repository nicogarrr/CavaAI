"""La politica de market context y el codigo no pueden separarse.

Este test ata `docs/market-context-data-policy.md` al comportamiento real: cada
motivo de no disponibilidad documentado tiene que existir en el codigo, y cada
motivo que el codigo puede devolver tiene que estar documentado. Sin esto, un
"sin datos" nuevo aparece en produccion sin que nadie sepa que afirmaba.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.services.connectors import sp500_factsheet
from app.services.market_regime_quant import (
    SP500_FACTSHEET_MAX_AGE_DAYS,
    sp500_top_ten_concentration,
)

DOC = Path(__file__).resolve().parents[1] / "docs" / "market-context-data-policy.md"

# Motivos que puede devolver la metrica: los de no disponibilidad del conector,
# mas los dos propios de la politica de vintage/pesos.
METRIC_REASONS = {
    sp500_factsheet.REASON_DIR_NOT_CONFIGURED,
    sp500_factsheet.REASON_NO_SNAPSHOT,
    sp500_factsheet.REASON_VINTAGE_AFTER,
    sp500_factsheet.REASON_INTEGRITY,
    sp500_factsheet.REASON_INVALID_DATE,
    "index_weights_not_published_by_source",
    "snapshot_too_stale_for_requested_date",
}


def test_the_policy_document_exists_and_is_about_this_data():
    assert DOC.is_file()
    text = DOC.read_text()
    assert "Market context data policy" in text
    # Los seis datos de FRED siguen siendo la politica vigente.
    for series in ("MORTGAGE30US", "DGS10", "DGS2", "T10YIE", "BAMLH0A0HYM2", "VIXCLS"):
        assert series in text
    # Y los backfills de FRED siguen sin poder presentarse como point-in-time.
    assert "must **not** be presented as" in text


def test_the_old_permanently_unavailable_claim_is_gone():
    """La frase que hacia top-10 'permanentemente no disponible' ya no aplica."""
    text = DOC.read_text()
    assert "remains\nunavailable until a complete dated" not in text
    assert "no longer permanently unavailable" in text


def test_every_documented_reason_exists_in_the_code_and_viceversa():
    text = DOC.read_text()
    documented = set(
        re.findall(
            r"`(snapshot_[a-z_]+|no_snapshot_in_disk|requested_date_invalid|index_weights_not_published_by_source)`",
            text,
        )
    )

    assert documented == METRIC_REASONS, (
        f"documentados={sorted(documented)} codigo={sorted(METRIC_REASONS)}"
    )


def test_the_documented_source_tier_and_opt_in_match_the_connector():
    text = DOC.read_text()
    assert f"`{sp500_factsheet.SOURCE_TIER}`" in text
    assert sp500_factsheet.SNAPSHOT_DIR_ENV in text
    assert f"{SP500_FACTSHEET_MAX_AGE_DAYS} days" in text
    assert "https://www.spglobal.com/spdji/en/indices/equity/sp-500/" in text
    # El tier y el ambito de licencia viajan en el dato, no en un comentario.
    assert sp500_factsheet.SOURCE_SCOPE == "aggregate_index_characteristics_only"


def test_the_worked_example_matches_the_built_snapshots():
    """El ejemplo concreto del doc tiene que ser el que sale del codigo."""
    text = DOC.read_text()
    directory = Path(__file__).resolve().parents[1] / "data" / "sp500_factsheet_snapshots"
    if not directory.exists():
        # data/ esta en .gitignore: los snapshots se generan con el script.
        return
    import json

    manifest = json.loads((directory / "manifest.json").read_text())
    as_ofs = {declared["as_of"] for declared in manifest["snapshots"].values()}
    for as_of in as_ofs:
        assert as_of in text, f"el doc no menciona el snapshot {as_of} construido"
    august = next(
        payload for _, payload in _payloads(directory) if payload["as_of"] == "2026-08-31"
    )
    assert str(august["metrics"]["weight_top_ten_pct"]) in text
    june = next(payload for _, payload in _payloads(directory) if payload["as_of"] == "2026-06-30")
    assert str(june["metrics"]["weight_top_ten_pct"]) in text
    assert str(august["metrics"]["constituents"]) in text


def _payloads(directory: Path):
    import json

    manifest = json.loads((directory / "manifest.json").read_text())
    for relative in manifest["snapshots"]:
        yield relative, json.loads((directory / relative).read_text())


def test_the_metric_is_the_only_way_concentration_reaches_the_snapshot():
    """Guardarrail: la metrica no puede responder sin fecha ni con peso inventado."""
    unavailable = sp500_top_ten_concentration(None)
    assert unavailable["status"] == "sin datos"
    assert unavailable["reason"] == sp500_factsheet.REASON_INVALID_DATE
    assert "fraction" not in unavailable
