"""Contratos del harness RAG: puertas, cobertura, hermeticidad y parsers.

Este fichero es la contraparte de ``evals/gates.py`` para el RAG. Lo que vigila,
en orden de gravedad:

* Las puertas no se pueden silenciar por omision. Una puerta que devuelve
  ``passed=True`` cuando falta la clave que necesita es una puerta muerta, y en
  este repo ya hubo tres asi (``probabilities_sum_to_one``,
  ``valuation_unchanged``, ``replay_no_duplicate_version``).
* La cobertura por puerta: si una puerta no se ejecuta en ningun caso, el
  runner tiene que fallar, no imprimir "todo verde".
* El runner es hermetico: sin red y sin proveedor de LLM. El guardian de
  socket se comprueba de verdad, no de palabra.
* El runner real no se salta: sin Qdrant tiene que salir con 1, no con un stub
  disfrazado de medicion.
* Los parsers que escribimos (cifras, identificadores, citas, frases) tienen
  los cuatro tests de contrato que los other agents forgot: coma decimal
  espanola, accession numbers, negaciones y citas ausentes.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals" / "rag"
CORPUS = json.loads((EVALS / "rag_corpus_v1.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((EVALS / "rag_golden_v1.json").read_text(encoding="utf-8"))
CORPUS_IDS = sorted({doc["id"] for doc in CORPUS["documents"]})


def _case(**overrides) -> dict:
    base = {
        "id": "rag-test-001",
        "question": "q",
        "expected_answer": "a",
        "expected_facts": [],
        "expected_sources": [],
        "must_refuse": False,
        "category": "qualitative",
        "applies_to": sorted(__import__("evals.rag.rag_gates", fromlist=["GATES"]).GATES),
        "notes": "n",
        "artifact": {"answer": "respuesta\nFuentes: doc-itu-provenance", "retrieved": []},
        "corpus_ids": CORPUS_IDS,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# las puertas no se pueden omitir
# --------------------------------------------------------------------------


def test_no_invented_numbers_fails_without_its_key():
    from evals.rag.rag_gates import gate_no_invented_numbers

    case = _case()
    del case["expected_facts"]
    result = gate_no_invented_numbers(case)
    assert result["passed"] is False
    assert "no puede omitirse" in result["details"][0]


def test_no_invented_numbers_fails_without_an_answer():
    from evals.rag.rag_gates import gate_no_invented_numbers

    case = _case()
    del case["artifact"]["answer"]
    result = gate_no_invented_numbers(case)
    assert result["passed"] is False
    assert "no puede omitirse" in result["details"][0]


def test_abstention_gate_fails_without_must_refuse():
    from evals.rag.rag_gates import gate_abstained_when_unanswerable

    case = _case()
    del case["must_refuse"]
    result = gate_abstained_when_unanswerable(case)
    assert result["passed"] is False
    assert "no puede omitirse" in result["details"][0]


def test_sources_are_real_fails_without_the_corpus():
    from evals.rag.rag_gates import gate_sources_are_real

    case = _case()
    del case["corpus_ids"]
    result = gate_sources_are_real(case)
    assert result["passed"] is False
    assert "no puede omitirse" in result["details"][0]


def test_expected_sources_cited_fails_without_its_key():
    from evals.rag.rag_gates import gate_expected_sources_cited

    case = _case()
    del case["expected_sources"]
    result = gate_expected_sources_cited(case)
    assert result["passed"] is False
    assert "no puede omitirse" in result["details"][0]


def test_schema_gate_rejects_an_empty_expected_answer():
    """Un golden sin respuesta de referencia no puede contrastar ninguna cifra."""
    from evals.rag.rag_gates import gate_golden_schema_valid

    result = gate_golden_schema_valid(_case(expected_answer="   "))
    assert result["passed"] is False
    assert any("expected_answer vacio" in detail for detail in result["details"])


def test_schema_gate_rejects_an_unanswerable_case_that_may_answer():
    from evals.rag.rag_gates import gate_golden_schema_valid

    result = gate_golden_schema_valid(_case(category="unanswerable", must_refuse=False))
    assert result["passed"] is False


def test_gate_that_never_ran_is_a_failing_runner_not_a_passing_one():
    """El recuento por puerta es lo que hace visible una puerta muerta."""
    from evals.rag.rag_gates import GATES, applies

    executed = dict.fromkeys(GATES, 0)
    for case in GOLDEN["cases"]:
        for gate_name in GATES:
            if applies(case, gate_name):
                executed[gate_name] += 1
    never_ran = [name for name, count in executed.items() if count == 0]
    assert not never_ran, f"puertas que no se ejecutan sobre ningun caso: {never_ran}"


# --------------------------------------------------------------------------
# hermeticidad
# --------------------------------------------------------------------------


def test_network_guard_blocks_a_public_host_and_allows_loopback():
    import socket

    from evals.rag.rag_harness import NetworkBlocked, NetworkGuard

    guard = NetworkGuard().install()
    try:
        with pytest.raises(NetworkBlocked):
            socket.create_connection(("huggingface.co", 443), timeout=1)
        # El puerto de loopback se PERMITE: sin esto el runner no podria hablar
        # con el Qdrant local, que es justo lo que tiene que hacer.
        guard._check(("127.0.0.1", 6333))
        guard._check(("localhost", 6333))
    finally:
        guard.restore()
    # Y al restaurar, la red vuelve a estar como estaba: importar el harness no
    # puede dejar el proceso con las salidas cortadas para siempre.
    assert socket.socket.connect.__name__ == "connect"


def test_network_guard_allows_model_hosts_only_when_asked():
    from evals.rag.rag_harness import NetworkGuard

    strict = NetworkGuard()
    strict.install()
    try:
        with pytest.raises(Exception):
            strict._check(("huggingface.co", 443))
        with pytest.raises(Exception):
            strict._check(("cdn-lfs.huggingface.co", 443))
    finally:
        strict.restore()

    permissive = NetworkGuard(allow_model_download=True)
    permissive.install()
    try:
        permissive.allow_model_hosts()
        permissive._check(("huggingface.co", 443))
        with pytest.raises(Exception):
            permissive._check(("api.openai.com", 443))
    finally:
        permissive.restore()


def test_harness_import_does_not_leave_the_network_blocked():
    """Importar el harness no puede cambiar el estado global del proceso."""
    import socket

    before = socket.socket.connect
    import evals.rag.rag_harness  # noqa: F401

    assert socket.socket.connect is before


# --------------------------------------------------------------------------
# refuse-to-skip
# --------------------------------------------------------------------------


def test_real_runner_exits_1_when_qdrant_is_not_reachable(tmp_path, monkeypatch):
    """Sin Qdrant el runner dice que no puede medir. No se degrada a un stub.

    Se apunta QDRANT_URL a un puerto cerrado en lugar de depender de que el
    puerto por defecto este o no ocupado en la maquina que corre el test.
    """
    env = {
        "QDRANT_URL": "http://127.0.0.1:6399",
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'rag.db').as_posix()}",
        "APP_ENV": "test",
    }
    import os

    merged = {**os.environ, **env}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_rag_evals.py")],
        capture_output=True,
        text=True,
        timeout=600,
        env=merged,
        cwd=str(ROOT),
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "no puede correr" in (result.stdout + result.stderr)
    assert "no se salta" in (result.stdout + result.stderr)


def _qdrant_reachable() -> bool:
    try:
        from app.services.rag import RAGIndex

        return bool(RAGIndex().status().get("configured"))
    except Exception:
        return False


requires_qdrant = pytest.mark.skipif(
    not _qdrant_reachable(),
    reason="Qdrant no disponible: el CI tiene que exigir este test con el gate de "
    "Qdrant, igual que con test_rag_activation.py (ver INTEGRACION PENDIENTE)",
)


@requires_qdrant
def test_real_runner_passes_the_six_gateable_metrics():
    """El numero que se gatea sale del pipeline real, no de un stub.

    Este test se salta si Qdrant no esta levantado, igual que
    ``tests/test_rag_activation.py``. Por eso el CI necesita un paso que falle
    si este test aparece como skipped: si no, la puerta del RAG se evapora en
    cuanto Qdrant no arranca. Es el mismo criterio que el gate "RAG activation
    tests skipped -> exit 1" que ya existe en ci.yml.
    """
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_rag_evals.py")],
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "gateable=si" in result.stdout
    for metric in (
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
        "abstention_accuracy",
        "source_hit_rate",
    ):
        assert metric in result.stdout, metric
    assert "NUNCA SE EJECUTO" not in result.stdout


def test_dry_run_marks_its_numbers_as_not_gateable():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_rag_evals.py"), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "gateable=no" in result.stdout
    assert "dry_run" in result.stdout


def test_dry_run_covers_every_gate():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_rag_evals.py"), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "NUNCA SE EJECUTO" not in result.stdout


# --------------------------------------------------------------------------
# contratos de los parsers
# --------------------------------------------------------------------------


def test_identifier_masks_do_not_turn_dates_into_invented_numbers():
    """Fechas, accession numbers y horas son identificadores, no magnitudes."""
    from evals.rag.rag_gates import numbers_in_prose

    prose = (
        "El periodo es 2022-01-01T00:00:00/2023-01-01T00:00:00, el accession es "
        "0001193125-26-342540, la hora 20:39:45 y el sha256 es 1da58c29610f9956d."
    )
    assert numbers_in_prose(prose) == [], numbers_in_prose(prose)


def test_a_frequency_range_yields_two_magnitudes_and_a_negative_survives():
    """'2483.5-2500' son dos cifras, y '-3' es una cifra negativa, no un guion."""
    from evals.rag.rag_gates import numbers_in_prose

    assert numbers_in_prose("de 2483.5-2500 MHz") == ["2483.5", "2500"]
    assert numbers_in_prose("con decimals -3 y 4 hechos") == ["-3", "4"]


def test_spanish_decimal_comma_is_not_a_thousands_separator():
    """Se reutiliza _norm_number de evals/gates.py, coma decimal incluida."""
    from evals.gates import _norm_number
    from evals.rag.rag_gates import numbers_in_prose

    assert numbers_in_prose("pesa 8,09 MB") == ["8,09"]
    assert _norm_number("8,09") == 8.09
    assert _norm_number("1,234") == 1234.0


def test_citations_are_parsed_from_the_answer_text_not_from_a_field():
    """Si el lector dice que cito, esta escrito; si no, la puerta tiene que verlo."""
    from evals.rag.rag_gates import is_abstention, parse_citations

    assert parse_citations("dato.\nFuentes: doc-a, doc-b") == ["doc-a", "doc-b"]
    assert parse_citations("dato sin linea de fuentes") is None
    assert parse_citations("dato.\nFuentes: ") == []
    assert is_abstention("No encuentro eso: no esta en la biblioteca.") is True
    assert is_abstention("No está en la biblioteca.") is True, "la tilde no decide"
    assert is_abstention("Aqui hay un 5.") is False


def test_a_token_with_letters_is_an_identifier_not_a_magnitude():
    """Un token con letras es un identificador: '8-K' no aporta la cifra 8."""
    from evals.rag.rag_gates import numbers_in_prose

    assert numbers_in_prose("J2026-83391 y all-MiniLM-L6-v2") == []
    assert numbers_in_prose("el 8-K pesa 48030 bytes") == ["48030"]


def test_reader_abstains_when_the_best_evidence_is_a_negation():
    """La frase que dice 'no son la fecha de publicacion' no puede ser la fecha."""
    from evals.rag.rag_harness import build_lexicon, compose_answer

    lexicon = build_lexicon([doc["content"] for doc in CORPUS["documents"]])
    retrieved = [
        {
            "doc_id": "doc-itu-provenance",
            "text": (
                "Advertencia del propio README: la fecha de registro BR y la fecha de recepcion "
                "no son la fecha de publicacion de las fichas ITU."
            ),
            "score": 1.0,
        }
    ]
    answer = compose_answer("Cual es la fecha de publicacion de las fichas ITU", retrieved, lexicon)
    assert "no esta en la biblioteca" in answer.lower()


def test_reader_does_not_add_a_second_sentence_from_an_unrelated_document():
    """Una segunda frase de ruido mete cifras que no estan en el golden."""
    from evals.rag.rag_harness import build_lexicon, compose_answer

    lexicon = build_lexicon([doc["content"] for doc in CORPUS["documents"]])
    retrieved = [
        {
            "doc_id": "doc-itu-d2026-84958",
            "text": "La ficha ITU D2026-84958 declara 5 bandas de frecuencia unicas (MHz).",
            "score": 1.0,
        },
        {
            "doc_id": "doc-itu-j2026-70633",
            "text": "El adjunto J-BLUEBIRD-NGSO_CR.mdb de la ficha ITU J2026-70633 pesa 13.6 MB.",
            "score": 0.9,
        },
    ]
    answer = compose_answer(
        "Cuantas bandas de frecuencia declara la ficha ITU D2026-84958, la del CR-MOD", retrieved, lexicon
    )
    assert "13.6" not in answer
    assert "5" in answer


def test_faithfulness_rejects_a_number_that_is_not_in_the_context():
    from evals.rag.rag_metrics import faithfulness

    context = "El valor del hecho Revenue es 7705687000 EUR."
    good = faithfulness("Revenue es 7705687000 EUR", context)
    assert good["score"] == 1.0
    bad = faithfulness("Revenue es 9999999999 EUR", context)
    assert bad["score"] == 0.0
    assert bad["unsupported"]


def test_context_precision_reproduces_the_average_precision_formula():
    """La AP de RAGAS pondera por posicion: un hit en 3 no vale lo mismo que en 1."""
    from evals.rag.rag_metrics import context_precision, context_recall

    references = ["bandas de frecuencia de la ficha ITU de referencia"]
    ranked_first = context_precision([references[0], "texto que no tiene nada que ver"], references)
    ranked_last = context_precision(["texto que no tiene nada que ver", references[0]], references)
    assert ranked_first["score"] > ranked_last["score"]
    assert ranked_first["score"] == 1.0
    assert ranked_last["score"] == 0.5
    assert context_recall([references[0]], references)["score"] == 1.0
    assert context_recall(["nada que ver"], references)["score"] == 0.0
