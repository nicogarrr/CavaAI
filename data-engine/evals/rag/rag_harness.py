"""Harness del golden set RAG: recuperacion real, lector determinista, red bloqueada.

Tres piezas, y por que estan separadas:

* ``network_guard``: bloquea ``socket.socket.connect`` y ``socket.create_connection``
  a todo lo que no sea loopback. El runner de evals no puede llamar a un LLM ni
  a un proveedor de metricas aunque alguien lo anada por error: si lo intenta,
  revienta con ``NetworkBlocked`` en vez de devolver un numero que nadie
  audito. Descargar el modelo de embeddings es la unica excepcion, y solo si el
  operador lo pide explicitamente con ``RAG_EVALS_ALLOW_MODEL_DOWNLOAD=1``.
* ``RealRetriever``: el pipeline de verdad. ``DocumentIngestionService`` trocea
  los documentos del corpus, ``RAGIndex`` los indexa en Qdrant con
  all-MiniLM-L6-v2 y ``RAGIndex.search`` recupera. Si algo de eso no puede
  correr, el runner devuelve exit 1: no se degrada a un stub en silencio
  (mismo criterio que "RAG activation tests skipped -> exit 1" en ci.yml).
* ``StubRetriever``: solo para ``--dry-run``. Recuperacion lexical pura, sin
  modelo y sin Qdrant, para iterar el golden set en local en menos de un
  segundo. El modo dry-run imprime sus numeros marcados como NO GATEABLES.
* ``ExtractiveReader``: el "generador" es un extractor determinista, no un LLM.
  Selecciona la frase del contexto recuperado que mas cubre los terminos de la
  pregunta y, si cubre terminos nuevos, anade una segunda frase de otro
  documento (multi-hop). Si ninguna llega al umbral de soporte, se abstiene.
"""

from __future__ import annotations

import math
import os
import re
import socket
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from evals.rag.rag_gates import ABSTENTION_MARKER, CITATION_PREFIX
from evals.rag.rag_metrics import content_terms, numbers_in, sentences, term_weights

# Hugging Face se pone en modo offline al IMPORTAR este modulo, que es antes de
# que nadie importe sentence_transformers: si se hiciera mas tarde,
# huggingface_hub ya habria leido la constante y el embedder haria un GET de
# comprobacion que el guardian bloquea. RAG_EVALS_ALLOW_MODEL_DOWNLOAD=1 es la
# unica forma de dejar salir al runner a por el modelo, y entonces no se fuerza
# offline. setdefault: una variable ya puesta en el entorno manda.
if os.getenv("RAG_EVALS_ALLOW_MODEL_DOWNLOAD") != "1":
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# Soporte minimo (cobertura IDF de los terminos de la pregunta) para dar una
# respuesta. Por debajo de esto el lector no afirma nada y devuelve la
# abstention.
MIN_ANSWER_SUPPORT = 0.34
# Por encima de este soporte, la primera frase se considera respuesta completa
# y NO se anade una segunda frase de otro documento. Sin este tope, el lector
# contestaba "¿cuanto pesa el .mdb de 8.09 MB?" con la frase correcta MAS la
# frase de la ficha hermana, que tambien menciona .mdb y el numero de ficha.
# Ese es el fallo tipico del multi-sentence RAG: mas cobertura, mas ruido.
MAX_SINGLE_SENTENCE_SUPPORT = 0.72
# Soporte minimo de la segunda frase de un multi-hop: solo se anade si aporta
# terminos de la pregunta que la primera no cubria.
MIN_SECOND_SENTENCE_GAIN = 0.15
# Y la segunda frase tiene que ser una respuesta, no una mencion de paso: una
# frase que comparte cuatro palabras sueltas con la pregunta y no la contesta
# ("Ninguno de los 3 emisores de la CNMV figura en el COMPANY_MASTER") no vale
# como segundo salto, aunque las frases se solapen en vocabulario.
MIN_SECOND_SENTENCE_COVERAGE = 0.20
MIN_SECOND_SENTENCE_NEW_TERMS = 2
MAX_SENTENCES = 2
# 8 y no los 5 por defecto de RAGIndex.search: con 17 documentos y 14 fichas
# ITU, un top-5 puede llenarse entero de chunks de la ficha hermana y la
# pregunta se queda sin su documento. El limite se imprime en el informe para
# que el numero se lea con su contexto.
RETRIEVAL_TOP_K = 8

# Una frase que NIEGA lo que la pregunta pide no sostiene una respuesta
# afirmativa. Sin esta comprobacion, el lector cita "no son la fecha de
# publicacion" como si fuera la fecha de publicacion, que es el modo de
# alucinacion mas sutil de los extractivos: no inventa nada, invierte el signo.
#
# NO es un parser de negacion: es la lista de las formas de negacion que este
# corpus usa. Si el corpus anadiera "no registra", la puerta de abstention
# bajaria y se veria en el numero, en vez de pasar desapercibida.
NEGATION_RE = re.compile(
    r"\b(no son|no se infiere|no consta|no debe|no declara|ningun|ninguna|ninguno|nunca)\b",
    re.IGNORECASE,
)

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0", ""})
# Hosts de Hugging Face, solo accesibles si el operador pide la descarga.
MODEL_HOSTS = frozenset({
    "huggingface.co",
    "cdn-lfs.huggingface.co",
    "cdn-lfs-us-1.hf.co",
    "cas-bridge.xethub.hf.co",
    "transfer.xethub.hf.co",
})

ABSTENTION_TEXT = f"No encuentro esa informacion: {ABSTENTION_MARKER}."


def get_settings_qdrant_url() -> str:
    """La URL de Qdrant que se esta usando, para poder nombrar el fallo."""
    try:
        from app.core.config import get_settings

        return get_settings().qdrant_url
    except Exception:
        return os.getenv("QDRANT_URL", "desconocida")


class NetworkBlocked(RuntimeError):
    """El runner intento salir a la red. El guardian convierte el silencioso en un fallo."""


class HarnessUnavailable(RuntimeError):
    """El pipeline real no puede correr. El runner debe salir con 1, no con un stub."""


@dataclass
class NetworkGuard:
    """Guardian de red: solo loopback, mas una excepcion opt-in para el modelo.

    Guarda las funciones originales y las restaura al salir, para que importar
    el harness no deje el proceso con las salidas de red cortadas para siempre.
    """

    allow_model_download: bool = False
    _original_connect: object = field(default=None, repr=False)
    _original_create_connection: object = field(default=None, repr=False)
    _extra_hosts: set[str] = field(default_factory=set, repr=False)
    _installed: bool = field(default=False, repr=False)

    def _permitted(self, address) -> bool:
        if isinstance(address, tuple) and address:
            host = str(address[0])
        else:
            host = str(address)
        if host in LOOPBACK_HOSTS:
            return True
        return host in self._extra_hosts

    def _check(self, address) -> None:
        if not self._permitted(address):
            raise NetworkBlocked(
                f"conexion bloqueada por el guardian del harness RAG: {address!r}. "
                "El runner de evals no habla con la red ni con proveedores de LLM."
            )

    def install(self) -> NetworkGuard:
        if self._installed:
            return self
        self._original_connect = socket.socket.connect
        self._original_create_connection = socket.create_connection
        original_connect = self._original_connect
        original_create_connection = self._original_create_connection
        guard = self

        def guarded_connect(sock, address, *args, **kwargs):  # type: ignore[no-untyped-def]
            guard._check(address)
            return original_connect(sock, address, *args, **kwargs)

        def guarded_create_connection(address, *args, **kwargs):  # type: ignore[no-untyped-def]
            guard._check(address)
            return original_create_connection(address, *args, **kwargs)

        socket.socket.connect = guarded_connect  # type: ignore[method-assign]
        socket.create_connection = guarded_create_connection  # type: ignore[assignment]
        self._installed = True
        return self

    def allow_model_hosts(self) -> None:
        """Permite Hugging Face durante la carga del embedder, y solo si se pidio."""
        if self.allow_model_download:
            self._extra_hosts |= set(MODEL_HOSTS)

    def restore(self) -> None:
        if not self._installed:
            return
        socket.socket.connect = self._original_connect  # type: ignore[method-assign]
        socket.create_connection = self._original_create_connection  # type: ignore[assignment]
        self._installed = False


# ---------------------------------------------------------------------------
# lector determinista
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    doc_id: str
    text: str
    rank: int
    index: int
    coverage: float


@dataclass(frozen=True)
class Lexicon:
    """Estadisticas del corpus: IDF y terminos raros, para el lector."""

    weights: dict[str, float]
    vocabulary: frozenset[str]
    default_weight: float
    rare: frozenset[str]

    def weight(self, term: str) -> float:
        return self.weights.get(term, self.default_weight)

    def absent(self, question: str) -> frozenset[str]:
        return frozenset(content_terms(question) - self.vocabulary)

    def coverage(self, question_terms: set[str], text: str) -> float:
        if not question_terms:
            return 0.0
        present = content_terms(text)
        total = sum(self.weight(term) for term in question_terms)
        if total <= 0:
            return 0.0
        got = sum(self.weight(term) for term in question_terms & present)
        return got / total


def build_lexicon(documents: list[str]) -> Lexicon:
    weights, vocabulary, default_weight, rare = term_weights(documents)
    return Lexicon(
        weights=weights, vocabulary=vocabulary, default_weight=default_weight, rare=rare
    )


def rank_candidates(
    question: str, retrieved: list[dict], lexicon: Lexicon | None = None
) -> list[Candidate]:
    """Frases del contexto recuperado, ordenadas por cobertura IDF de la pregunta.

    El desempate es total y explicito (rank, indice, doc_id, texto): dos
    ejecuciones sobre el mismo contexto devuelven la misma frase, que es lo que
    hace gateable la metrica.
    """
    question_terms = content_terms(question)
    if not question_terms:
        return []
    if lexicon is None:
        lexicon = build_lexicon([hit.get("text") or "" for hit in retrieved])
    candidates: list[Candidate] = []
    for rank, hit in enumerate(retrieved):
        for index, sentence in enumerate(sentences(hit.get("text") or "")):
            terms = content_terms(sentence)
            if not terms:
                continue
            coverage = lexicon.coverage(question_terms, sentence)
            candidates.append(
                Candidate(
                    doc_id=str(hit.get("doc_id") or ""),
                    text=sentence,
                    rank=rank,
                    index=index,
                    coverage=coverage,
                )
            )
    candidates.sort(
        key=lambda c: (
            -round(c.coverage, 6),
            c.rank,
            c.index,
            c.doc_id,
            c.text,
        )
    )
    return candidates


def select_sentences(
    question: str, retrieved: list[dict], lexicon: Lexicon | None = None
) -> list[Candidate]:
    """Primera frase por encima del umbral, mas una segunda que aporte algo nuevo.

    Dos reglas de abstention:

    1. Si la mejor evidencia es una negacion ("no son la fecha de
       publicacion"), el lector se abstiene en vez de invertir el signo.
    2. Si ninguna frase llega al umbral de soporte, se abstiene.

    NO hay una regla del tipo "si la pregunta nombra algo ausente de la
    biblioteca, abstention garantizada": con esa regla `abstention_accuracy`
    valdria 1.0 por construccion y no mediria nada. El golden set garantiza por
    contrato (test_rag_golden_dataset.py) que las preguntas respondibles
    recuperan contexto, y que las que deben negarse lo hacen; el trabajo de
    decidir es del umbral.
    """
    if not retrieved:
        return []
    candidates = rank_candidates(question, retrieved, lexicon)
    if not candidates or candidates[0].coverage < MIN_ANSWER_SUPPORT:
        return []
    if NEGATION_RE.search(candidates[0].text):
        return []
    chosen = [candidates[0]]
    if len(candidates) < 2 or len(chosen) >= MAX_SENTENCES:
        return chosen
    if candidates[0].coverage >= MAX_SINGLE_SENTENCE_SUPPORT:
        return chosen
    question_terms = content_terms(question)
    covered = content_terms(candidates[0].text)
    total = sum(lexicon.weight(term) for term in question_terms) if lexicon else len(question_terms)
    if total <= 0:
        return chosen
    # El segundo salto tiene que tocar un termino RARO de la pregunta, es decir
    # uno que solo aparece en 2 documentos o menos de la biblioteca. Es lo que
    # separa un multi-hop real de una frase de ruido: "cuantas bandas en la
    # ficha D2026-84958 y en la J2026-70632" necesita la ficha con el 70632, y
    # en cambio "el unico emisor con FCC" no necesita una frase que hable de
    # emisores con riesgo dilution aunque comparta cuatro palabras.
    required = lexicon.rare if lexicon is not None else question_terms
    for candidate in candidates[1:]:
        if candidate.doc_id == chosen[0].doc_id:
            continue
        if candidate.coverage < MIN_SECOND_SENTENCE_COVERAGE:
            continue
        new = question_terms & content_terms(candidate.text) - covered
        if len(new) < MIN_SECOND_SENTENCE_NEW_TERMS:
            continue
        if not (new & required):
            continue
        if sum(lexicon.weight(term) for term in new) / total >= MIN_SECOND_SENTENCE_GAIN:
            covered |= content_terms(candidate.text)
            chosen.append(candidate)
            break
    return chosen


def compose_answer(
    question: str, retrieved: list[dict], lexicon: Lexicon | None = None
) -> str:
    """Respuesta del lector: frases soportadas + linea de fuentes.

    Devolver el mismo TEXTO que las puertas leen (no un campo aparte) es
    deliberado: si el lector dice que cito una fuente, esta escrita.
    """
    chosen = select_sentences(question, retrieved, lexicon)
    if not chosen:
        return ABSTENTION_TEXT
    prose = " ".join(candidate.text for candidate in chosen)
    sources = list(dict.fromkeys(candidate.doc_id for candidate in chosen))
    return f"{prose}\n{CITATION_PREFIX} {', '.join(sources)}"


# ---------------------------------------------------------------------------
# recuperador stub (--dry-run)
# ---------------------------------------------------------------------------


class StubRetriever:
    """Recuperacion lexical TF-IDF sobre los chunks del corpus. Sin modelo ni Qdrant."""

    name = "stub_lexical"
    gateable = False

    def __init__(self, documents: list[dict]) -> None:
        self.documents = documents
        self._chunks = [
            {"doc_id": doc["id"], "text": text} for doc in documents for text in _chunk(doc["content"])
        ]
        self._df = Counter()
        for chunk in self._chunks:
            self._df.update(set(content_terms(chunk["text"])))

    def _idf(self, term: str) -> float:
        total = len(self._chunks) or 1
        return math.log(1 + total / (1 + self._df.get(term, 0)))

    def search(self, query: str, limit: int = RETRIEVAL_TOP_K) -> list[dict]:
        query_terms = content_terms(query)
        if not query_terms:
            return []
        scored = []
        for chunk in self._chunks:
            terms = content_terms(chunk["text"])
            if not terms:
                continue
            score = sum(self._idf(term) for term in query_terms & terms)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: (-round(item[0], 9), item[1]["doc_id"], item[1]["text"]))
        return [
            {"doc_id": chunk["doc_id"], "text": chunk["text"], "score": round(score, 6)}
            for score, chunk in scored[:limit]
        ]

    def close(self) -> None:
        return None


def _chunk(content: str, max_chars: int = 1200) -> list[str]:
    """Troceo por parrafos, al estilo del chunker de la ingesta real."""
    blocks = [block.strip() for block in str(content or "").split("\n") if block.strip()]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for block in blocks:
        if size + len(block) > max_chars and current:
            chunks.append("\n".join(current))
            current, size = [], 0
        current.append(block)
        size += len(block) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks or [str(content or "")]


# ---------------------------------------------------------------------------
# recuperador real (Qdrant + all-MiniLM-L6-v2)
# ---------------------------------------------------------------------------

EVAL_COLLECTION = "rag_eval_v1_documents"
EVAL_SOURCE_TYPE = "rag_eval_v1"
EVAL_TICKER_BUCKET = "RAGEVAL"


class RealRetriever:
    """Pipeline real: ingesta -> troceado -> Qdrant -> busqueda vectorial.

    Reutiliza ``DocumentIngestionService`` y ``RAGIndex`` tal cual, con la misma
    base SQLite en memoria que usa ``tests/test_rag_activation.py``. Si el
    embedder, Qdrant o la ingesta no funcionan, lanza ``HarnessUnavailable``.
    """

    name = "qdrant_all-MiniLM-L6-v2"
    gateable = True

    def __init__(self, documents: list[dict], guard: NetworkGuard | None = None) -> None:
        self.guard = guard
        self.documents = documents
        self.db = None
        self.engine = None
        self.tenant_id: int | None = None
        self.chunks_indexed = 0
        self._point_ids: list[str] = []
        self._db_id_to_corpus_id: dict[str, str] = {}
        self._by_id: dict[str, dict] | None = None
        self._prepare_env()
        self._reset_collection()
        self._bootstrap()
        self._ingest()
        self._verify()

    def _prepare_env(self) -> None:
        # Flags de la ingesta vectorial y apagado de todo lo que hable o pague.
        os.environ["CAVAAI_ENABLE_VECTOR_INGEST"] = "1"
        os.environ["CAVAAI_ENABLE_VECTOR_SEARCH"] = "1"
        os.environ["CAVAAI_ENABLE_AUTO_KPI_EXTRACTION"] = "0"
        os.environ["CAVAAI_ENABLE_AUTO_RESEARCH"] = "0"
        os.environ["APP_ENV"] = "test"
        # El modo offline de Hugging Face se activa al importar este modulo (arriba
        # del fichero). Aqui solo se abre la excepcion de la descarga, y solo si
        # el modelo no esta ya en la cache local: bajar 90 MB sin que nadie lo
        # haya pedido seria peor que fallar con un mensaje claro.
        if self.guard is not None and self.guard.allow_model_download and not self._model_is_cached():
            self.guard.allow_model_hosts()

    @staticmethod
    def _model_is_cached() -> bool:
        root = Path(
            os.getenv("HF_HOME")
            or (Path.home() / ".cache" / "huggingface" / "hub")
        )
        return (root / "models--sentence-transformers--all-MiniLM-L6-v2").exists()

    def _reset_collection(self) -> None:
        """Empezar de cero, siempre.

        Una corrida anterior que murio antes del ``close()`` (por ejemplo, un
        Qdrant caido a mitad) deja puntos en la coleccion de evaluacion. Si la
        siguiente corrida los hereda, los 8 hits de una pregunta vienen de dos
        corridas distintas y las metricas de recuperacion miden un estado que
        nadie puede reproducir. Borrar la coleccion entera es lo unico que
        hace la corrida reproducible.

        Aqui, y no en el ``except`` de mas abajo, se convierte un Qdrant
        inalcanzable en ``HarnessUnavailable``: el runner tiene que salir con 1
        y un mensaje, no con un traceback de urllib3.
        """
        from app.services.rag import RAGIndex

        try:
            client = RAGIndex().client()
            existing = [c.name for c in client.get_collections().collections]
        except Exception as exc:
            raise HarnessUnavailable(
                f"Qdrant no responde en {get_settings_qdrant_url()}: {type(exc).__name__}"
            ) from exc
        if EVAL_COLLECTION in existing:
            client.delete_collection(collection_name=EVAL_COLLECTION)

    def _bootstrap(self) -> None:
        try:
            from sqlalchemy import create_engine, select
            from sqlalchemy.orm import Session

            from app.core.database import Base
            from app.models import Company, Tenant
        except Exception as exc:  # pragma: no cover - entorno sin la app
            raise HarnessUnavailable(f"no se pudo importar la app: {exc}") from exc

        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        tenant = Tenant(external_id="rag-eval-v1", name="RAG eval golden set")
        self.db.add(tenant)
        self.db.flush()
        self.tenant_id = tenant.id
        self.db.info["tenant_id"] = tenant.id

        tickers = {doc["ticker"] for doc in self.documents}
        for ticker in sorted(tickers):
            existing = self.db.scalar(select(Company).where(Company.ticker == ticker))
            if existing is not None:
                continue
            self.db.add(
                Company(
                    ticker=ticker,
                    name="RAG eval corpus bucket" if ticker == EVAL_TICKER_BUCKET else ticker,
                    exchange="EVAL",
                    currency="USD",
                    sector="Evaluation",
                    industry="Evaluation",
                    company_type="standard",
                    valuation_model="standard_dcf",
                    special_sources=[],
                    special_risks=[],
                    factor_tags=[],
                )
            )
        self.db.flush()

    def _ingest(self) -> None:
        try:
            from sqlalchemy import select

            from app.models import Document, DocumentChunk
            from app.services.document_ingestion_service import DocumentIngestionService
        except Exception as exc:  # pragma: no cover
            raise HarnessUnavailable(f"no se pudo importar la ingesta: {exc}") from exc

        service = DocumentIngestionService()
        indexed = 0
        document_ids: list[int] = []
        for doc in self.documents:
            result = service.ingest_bytes(
                self.db,
                ticker=doc["ticker"],
                title=doc["title"],
                content=doc["content"].encode("utf-8"),
                filename=f"{doc['id']}.md",
                source_type=EVAL_SOURCE_TYPE,
                content_type="text/markdown",
            )
            if result.get("status") != "ingested":
                raise HarnessUnavailable(
                    f"{doc['id']}: la ingesta real devolvio status={result.get('status')}: "
                    f"{result.get('warnings')}"
                )
            rag = result.get("rag") or {}
            if rag.get("error"):
                raise HarnessUnavailable(f"{doc['id']}: RAGIndex no pudo indexar: {rag['error']}")
            indexed += int(rag.get("chunks_indexed") or 0)
            document_ids.append(int(result["document_id"]))
            self._db_id_to_corpus_id[str(result["document_id"])] = str(doc["id"])
        # Los puntos de Qdrant se borran por su id real (UUID), no por doc_id:
        # el payload guarda el UUID de DocumentChunk, y borrar por el id
        # equivocado deja basura en una coleccion que comparte con la app.
        self._point_ids = [
            str(point_id)
            for point_id in self.db.scalars(
                select(DocumentChunk.qdrant_point_id).where(
                    DocumentChunk.document_id.in_(document_ids),
                    DocumentChunk.qdrant_point_id.is_not(None),
                )
            ).all()
        ]
        assert Document is not None  # la importacion documenta el modelo usado
        self.chunks_indexed = indexed
        if indexed == 0:
            raise HarnessUnavailable("la ingesta real no indexo ni un chunk en Qdrant")

    def _verify(self) -> None:
        """Que la busqueda real devuelva algo antes de medir nada.

        Sin este paso, un Qdrant que acepta la escritura pero no la lectura
        produciria 0 hits y unas metricas de 0.0 que parecen un resultado
        honesto cuando en realidad son un fallo de infraestructura.
        """
        try:
            probe = self.search(self.documents[0]["content"].split("\n")[0], limit=1)
        except Exception as exc:
            raise HarnessUnavailable(f"la busqueda vectorial real fallo: {exc}") from exc
        if not probe:
            raise HarnessUnavailable(
                "la busqueda vectorial real devolvio 0 hits para un texto que esta en el corpus"
            )

    def search(self, query: str, limit: int = RETRIEVAL_TOP_K) -> list[dict]:
        """Busqueda real. Un fallo de Qdrant aqui NO es "cero resultados".

        ``RAGIndex.search`` devuelve ``[]`` cuando el embedder o Qdrant fallan,
        y un ``[]`` indistinguible de "no hay nada en la biblioteca" convertiria
        un fallo de infraestructura en un 0.0 que parece un resultado honesto.
        """
        from app.services.rag import RAGIndex

        try:
            hits = RAGIndex().search(query, limit=limit, tenant_id=self.tenant_id)
        except Exception as exc:
            raise HarnessUnavailable(
                f"RAGIndex.search fallo contra {get_settings_qdrant_url()}: {type(exc).__name__}"
            ) from exc
        if not hits:
            return []
        # El payload de RAGIndex lleva el document_id de la BASE DE DATOS (un
        # entero autoincremental), no el doc_id del corpus. Sin este mapa, los
        # 55 hits se descartarian y las metricas de recuperacion serian 0.0
        # Pickapara un fallo de mapeo.
        rows = []
        for hit in hits:
            doc_id = self._db_id_to_corpus_id.get(str(hit.get("document_id") or ""))
            if doc_id is None:
                continue
            rows.append(
                {
                    "doc_id": doc_id,
                    "text": hit.get("text") or "",
                    "score": round(float(hit.get("score") or 0.0), 6),
                }
            )
        rows.sort(key=lambda row: (-row["score"], row["doc_id"], row["text"]))
        return rows[:limit]

    def _documents_by_id(self) -> dict[str, dict]:
        if self._by_id is None:
            self._by_id = {str(doc["id"]): doc for doc in self.documents}
        return self._by_id

    def close(self) -> None:
        try:
            from app.services.rag import RAGIndex

            RAGIndex().client().delete_collection(collection_name=EVAL_COLLECTION)
        except Exception:
            pass
        if self.db is not None:
            self.db.close()
        if self.engine is not None:
            self.engine.dispose()
        self._purge_storage()

    def _purge_storage(self) -> None:
        """Borra los originales que dejo la ingesta en storage/raw.

        ``DocumentStore`` escribe en ``storage/raw/tenant-<id>/<TICKER>/<categoria>``
        cuando hay tenant (y en ``storage/raw/<TICKER>/<categoria>`` cuando no lo
        hay), asi que se limpian las dos formas. Sin esto, cada corrida dejaba
        17 ficheros .md en el arbol de trabajo.
        """
        roots = [Path("storage/raw")]
        if self.tenant_id is not None:
            roots.append(Path("storage/raw") / f"tenant-{self.tenant_id}")
        for root in roots:
            for directory in root.glob(f"*/{EVAL_SOURCE_TYPE}"):
                for path in directory.glob("*"):
                    if path.is_file():
                        path.unlink(missing_ok=True)
                for parent in (directory, directory.parent, root):
                    try:
                        parent.rmdir()
                    except OSError:
                        break


def isolate_collection() -> None:
    """El harness indexa en una coleccion PROPIA, no en la de la aplicacion.

    ``RAGIndex.collection_name`` es ``portfolio_research_documents``, la misma
    que usa el producto: indexar ahi 17 documentos de evaluacion contaminaria el
    indice de un Qdrant local de desarrollo, y los hits de otra corrida (o de la
    app) se mezclarian con los del golden set. Se sobreescribe el atributo de
    clase SOLO en el proceso del runner y la coleccion se borra al terminar,
    asi que la evaluacion no deja rastro y no puede falsear un resultado.
    """
    from app.services.rag import RAGIndex

    RAGIndex.collection_name = EVAL_COLLECTION


def memoize_embedder() -> None:
    """Una sola carga de all-MiniLM-L6-v2 por proceso del harness.

    ``RAGIndex._embedder()`` construye un ``SentenceTransformer`` nuevo en cada
    llamada, y el harness indexa 17 documentos y hace 55 busquedas: sin esto
    son 72 cargas del mismo modelo de 90 MB. El monkeypatch vive SOLO en el
    proceso del runner; ``app/`` no se toca, y el embedder que se usa es
    exactamente el de produccion.
    """
    from app.services.rag import RAGIndex

    if getattr(RAGIndex, "_rag_eval_memoized", False):
        return
    original = RAGIndex._embedder
    cache: dict[str, object] = {}

    def memoized(self):  # type: ignore[no-untyped-def]
        key = "all-MiniLM-L6-v2"
        if key not in cache:
            cache[key] = original(self)
        return cache[key]

    RAGIndex._embedder = memoized  # type: ignore[method-assign]
    RAGIndex._rag_eval_memoized = True  # type: ignore[attr-defined]


def build_retriever(documents: list[dict], dry_run: bool, guard: NetworkGuard) -> object:
    if dry_run:
        return StubRetriever(documents)
    isolate_collection()
    memoize_embedder()
    return RealRetriever(documents, guard)


__all__ = [
    "ABSTENTION_TEXT",
    "Candidate",
    "HarnessUnavailable",
    "Lexicon",
    "MIN_ANSWER_SUPPORT",
    "NetworkBlocked",
    "NetworkGuard",
    "RealRetriever",
    "StubRetriever",
    "build_lexicon",
    "build_retriever",
    "compose_answer",
    "isolate_collection",
    "memoize_embedder",
    "numbers_in",
    "rank_candidates",
    "select_sentences",
]
