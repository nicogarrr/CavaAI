"""Las cuatro metricas gateables del RAG, deterministas y sin LLM.

Definiciones (RAGAS, Apache-2.0) y que se sustituye aqui:

============================  ===============================================  =========================
Metrica                       Que mide (formulacion RAGAS)                     Substitute determinista
============================  ===============================================  =========================
``faithfulness``              Fraccion de sentencias de la respuesta que el      Judge de soporte lexical:
                              contexto recuperado respalda.                      todo termino de contenido y
                                                                                toda cifra de la sentencia
                                                                                estan en el contexto.
``answer_relevancy``          La respuesta responde a la pregunta.              Cobertura de los terminos de
                                                                                contenido de la pregunta por
                                                                                la mejor frase de la respuesta.
``context_precision``         Precision media en el ranking de contexto         AP de RAGAS con relevancia
                              recuperado, con `reference_contexts`.              binaria por solapamiento.
``context_recall``            Fraccion de los `reference_contexts` cubiertos     Recall de RAGAS con relevancia
                              por el contexto recuperado.                       binaria por solapamiento.
============================  ===============================================  =========================

Por que un judge lexical y no el LLM de RAGAS: el fixture del repo declara
"Deterministic hard gates only; no LLM judging LLM" y un juez LLM da un numero
distinto en cada corrida, lo que hace la puerta imposible de gatear. El
`--ragas-crossover` del runner corre las metricas no-LLM reales de RAGAS
(``NonLLMContextPrecisionWithReference`` y ``NonLLMContextRecall``) sobre las
mismas muestras para que la desviacion este cuantificada y no supuesta.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from evals.rag.rag_gates import normalize_text, strip_accents

# Umbral de relevancia binaria de context_precision / context_recall. Es un
# coeficiente de Dice sobre terminos de contenido: un chunk de un documento
# ajeno puntua por debajo de 0.10, y uno del documento correcto por encima de 0.30.
RELEVANCE_THRESHOLD = 0.30

# Un termino que aparece en 2 documentos o menos es el que identifica una
# entidad concreta del corpus (un numero de ficha, un accession, un CIK). Con
# 17 documentos, el IDF maximo vale 2.5 y el minimo 0.6: demasiado plano para
# separar "J2026-70632" de "banda", asi que el multi-hop decide por frecuencia
# de documento, que si separa.
RARE_DOCUMENT_FREQUENCY = 2

# Cobertura de terminos que hace que una sentencia este soportada. 0.85 y no 1.0
# porque la flexion y la ordenacion de palabras no son alucinaciones; la cifra,
# en cambio, tiene que estar exactamente (gate `no_invented_numbers`).
SUPPORT_COVERAGE = 0.85

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)?")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;:])\s+|\n+")

# Stopwords es/en. Una lista corta y explicita: sin ellas "de" y "the" cuentan
# como senal y las metricas de recuperacion miden palabras vacias en vez de tema.
# Incluye el armazon de la pregunta ("cual", "cuanto", "usa", "decia") porque el
# golden set esta escrito como lo escribiria un usuario, con esas palabras en
# todas las preguntas y en ningun documento.
STOPWORDS = frozenset(
    [
        "a", "al", "algo", "algun", "alguna", "algunas", "alguno", "algunos", "ante",
        "antes", "aqui", "asi", "aun", "aunque", "bajo", "bien", "cada", "como",
        "con", "contra", "cual", "cuales", "cuanta", "cuantas", "cuanto", "cuantos",
        "cuando", "de", "del", "desde", "donde", "dos", "el", "ella", "ellas",
        "ellos", "en", "entre", "era", "eran", "eres", "es", "esa", "esas", "ese",
        "eso", "esos", "esta", "estan", "estas", "este", "esto", "estos", "fue", "ha",
        "habia", "han", "hasta", "hay", "la", "las", "le", "les", "lo", "los", "mas",
        "me", "mi", "mis", "mucho", "muchos", "muy", "nada", "ni", "no", "nos",
        "nuestra", "nuestro", "o", "os", "otra", "otras", "otro", "otros", "para",
        "pero", "poco", "por", "porque", "que", "quien", "quienes", "se", "sea",
        "segun", "ser", "si", "sin", "sobre", "solo", "son", "su", "sus", "tambien",
        "tanto", "te", "tiene", "tienen", "todo", "todos", "tu", "tus", "un", "una",
        "unas", "uno", "unos", "y", "ya",
        "an", "and", "are", "as", "at", "be", "been", "being", "by", "can", "did",
        "do", "does", "for", "from", "had", "has", "have", "how", "if", "in", "into",
        "is", "it", "its", "of", "on", "or", "our", "out", "over", "she", "that",
        "the", "their", "them", "then", "there", "these", "they", "this", "to", "was",
        "were", "what", "when", "which", "who", "will", "with", "would",
    ]
)


def normalize_term(token: str) -> str:
    """Minusculas, sin tildes y con la 's' final de plural.caida.

    Sin esto el golden set es imposible de satisfacer: el corpus dice "senales
    point-in-time" y la pregunta "senal point-in-time", y la cobertura lexical
    los separaba. Hay dos reglas, en este orden, porque el plural espanol no es
    solo "-s":

    * "-es" final con palabra de 6+ letras -> "senales" -> "senal".
    * "-s" final con palabra de 5+ letras -> "bandas" -> "banda".

    No es un stemmer: no hay raiz, ni conjugacion, ni negation.
    """
    lowered = strip_accents(str(token or "")).lower()
    if len(lowered) >= 6 and lowered.endswith("es"):
        return lowered[:-2]
    if len(lowered) >= 5 and lowered.endswith("s") and not lowered.endswith("ss"):
        return lowered[:-1]
    return lowered


def content_terms(text: str) -> set[str]:
    """Terminos de contenido normalizados: minusculas, sin tildes, sin stopwords.

    Las cifras SI son terminos de contenido. Una pregunta que dice "la banda de
    1675-1680 MHz" tiene que poder distinguirla de la de "2483.5-2500 MHz", y
    con el IDF un numero raro pesa mas que un ano que aparece en todos lados.
    """
    tokens = _TOKEN_RE.findall(strip_accents(str(text or "")).lower())
    return {
        token
        for token in (normalize_term(token) for token in tokens)
        if len(token) >= 2 and token not in STOPWORDS
    }


def numbers_in(text: str) -> set[str]:
    """Cifras tal cual aparecen, para que "2483.5" no colisione con "2483"."""
    return {
        token.replace(",", "")
        for token in _TOKEN_RE.findall(strip_accents(str(text or "")).lower())
        if token[0].isdigit()
    }


def sentences(text: str) -> list[str]:
    """Frases del texto. El corte exige espacio tras el signo, asi que ni
    "2483.5" ni "20.08.2026" se parten por el punto."""
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(str(text or "")) if part.strip()]


def dice(left: set[str], right: set[str]) -> float:
    """Similitud de Dice entre dos conjuntos de terminos de contenido."""
    if not left or not right:
        return 0.0
    return 2 * len(left & right) / (len(left) + len(right))


def _round(value: float) -> float:
    """3 decimales: el gate compara umbrales, no bits de coma flotante."""
    return round(float(value), 3)


# ---------------------------------------------------------------------------
# faithfulness (groundedness)
# ---------------------------------------------------------------------------


def is_supported(statement: str, context: str) -> bool:
    context_terms = content_terms(context)
    context_numbers = numbers_in(context)
    terms = content_terms(statement)
    if not terms:
        return False
    coverage = len(terms & context_terms) / len(terms)
    if coverage < SUPPORT_COVERAGE:
        return False
    # Una cifra que no esta en el contexto no puede estar soportada por el.
    return numbers_in(statement) <= context_numbers


def faithfulness(answer: str, context: str) -> dict:
    statements = sentences(answer)
    if not statements:
        return {"score": 0.0, "supported": 0, "total": 0, "unsupported": []}
    unsupported = [s for s in statements if not is_supported(s, context)]
    return {
        "score": _round((len(statements) - len(unsupported)) / len(statements)),
        "supported": len(statements) - len(unsupported),
        "total": len(statements),
        "unsupported": unsupported[:3],
    }


# ---------------------------------------------------------------------------
# answer_relevancy
# ---------------------------------------------------------------------------


def answer_relevancy(question: str, answer: str) -> dict:
    question_terms = content_terms(question)
    if not question_terms:
        return {"score": 0.0, "best": 0.0, "covered": 0, "asked": 0}
    covered: set[str] = set()
    best = 0.0
    for sentence in sentences(answer):
        overlap = len(question_terms & content_terms(sentence))
        ratio = overlap / len(question_terms)
        if ratio > best:
            best = ratio
        covered |= question_terms & content_terms(sentence)
    return {
        "score": _round(best),
        "best": _round(best),
        "covered": len(covered),
        "asked": len(question_terms),
    }


# ---------------------------------------------------------------------------
# context_precision / context_recall
# ---------------------------------------------------------------------------


def _relevance(retrieved: list[str], references: list[str]) -> list[float]:
    ref_sets = [content_terms(text) for text in references]
    return [max((dice(content_terms(chunk), ref) for ref in ref_sets), default=0.0) for chunk in retrieved]


def context_precision(retrieved: list[str], references: list[str]) -> dict:
    """Average precision de RAGAS sobre la lista rankeada de contexto.

    Reproduce `_calculate_average_precision` de ``NonLLMContextPrecisionWithReference``:
    veredicto binario por chunk, y el AP ponderado por posicion.
    """
    scores = [1 if score >= RELEVANCE_THRESHOLD else 0 for score in _relevance(retrieved, references)]
    if not scores:
        return {"score": 0.0, "verdicts": [], "relevant": 0, "total": 0}
    denominator = sum(scores) + 1e-10
    numerator = sum(
        (sum(scores[: index + 1]) / (index + 1)) * scores[index] for index in range(len(scores))
    )
    return {
        "score": _round(numerator / denominator),
        "verdicts": scores,
        "relevant": sum(scores),
        "total": len(scores),
    }


def context_recall(retrieved: list[str], references: list[str]) -> dict:
    """Recall de RAGAS sobre `reference_contexts`: cada referencia, cubierta o no."""
    if not references:
        return {"score": 0.0, "covered": 0, "total": 0}
    hits = [
        1 if max((dice(content_terms(chunk), content_terms(reference)) for chunk in retrieved),
                 default=0.0) >= RELEVANCE_THRESHOLD else 0
        for reference in references
    ]
    return {"score": _round(sum(hits) / len(hits)), "covered": sum(hits), "total": len(hits)}


# ---------------------------------------------------------------------------
# agregacion del runner
# ---------------------------------------------------------------------------


def mean(values: list[float]) -> float:
    return _round(sum(values) / len(values)) if values else 0.0


def term_weights(documents: list[str]) -> tuple[dict[str, float], frozenset[str], float, frozenset[str]]:
    """IDF y frecuencia de documento sobre el corpus.

    Devuelve ``(pesos, vocabulario, peso_por_defecto, termos_raros)``:

    * ``pesos``: IDF por termino, para que el lector pese "LEI" mas que "ASTS".
    * ``vocabulario``: los terminos que existen en la biblioteca.
    * ``peso_por_defecto``: el IDF de un termino ausente, que es el maximo
      posible (df=0 se trata como df=1, el IDF suavizado estandar).
    * ``terminos_raros``: los que aparecen en 2 documentos o menos. Con 17
      documentos el IDF es demasiado plano para decir "este es el termino
      discriminante de la pregunta", asi que el multi-hop decide con la
      frecuencia de documento, que si separa.
    """
    frequencies: Counter[str] = Counter()
    vocabulary: set[str] = set()
    for document in documents:
        terms = content_terms(document)
        vocabulary |= terms
        frequencies.update(terms)
    total = max(len(documents), 1)
    weights = {
        term: math.log((total + 1) / (count + 1)) for term, count in frequencies.items()
    }
    rare = frozenset(term for term, count in frequencies.items() if count <= RARE_DOCUMENT_FREQUENCY)
    return weights, frozenset(vocabulary), math.log(total + 1), rare


def aggregate(measurements: dict[str, list[float]]) -> dict[str, float]:
    return {name: mean(values) for name, values in measurements.items()}


__all__ = [
    "RELEVANCE_THRESHOLD",
    "SUPPORT_COVERAGE",
    "aggregate",
    "answer_relevancy",
    "content_terms",
    "context_precision",
    "context_recall",
    "dice",
    "faithfulness",
    "is_supported",
    "mean",
    "normalize_text",
    "normalize_term",
    "numbers_in",
    "sentences",
    "term_weights",
]
