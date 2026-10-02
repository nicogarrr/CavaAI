"""Hard gates deterministas para la evaluacion del RAG sobre el golden set.

Mismo contrato que ``evals/gates.py``: cada gate es una funcion pura
``f(case) -> {"gate", "passed", "details"}`` sobre el caso del golden set mas
el artefacto observado (la respuesta que el RAG dio de verdad). Nada de LLM
 juzgando a LLM: schema, numeros contra los hechos esperados, abstention,
 y fuentes reales del corpus.

Dos reglas que el harness debe respetAR o estas puertas no valen nada:

1. ``applies_to`` declara que gates ejercita cada caso; el runner cuenta la
   cobertura por puerta y falla si alguna no se ejecuto nunca.
2. Ninguna puerta se puede silenciar por omision. Si falta la clave que la
   puerta necesita, ``passed=False`` con la cadena
   ``"el gate no puede omitirse"`` (mismo criterio que
   ``probabilities_sum_to_one`` y ``valuation_unchanged``).
"""

from __future__ import annotations

import re
import unicodedata

from evals.gates import _norm_number

# Marcador de abstention. Se compara sobre texto normalizado (sin acentos y en
# minusculas) para que la tildacion no decida si el RAG se abstuvo o no.
ABSTENTION_MARKER = "no esta en la biblioteca"

# Formato de la linea de citas que el lector determinista anade a la respuesta.
CITATION_PREFIX = "Fuentes:"

CATEGORIES = frozenset(
    {"numeric_lookup", "multi_hop", "qualitative", "unanswerable", "out_of_scope"}
)
# `negative_control` no es una pregunta: es un artefacto fabricado que existe
# para que su puerta falle. El runner lo excluye de las metricas.
NEGATIVE_CONTROL_CATEGORY = "negative_control"
ALL_CATEGORIES = CATEGORIES | {NEGATIVE_CONTROL_CATEGORY}
REFUSE_CATEGORIES = frozenset({"unanswerable", "out_of_scope"})

OMISSIBLE = "el gate no puede omitirse"

# Un numero es una magnitud, no un identificador. En la biblioteca_convivem
# importes, frecuencias, accession numbers ("0001193125-26-342540"), fechas
# ISO ("2022-01-01T00:00:00"), horas, referencias ITU ("J2026-83391") y huellas
# MD5. Sin esta mascara, la puerta reportaba como "cifra inventada" el ano de una
# fecha o un trozo de un LEI, y el golden set era imposible de satisfacer sin
# mentir. Regla: se ignoran los identificadores, y de un token se extraen
# magnitudes solo si NO contiene ninguna letra.
_IDENTIFIER_RE = re.compile(
    r"\d+[-/]\d+[-/]\d+"  # fechas ISO, fechas dd/mm/aaaa, accession numbers
    r"|\d{1,2}:\d{2}(?::\d{2})?"  # horas y marcas de tiempo
)
_MAGNITUDE_RE = re.compile(r"-?\d+(?:[.,]\d+)*")
_CITATION_RE = re.compile(rf"^{re.escape(CITATION_PREFIX)}\s*(?P<body>.*)$", re.MULTILINE)
_ID_RE = re.compile(r"^rag-[a-z0-9-]+$")

REQUIRED_CASE_KEYS: dict[str, type] = {
    "id": str,
    "question": str,
    "expected_answer": str,
    "expected_facts": list,
    "expected_sources": list,
    "must_refuse": bool,
    "category": str,
    "applies_to": list,
    "notes": str,
}

REQUIRED_ARTIFACT_KEYS: dict[str, type] = {
    "answer": str,
    "retrieved": list,
}


def strip_accents(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    )


def normalize_text(text: str) -> str:
    return strip_accents(str(text or "")).lower()


def is_abstention(answer: str) -> bool:
    """La respuesta se abstiene SI el marcador aparece en el TEXTO.

    No se mira un booleano del harness: un flag que el propio lector pone a True
    mientras escribe una respuesta completa es exactamente el fallo que este
    gate existe para cazar.
    """
    return ABSTENTION_MARKER in normalize_text(answer)


def parse_citations(answer: str) -> list[str] | None:
    """Ids de fuente citados en el texto de la respuesta, o None si no hay linea.

    Las puertas leen el TEXTO, no un campo de bookkeeping del harness: si el
    lector dice que-Tho cito una fuente tiene que estar escrito en la respuesta.
    """
    match = _CITATION_RE.search(str(answer or ""))
    if not match:
        return None
    body = match.group("body").strip()
    if not body:
        return []
    return [part.strip() for part in body.split(",") if part.strip()]


def answer_prose(answer: str) -> str:
    """La respuesta sin la linea de citas, para no contar ids como cifras."""
    return _CITATION_RE.sub("", str(answer or ""))


# ---------------------------------------------------------------------------
# 1. schema del golden set
# ---------------------------------------------------------------------------


def gate_golden_schema_valid(case: dict) -> dict:
    problems: list[str] = []
    for key, expected_type in REQUIRED_CASE_KEYS.items():
        if key not in case:
            problems.append(f"falta {key}")
        elif not isinstance(case[key], expected_type):
            problems.append(f"{key} no es {expected_type.__name__}")
    artifact = case.get("artifact")
    if not isinstance(artifact, dict):
        problems.append("falta artifact (la observacion del RAG)")
    else:
        for key, expected_type in REQUIRED_ARTIFACT_KEYS.items():
            if key not in artifact:
                problems.append(f"artifact sin {key}")
            elif not isinstance(artifact[key], expected_type):
                problems.append(f"artifact.{key} no es {expected_type.__name__}")
    if isinstance(case.get("id"), str) and not _ID_RE.match(case["id"]):
        problems.append(f"id fuera de formato rag-*: {case['id']}")
    for key in ("question", "expected_answer", "notes"):
        value = case.get(key)
        if isinstance(value, str) and not value.strip():
            # Un golden con expected_answer vacio autorizaria cualquier cifra en
            # la respuesta, porque no habria nada contra lo que contrastarla.
            problems.append(f"{key} vacio")
    category = case.get("category")
    if isinstance(category, str) and category not in ALL_CATEGORIES:
        problems.append(f"categoria desconocida: {category}")
    if isinstance(case.get("must_refuse"), bool) and isinstance(category, str):
        if category in CATEGORIES:
            # La categoria ya dice si la respuesta correcta es abstainerse: un
            # caso unanswerable marcado must_refuse=false es un golden set que
            # premia la alucinacion.
            expected_refuse = category in REFUSE_CATEGORIES
            if case["must_refuse"] is not expected_refuse:
                problems.append(
                    f"must_refuse={case['must_refuse']} incompatible con category={category}"
                )
    for index, fact in enumerate(case.get("expected_facts") or []):
        if not isinstance(fact, dict):
            problems.append(f"expected_facts[{index}] no es dict")
            continue
        if not isinstance(fact.get("metric"), str):
            problems.append(f"expected_facts[{index}].metric no es str")
        if not isinstance(fact.get("value"), (int, float, str)):
            problems.append(f"expected_facts[{index}].value no es numero")
    for index, source in enumerate(case.get("expected_sources") or []):
        if not isinstance(source, str):
            problems.append(f"expected_sources[{index}] no es str")
    for index, gate_name in enumerate(case.get("applies_to") or []):
        if not isinstance(gate_name, str):
            problems.append(f"applies_to[{index}] no es str")
    return _result("golden_schema_valid", not problems, problems)


# ---------------------------------------------------------------------------
# 2. numeros: toda cifra de la respuesta tiene que estar en el golden
# ---------------------------------------------------------------------------


def numbers_in_prose(text: str) -> list[str]:
    """Magnitudes del texto, con los identificadores ya fuera.

    "2483.5-2500 MHz" son dos magnitudes (2483.5 y 2500), no una sola; por eso
    un rango no se puede tratar como un token opaco. Y "-3" preceded de un
    espacio es una magnitud negativa, mientras que el "-2500" de un rango es un
    separador: la regla es "el signo cuenta solo si no va detras de otra cifra".
    """
    cleaned = _IDENTIFIER_RE.sub(" ", str(text or ""))
    magnitudes: list[str] = []
    for token in cleaned.split():
        if any(char.isalpha() for char in token):
            continue
        for match in re.finditer(r"(?<![\d.,])-?\d+(?:[.,]\d+)*", token):
            magnitudes.append(match.group(0))
    return magnitudes


def _expected_numbers(case: dict) -> set[float]:
    """Cifras que el golden autoriza: expected_facts + las del expected_answer.

    Se admiten las del expected_answer porque el golden esta escrito en lenguaje
    natural: "16,5 MHz de amplitud" es una cifra esperada, no una alucinacion.
    Lo que NO se admite es cualquier cifra que no aparezca en el golden: traer
    una cifra correcta de OTRA frase del contexto tampoco es la respuesta, es
    otra respuesta.
    """
    numbers: set[float] = set()
    for fact in case.get("expected_facts") or []:
        if not isinstance(fact, dict):
            continue
        raw = fact.get("value")
        if raw is None:
            continue
        number = _norm_number(str(raw))
        if number is not None:
            numbers.add(number)
    for match in numbers_in_prose(answer_prose(str(case.get("expected_answer") or ""))):
        number = _norm_number(match)
        if number is not None:
            numbers.add(number)
    return numbers


def gate_no_invented_numbers(case: dict) -> dict:
    artifact = case.get("artifact")
    if not isinstance(artifact, dict) or "answer" not in artifact:
        return _result(
            "no_invented_numbers",
            False,
            ["el artefacto no trae answer: el gate no puede omitirse"],
        )
    if "expected_facts" not in case:
        return _result(
            "no_invented_numbers",
            False,
            ["el caso no trae expected_facts: el gate no puede omitirse"],
        )
    if parse_citations(artifact.get("answer")) is None and not is_abstention(
        artifact.get("answer")
    ):
        return _result(
            "no_invented_numbers",
            False,
            ["la respuesta no trae linea de fuentes: el gate no puede omitirse"],
        )
    known = _expected_numbers(case)
    problems: list[str] = []
    prose = answer_prose(artifact.get("answer") or "")
    for match in numbers_in_prose(prose):
        number = _norm_number(match)
        if number is None or number in known:
            continue
        problems.append(f"cifra sin hecho esperado en la respuesta: {match}")
    return _result("no_invented_numbers", not problems, problems[:10])


# ---------------------------------------------------------------------------
# 3. abstention: la respuesta correcta a un unanswerable es no responder
# ---------------------------------------------------------------------------


def gate_abstained_when_unanswerable(case: dict) -> dict:
    if "must_refuse" not in case:
        return _result(
            "abstained_when_unanswerable",
            False,
            ["el caso no declara must_refuse: el gate no puede omitirse"],
        )
    artifact = case.get("artifact")
    if not isinstance(artifact, dict) or "answer" not in artifact:
        return _result(
            "abstained_when_unanswerable",
            False,
            ["el artefacto no trae answer: el gate no puede omitirse"],
        )
    answer = artifact["answer"]
    abstained = is_abstention(answer)
    if case["must_refuse"] and not abstained:
        return _result(
            "abstained_when_unanswerable",
            False,
            ["respondio cuando la respuesta correcta es 'no esta en la biblioteca'"],
        )
    if not case["must_refuse"] and abstained:
        return _result(
            "abstained_when_unanswerable",
            False,
            ["se abstuvo en una pregunta que la biblioteca si responde"],
        )
    return _result("abstained_when_unanswerable", True, [])


# ---------------------------------------------------------------------------
# 4. las fuentes citadas existen en el corpus
# ---------------------------------------------------------------------------


def gate_sources_are_real(case: dict) -> dict:
    corpus_ids = case.get("corpus_ids")
    if not isinstance(corpus_ids, list) or not corpus_ids:
        return _result(
            "sources_are_real",
            False,
            ["el caso no inyecta corpus_ids: el gate no puede omitirse"],
        )
    artifact = case.get("artifact")
    if not isinstance(artifact, dict) or "answer" not in artifact:
        return _result(
            "sources_are_real",
            False,
            ["el artefacto no trae answer: el gate no puede omitirse"],
        )
    answer = artifact["answer"]
    cited = parse_citations(answer)
    if cited is None and not is_abstention(answer):
        return _result(
            "sources_are_real",
            False,
            ["la respuesta no trae linea de fuentes: el gate no puede omitirse"],
        )
    cited = cited or []
    known = {str(item) for item in corpus_ids}
    problems = [f"fuente citada que no existe en el corpus: {source}" for source in cited
                if source not in known]
    return _result("sources_are_real", not problems, problems[:10])


# ---------------------------------------------------------------------------
# 5. cita al menos una fuente esperada
# ---------------------------------------------------------------------------


def gate_expected_sources_cited(case: dict) -> dict:
    if "expected_sources" not in case:
        return _result(
            "expected_sources_cited",
            False,
            ["el caso no trae expected_sources: el gate no puede omitirse"],
        )
    artifact = case.get("artifact")
    if not isinstance(artifact, dict) or "answer" not in artifact:
        return _result(
            "expected_sources_cited",
            False,
            ["el artefacto no trae answer: el gate no puede omitirse"],
        )
    answer = artifact["answer"]
    cited = parse_citations(answer) or []
    if case.get("must_refuse"):
        # Una abstention que ademas cita fuentes es incoherente: o no sabes, o
        # sabes de donde. Citar yuirse a la vez es el sintoma de un RAG que
        # improvisa.
        if cited:
            return _result(
                "expected_sources_cited",
                False,
                [f"abstention que ademas cita fuentes: {', '.join(cited)}"],
            )
        return _result("expected_sources_cited", True, [])
    expected = [str(item) for item in case["expected_sources"]]
    if not expected:
        return _result(
            "expected_sources_cited",
            False,
            ["el caso no declara expected_sources y aun exige respuesta: el gate no puede omitirse"],
        )
    missing = [source for source in expected if source not in cited]
    if missing:
        return _result(
            "expected_sources_cited",
            False,
            [f"no cita ninguna fuente esperada: {', '.join(missing)}"],
        )
    return _result("expected_sources_cited", True, [])


GATES = {
    "golden_schema_valid": gate_golden_schema_valid,
    "no_invented_numbers": gate_no_invented_numbers,
    "abstained_when_unanswerable": gate_abstained_when_unanswerable,
    "sources_are_real": gate_sources_are_real,
    "expected_sources_cited": gate_expected_sources_cited,
}


def applies(case: dict, gate_name: str) -> bool:
    """Si el caso declara que ejercita una puerta. Sin declaracion, la puerta corre."""
    declared = case.get("applies_to")
    if declared is None:
        return True
    return gate_name in declared


def _result(gate: str, passed: bool, details: list[str]) -> dict:
    return {"gate": gate, "passed": passed, "details": details}
