"""C4: el corpus de ingesta es sintetico DECLARADO y tiene el esquema esperado.

Dos cosas se comprueban aqui:

1. Cada fixture declara su origen (`origin: synthetic_fixture` en JSON, comentario
   en XML) y tiene la forma que el harness y las puertas esperan.
2. Ningun valor monetario se cuela sin declararse. El corpus usa numeros
   redondos inventados para que un despliegue con cifras reales sea visible de
   un vistazo: `ALLOWED_VALUES` es la lista blanca completa, y cualquier
   magnitud fuera de ella hace fallar el test.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from evals.ingest import harness
from evals.ingest.ingest_gates import FAMILY_SOURCE_TYPES

FIXTURES = harness.FIXTURES
DATASET = harness.ROOT / "evals" / "ingest" / "ingest_v1.json"
ORIGIN = "synthetic_fixture"

REQUIRED_KEYS = {
    "sec/companyfacts_calendar_fy.json": ("facts",),
    "sec/submissions_calendar_fy.json": ("filings", "cik", "tickers"),
    "sec/index/verified.json": ("index_html", "index_sha256", "document", "document_sha256",
                                "document_url", "capture", "company", "accession"),
    "fmp/income_statement_history.json": ("endpoint", "rows"),
    "esef/xbrl_json_core.json": ("facts", "lei"),
    "esef/filings_page.json": ("data", "meta"),
    "esef/entity.json": ("data",),
}

# Todos los valores monetarios / ratios del corpus, con su procedencia. Cualquier
# numero fuera de esta lista es un valor sin declarar.
ALLOWED_VALUES = {
    # Magnitudes enteras del corpus (ingresos, activos, acciones, quotas).
    1_234_567, 2_000_000, 72_000_000, 80_000_000, 90_000_000, 96_000_000, 100_000_000, 110_000_000,
    120_000_000, 140_000_000, 150_000_000, 160_000_000, 180_000_000, 190_000_000, 200_000_000, 240_000_000,
    250_000_000, 260_000_000, 300_000_000, 400_000_000, 410_000_000, 420_000_000, 450_000_000, 460_000_000,
    470_000_000, 496_000_000, 500_000_000, 512_000_000, 520_000_000, 530_000_000, 550_000_000, 560_000_000,
    570_000_000, 600_000_000, 620_000_000, 700_000_000, 710_000_000, 720_000_000, 770_000_000, 800_000_000,
    820_000_000, 830_000_000, 880_000_000, 900_000_000, 999_000_000, 1_000_000_000, 1_100_000_000,
    1_143_000_000, 1_160_000_000, 1_170_000_000, 1_176_000_000, 1_200_000_000, 1_250_000_000, 1_260_000_000,
    1_400_000_000, 1_500_000_000, 1_600_000_000, 1_900_000_000, 2_000_000_000, 2_100_000_000, 2_268_000_000,
    2_300_000_000, 2_500_000_000, 2_520_000_000, 2_600_000_000, 3_000_000_000, 3_100_000_000, 4_000_000_000,
    4_100_000_000, 4_500_000_000, 4_520_000_000, 4_600_000_000, 4_800_000_000, 5_000_000_000, 5_100_000_000,
    5_300_000_000, 5_900_000_000, 6_500_000_000, 7_000_000_000, 7_100_000_000, 7_900_000_000, 8_000_000_000,
    8_400_000_000, 9_000_000_000, 19_000_000_000, 20_000_000_000, 21_000_000_000, 42_000_000_000,
    50_000_000_000, 99_000_000_000, 888_000_000_000, 999_000_000_000,
    # Ratios, BPA y precios por accion.
    0.1, 0.12, 0.14, 0.19, 0.25, 0.4, 0.48, 0.75, 0.95, 1.05, 1.15, 1.2, 1.25, 2.1, 3.5, 4.25, 42.37,
    # Contadores y centinelas pequenos que el corpus usa como flags.
    0, 1, 2, 3, 4, 5, 6, 10, 12, 14, 15, 19, 25, 37, 40, 42, 48, 50, 75, 95,
}

NUMBER_RE = re.compile(r">\s*(-?\d[\d.]*)\s*<")


def _json_files() -> list[Path]:
    return sorted(FIXTURES.rglob("*.json"))


def _all_files() -> list[Path]:
    return sorted(path for path in FIXTURES.rglob("*") if path.is_file())


def test_corpus_exists_and_is_not_empty():
    assert FIXTURES.is_dir()
    assert len(_all_files()) >= 40
    assert (FIXTURES / "README.md").exists()


def test_readme_declares_the_synthetic_origin():
    readme = (FIXTURES / "README.md").read_text(encoding="utf-8")
    assert ORIGIN in readme
    assert "sintetico" in readme.lower() or "sintético" in readme.lower()
    assert "ninguna cifra" in readme.lower() or "ningun valor" in readme.lower()


@pytest.mark.parametrize("path", _json_files(), ids=lambda p: p.name)
def test_every_json_fixture_declares_the_origin(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"{path.name} deberia ser un objeto con 'origin'"
    assert payload.get("origin") == ORIGIN, f"{path.name} no declara origin={ORIGIN}"


@pytest.mark.parametrize(
    "path", sorted(FIXTURES.rglob("*.xml")), ids=lambda p: p.name
)
def test_every_xml_fixture_declares_the_origin(path: Path):
    assert ORIGIN in path.read_text(encoding="utf-8")[:400]


@pytest.mark.parametrize("relative", sorted(REQUIRED_KEYS))
def test_required_fixture_keys(relative: str):
    payload = json.loads((FIXTURES / relative).read_text(encoding="utf-8"))
    for key in REQUIRED_KEYS[relative]:
        assert key in payload, f"{relative} no trae {key}"


def test_companyfacts_fixtures_have_the_us_gaap_shape():
    for path in sorted((FIXTURES / "sec").glob("companyfacts_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        facts = payload["facts"]
        assert "us-gaap" in facts, f"{path.name} no trae facts.us-gaap"
        for concept, body in facts["us-gaap"].items():
            assert isinstance(body, dict) and "units" in body, f"{path.name}:{concept}"
            for unit, entries in body["units"].items():
                assert isinstance(entries, list), f"{path.name}:{concept}:{unit}"
                for entry in entries:
                    assert "end" in entry, f"{path.name}:{concept} sin end"
                    assert "val" in entry, f"{path.name}:{concept} sin val (puede ser null)"
                    assert "accn" in entry, f"{path.name}:{concept} sin accn"
                    assert "form" in entry, f"{path.name}:{concept} sin form"
                    assert "filed" in entry, f"{path.name}:{concept} sin filed"
                    assert "fp" in entry, f"{path.name}:{concept} sin fp"


def test_submissions_fixtures_have_the_recent_block():
    for path in sorted((FIXTURES / "sec").glob("submissions_*.json")):
        recent = json.loads(path.read_text(encoding="utf-8"))["filings"]["recent"]
        columns = ["accessionNumber", "form", "filingDate", "reportDate", "primaryDocument"]
        for column in columns:
            assert column in recent, f"{path.name} no trae filings.recent.{column}"
        lengths = {len(recent[column]) for column in columns}
        assert len(lengths) == 1, f"{path.name}: columnas de longitudes distintas {lengths}"


def test_index_fixtures_carry_matching_sha256():
    import hashlib

    for path in sorted((FIXTURES / "sec" / "index").glob("*.json")):
        bundle = json.loads(path.read_text(encoding="utf-8"))
        if bundle.get("tamper_index_sha256"):
            continue
        if path.name == "tampered_sha.json":
            assert bundle["index_sha256"] == "0" * 64
            continue
        if bundle.get("missing_index"):
            continue
        expected = hashlib.sha256(bundle["index_html"].encode("utf-8")).hexdigest()
        assert bundle["index_sha256"] == expected, f"{path.name}: index_sha256 no casa"
        document = hashlib.sha256(bundle["document"].encode("utf-8")).hexdigest()
        assert bundle["document_sha256"] == document, f"{path.name}: document_sha256 no casa"


def test_esef_fixtures_use_fact_id_keys():
    """`normalize_xbrl_json` itera values(): agrupar por concepto haria que la
    unidad viera una lista y el corpus mediria el fixture equivocado."""
    from app.services.connectors.esef import normalize_xbrl_json

    for path in sorted((FIXTURES / "esef").glob("xbrl_json_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["lei"], f"{path.name} sin LEI"
        assert len(payload["lei"]) == 20, f"{path.name}: LEI de {len(payload['lei'])} chars"
        for key, fact in payload["facts"].items():
            assert key.startswith("fact-"), f"{path.name}: clave {key} no es fact-N"
            assert "dimensions" in fact and "concept" in fact["dimensions"], f"{path.name}:{key}"
        normalized = normalize_xbrl_json(payload)
        if path.name == "xbrl_json_core.json":
            assert normalized["ifrs-full:Revenue"]["iso4217:EUR"][0]["val"] == "5900000000"


def test_untagged_report_has_no_facts_block():
    from app.services.connectors.esef import EsefError, normalize_xbrl_json

    payload = json.loads((FIXTURES / "esef" / "untagged_report.json").read_text(encoding="utf-8"))
    assert "facts" not in payload
    with pytest.raises(EsefError):
        normalize_xbrl_json(payload)


def test_inline_instance_declares_scale_sign_and_no_unitref():
    text = (FIXTURES / "sec" / "instances" / "no_unitref_scale_sign.xml").read_text(encoding="utf-8")
    assert 'scale="3"' in text
    assert 'sign="-"' in text
    assert "unitRef" not in text


def test_dataset_only_references_fixtures_that_exist():
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    for case in dataset["cases"]:
        for relative in harness.declared_fixtures(case):
            assert (FIXTURES / relative).exists(), f"{case['id']} -> {relative} no existe"


def test_dataset_families_and_scenarios_are_known():
    from evals.ingest.harness import SCENARIOS

    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    for case in dataset["cases"]:
        assert case["family"] in FAMILY_SOURCE_TYPES, case["id"]
        assert case["scenario"] in SCENARIOS, case["id"]
        assert case["expected"]["tolerance"] is not None, case["id"]
        assert isinstance(case["expected"]["as_of"], str), case["id"]


def test_dataset_families_and_scenarios_are_known():
    from evals.ingest.harness import SCENARIOS
    from evals.ingest.ingest_gates import NON_SKIPPABLE_GATES

    # Un control negativo que quita una clave declarada a proposito (la
    # tolerancia, `as_of`, `index`, `absent_metrics`) no puede cumplir el
    # esquema de un caso bueno: para eso existe.
    omits_keys = set(NON_SKIPPABLE_GATES) | {"fixture_schema_valid"}
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    for case in dataset["cases"]:
        assert case["family"] in FAMILY_SOURCE_TYPES, case["id"]
        assert case["scenario"] in SCENARIOS, case["id"]
        if case.get("expect_gate_failure") in omits_keys:
            continue
        assert case["expected"]["tolerance"] is not None, case["id"]
        assert isinstance(case["expected"]["as_of"], str), case["id"]


MONETARY_KEYS = {
    "val", "value", "revenue", "grossProfit", "operatingIncome", "incomeBeforeTax",
    "incomeTaxExpense", "interestExpense", "netIncome", "ebitda", "epsdiluted",
    "weightedAverageShsOutDil", "cashAndCashEquivalents", "totalDebt", "netDebt",
    "totalAssets", "totalLiabilities", "totalStockholdersEquity", "goodwill",
    "intangibleAssets", "operatingLeaseLiabilities", "operatingCashFlow",
    "capitalExpenditure", "freeCashFlow", "commonStockRepurchased", "dividendsPaid",
    "grossProfitMargin", "operatingProfitMargin", "netProfitMargin", "debtEquityRatio",
    "effectiveTaxRate", "beta", "mktCap", "price", "volume", "document",
    "index_html", "submissions_capture",
}
# Claves de identificacion/fecha cuyo numero no es una magnitud declarada.
IDENTIFIER_KEYS = {
    "accn", "cik", "fxo_id", "lei", "entity", "sha256", "index_sha256",
    "document_sha256", "submissions_sha256", "timestamp", "filingDate", "reportDate",
    "end", "start", "instant", "period", "date", "fillingDate", "decimals", "ticker",
    "accession", "document_url", "period_end", "id",
}


def _numeric_leaves(node, key=None):
    if isinstance(node, dict):
        for child_key, child in node.items():
            yield from _numeric_leaves(child, child_key)
    elif isinstance(node, list):
        for child in node:
            yield from _numeric_leaves(child, key)
    elif isinstance(node, bool):
        return
    elif isinstance(node, (int, float)):
        yield key, float(node)
    elif isinstance(node, str) and key in {"val", "value"}:
        try:
            yield key, float(node)
        except ValueError:
            return


def test_no_undeclared_magnitudes_in_the_corpus():
    """Lista blanca cerrada: una magnitud fuera de ella es un valor sin declarar.

    El recorrido es estructural (claves `val`/`value`/metricas del proveedor), no
    una regexp sobre el texto: los accessions, los LEI y las fechas son numeros
    que no son magnitudes y declararlos uno a uno solo haria la lista ilegible.
    """
    undeclared: list[str] = []
    for path in sorted((FIXTURES / "sec").glob("companyfacts_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for concept, body in payload["facts"]["us-gaap"].items():
            for unit, entries in body["units"].items():
                for entry in entries:
                    value = entry.get("val")
                    if value is None:
                        continue
                    magnitude = float(value)
                    if abs(magnitude) not in ALLOWED_VALUES:
                        undeclared.append(f"{path.name}:{concept}={value}")
    for path in sorted((FIXTURES / "fmp").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("rows") or []:
            for key, value in row.items():
                if key not in MONETARY_KEYS or key in IDENTIFIER_KEYS:
                    continue
                if value is None or value == "":
                    continue
                try:
                    magnitude = float(value)
                except (TypeError, ValueError):
                    continue
                if abs(magnitude) not in ALLOWED_VALUES:
                    undeclared.append(f"{path.name}:{key}={value}")
    for path in sorted((FIXTURES / "esef").glob("xbrl_json_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for key, magnitude in _numeric_leaves(payload.get("facts", {})):
            if key == "decimals" or abs(magnitude) in ALLOWED_VALUES:
                continue
            undeclared.append(f"{path.name}:{key}={magnitude}")
    for path in sorted((FIXTURES / "sec" / "instances").glob("*.xml")):
        for text in re.findall(r">\s*(-?\d[\d.]*)\s*<", path.read_text(encoding="utf-8")):
            magnitude = float(text)
            if abs(magnitude) not in ALLOWED_VALUES:
                undeclared.append(f"{path.name}:{text}")
    assert not undeclared, "magnitudes sin declarar en el corpus: " + ", ".join(undeclared[:20])


def test_every_fixture_is_referenced_by_the_dataset():
    """Un fixture que nadie ejercita es corpus muerto: mide el fixture equivocado."""
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    referenced: set[str] = set()
    for case in dataset["cases"]:
        referenced.update(harness.declared_fixtures(case))
    orphans = [
        str(path.relative_to(FIXTURES)).replace("\\", "/")
        for path in _all_files()
        if path.name != "README.md"
        and str(path.relative_to(FIXTURES)).replace("\\", "/") not in referenced
    ]
    assert not orphans, f"fixtures sin caso que los ejercite: {orphans}"


def test_submissions_index_missing_is_declared_missing():
    bundle = json.loads(
        (FIXTURES / "sec" / "index" / "missing_index.json").read_text(encoding="utf-8")
    )
    assert bundle["missing_index"] is True
    assert bundle["origin"] == ORIGIN
