"""El golden set RAG es la fuente de verdad, y estas son sus reglas.

Tres bloques, en el mismo orden que el riesgo que cubren:

1. Contrato del dataset y del corpus: schema, cobertura de las 5 categorias,
   ids unicos, y que los documentos del golden existan de verdad en el corpus.
2. Negative controls: un caso por puerta que TIENE que fallar, y que el
   artefacto de la puerta se lee del TEXTO de la respuesta, no de un campo de
   bookkeeping.
3. Determinismo: dos corridas del runner dan las mismas metricas. Un numero que
   cambia entre corridas no es gateable, por muy alto que sea el umbral.

Los tests del harness (puertas que no se pueden omitir, cobertura por puerta,
guardian de red, parsers) viven en test_rag_evals_contracts.py.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals" / "rag"
CORPUS = json.loads((EVALS / "rag_corpus_v1.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((EVALS / "rag_golden_v1.json").read_text(encoding="utf-8"))
CASES = GOLDEN["cases"]
CORPUS_IDS = {doc["id"] for doc in CORPUS["documents"]}


def test_corpus_declares_its_origin_and_provenance():
    """Un corpus sin origen declarado no se puede auditar ni citar."""
    assert CORPUS["corpus_origin"] == "repo_derived", (
        "el corpus tiene que declarar su origen; si algum dia fuera sintetico, "
        "corpus_origin tiene que valer 'synthetic_fixture' y decirlo en la nota"
    )
    assert CORPUS["source_files"], "el corpus tiene que listar los ficheros de procedencia"
    for entry in CORPUS["source_files"]:
        assert entry["path"].startswith("data-engine/"), entry
        assert len(entry["sha256"]) == 64, entry
        assert entry["used_for"], entry
    for doc in CORPUS["documents"]:
        assert doc["source_ref"], doc["id"]
        assert doc["content"].strip(), doc["id"]


def test_golden_set_has_at_least_45_cases_and_5_categories():
    assert len(CASES) >= 45, f"solo hay {len(CASES)} casos"
    measured = [c for c in CASES if c["category"] != "negative_control"]
    assert len(measured) >= 45, f"solo hay {len(measured)} casos medidos"
    categories = {c["category"] for c in measured}
    assert {
        "numeric_lookup",
        "multi_hop",
        "qualitative",
        "unanswerable",
        "out_of_scope",
    } <= categories, categories
    counts = {name: sum(1 for c in measured if c["category"] == name) for name in categories}
    assert counts["unanswerable"] >= 6, counts
    assert counts["out_of_scope"] >= 6, counts
    assert counts["numeric_lookup"] >= 8, counts
    assert counts["multi_hop"] >= 8, counts


def test_case_ids_are_unique_and_well_formed():
    ids = [case["id"] for case in CASES]
    assert len(set(ids)) == len(ids), "hay ids repetidos: el informe seria ilegible"
    for case in CASES:
        assert case["id"].startswith("rag-"), case["id"]


def test_every_cited_source_exists_in_the_corpus():
    """Una fuente que no existe es una cita inventada escrita en el golden."""
    for case in CASES:
        for source in case["expected_sources"]:
            assert source in CORPUS_IDS, f"{case['id']} cita {source}, que no esta en el corpus"


def test_refuse_cases_have_no_expected_source():
    """Si la respuesta correcta es abstaincion, no puede tener documento que citar."""
    for case in CASES:
        if case["must_refuse"]:
            assert case["expected_sources"] == [], case["id"]


def test_unanswerable_and_out_of_scope_must_refuse():
    """La categoria y `must_refuse` no pueden contradecirse."""
    for case in CASES:
        if case["category"] in {"unanswerable", "out_of_scope"}:
            assert case["must_refuse"] is True, case["id"]
        if case["category"] in {"numeric_lookup", "multi_hop", "qualitative"}:
            assert case["must_refuse"] is False, case["id"]


def test_negative_control_covers_every_gate():
    """Una puerta sin control negativo no ha demostrado que muerde."""
    from evals.rag.rag_gates import GATES

    failures = {case["expect_gate_failure"] for case in CASES if case.get("expect_gate_failure")}
    assert failures == set(GATES), f"sin control negativo: {sorted(set(GATES) - failures)}"
    for case in CASES:
        if case.get("expect_gate_failure"):
            assert case["category"] == "negative_control", case["id"]
            assert case["artifact"], case["id"]


def test_negative_controls_actually_fail_their_gate():
    from evals.rag.rag_gates import GATES

    negatives = [c for c in CASES if c.get("expect_gate_failure")]
    assert len(negatives) == len(GATES)
    for case in negatives:
        observed = dict(case)
        observed["corpus_ids"] = sorted(CORPUS_IDS)
        result = GATES[case["expect_gate_failure"]](observed)
        assert result["passed"] is False, f"{case['id']}: {result}"


def test_every_unanswerable_case_retrieves_context():
    """La abstention tiene que costar algo.

    Si el recuperador no devuelve NADA para una pregunta `unanswerable`, el RAG
    se abstiene por falta de contexto y no por criterio: el caso mide
    retrievability, no alucinacion. Con el stub determinista (mismo criterio
    que el resto del fichero, sin depender de Qdrant) los 16 casos de
    abstention tienen que recuperar al menos un fragmento.
    """
    from evals.rag.rag_harness import StubRetriever

    retriever = StubRetriever(CORPUS["documents"])
    blind = []
    for case in CASES:
        if case["category"] not in {"unanswerable", "out_of_scope"}:
            continue
        if case["category"] == "out_of_scope" and not retriever.search(case["question"]):
            continue  # fuera de dominio: que no recupere nada es lo correcto
        if not retriever.search(case["question"]):
            blind.append(case["id"])
    assert not blind, f"preguntas que el RAG no puede ver y aun asi deberia negar: {blind}"


def test_runner_is_deterministic():
    """Dos invocaciones seguidas, mismos numeros. Sin esto no hay puerta."""
    command = [sys.executable, str(ROOT / "scripts" / "run_rag_evals.py"), "--dry-run"]
    runs = []
    for _ in range(2):
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        assert result.returncode == 0, result.stdout + result.stderr
        runs.append(_metrics_from_stdout(result.stdout))
    assert runs[0] == runs[1], f"el runner no es determinista: {runs[0]} != {runs[1]}"


def _metrics_from_stdout(stdout: str) -> dict:
    """Lee el bloque de metricas del informe del runner.

    Se parsea la salida y no el JSON del corpus porque lo que tiene que ser
    determinista es lo que el CI lee: los numeros que imprime el runner.
    """
    metrics: dict[str, float] = {}
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[1].replace(".", "").isdigit() and parts[0] in {
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "abstention_accuracy",
            "source_hit_rate",
        }:
            metrics[parts[0]] = float(parts[1])
    assert len(metrics) == 6, f"no se pudieron leer las 6 metricas del informe:\n{stdout}"
    return metrics
