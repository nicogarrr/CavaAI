# RAG de conocimiento profesional (cartas, libros, memos)

Estado: **pipeline listo, apagado por defecto, sin corpus real ingerido.**
Flag: `KNOWLEDGE_RAG_ENABLED=false`. API y actor responden 503 / rechazan el trabajo mientras este apagado.

## Stack (decidido, no se reabre)

Qdrant + PostgreSQL + dramatiq + embeddings locales. Piezas nuevas: `llama-index-core` (MIT; solo
`TextNode`/`NodeWithScore`/`QueryBundle`/postprocesadores) y Docling (MIT, ya era dependencia).
No se anade `llama-index-vector-stores-qdrant`: exige `qdrant-client>=1.16` y prod pinea `<1.15`
(servidor Qdrant 1.12.5). El store es propio sobre `qdrant-client` y reutiliza
`app/services/hybrid_retrieval.py` (RRF en cliente). Sin LlamaParse/LlamaCloud/OpenAI.

## Flujo

```
fichero en inbox -> sha256 (dedupe por tenant) -> registro Postgres (queued)
  -> dramatiq cola "knowledge" -> Docling (PDF/EPUB/HTML/DOCX/MD; .txt sin Docling)
  -> secciones (ruta de encabezados, pagina, bbox)
  -> chunks hijo (<=200 wordpieces) dentro de padres (<=900), solape 30
  -> denso MiniLM (fastembed) + sparse BM25 -> Qdrant (hijos) / Postgres (padres)
consulta: denso + sparse -> RRF -> [reranker] -> dedupe de solapes -> padre -> verificacion -> citas [n]
```

- **Tokenizer**: all-MiniLM-L6-v2 trunca a 256 wordpieces (incluye `[CLS]/[SEP]`). El limite del hijo
  (200 por defecto, maximo configurable 250) cuenta el prefijo de contexto (`titulo > seccion: `) y los
  especiales, con el tokenizer real del modelo (copia del de fastembed, sin mutar el compartido).
  Sin modelo cae a un contador heuristico que sobrestima.
- **Padre/hijo**: se indexa solo el hijo; el padre vive en Postgres (`knowledge_rag_parents`) y se
  devuelve como `context`. Una cita es literalmente `padre.text[char_start:char_end]`.
- **Dos corpus**: `evergreen` (letter/book/memo/article/transcript) y `dated` (filing/dataset, exige
  `as_of`). La consulta filtra `evergreen` por defecto; `corpus=dated|any` es explicito.
  Filtros: autor, idioma, tipo, fuente, `published_from/to`, `as_of_from/to`. Todo filtrado por `tenant_id`.
- **BM25**: la coleccion usa `modifier=IDF`; documentos con `embed()`, consultas con `query_embed()`.
- **Reranker**: hook `RerankPostprocessor` (LlamaIndex). Vacio por defecto
  (`KNOWLEDGE_RAG_RERANKER_MODEL`). `Xenova/ms-marco-MiniLM-L-6-v2` (~80 MB, Apache-2.0) es solo ingles;
  para espanol hace falta multilingue (`BAAI/bge-reranker-v2-m3-int8`, ~570 MB, Apache-2.0). No activar
  sin medir en el piloto. `jina-reranker-v2-base-multilingual` es CC-BY-NC: no usar.

## Procedencia por chunk (payload Qdrant)

`title, author, source_uri, filename (inbox), published_date, as_of, language, doc_type, corpus, rights,
source_sha256, text_sha256, parent_id, char_start/char_end, section_path, page_start/page_end,
bboxes[{page,l,t,r,b,origin}], extractor`. Docling aporta pagina y bbox en PDF; EPUB/HTML/MD no tienen
pagina (queda `null`, honesto). `.txt` no tiene ni encabezados ni paginas (warning en el registro).

`verify_citation` comprueba: cita == span del padre, hash de la cita, hash del padre (siempre en
consulta; una cita que falla se descarta y se cuenta en `dropped_unverified`). Para auditar contra el
original: `source_bytes` + `source_sha256` (el fichero no cambio), y `reference_page_text` (texto de la
pagina extraido con otra herramienta). **El original no se guarda en el indice**: se conserva en el inbox/
backup del usuario; `source_sha256` permite comprobar que es el mismo fichero.
Respuesta sin citas verificadas => `abstain: true`.

## Pesos necesarios (no van en el repo)

| Peso | Tamano | Licencia | Cuando |
|---|---|---|---|
| `sentence-transformers/all-MiniLM-L6-v2` (ONNX via fastembed) | ~90 MB | Apache-2.0 | ya en prod |
| `Qdrant/bm25` | ~10 MB | Apache-2.0 | ya usado por el RAG hibrido |
| `docling-project/docling-layout-heron` | ~164 MB medido | Apache-2.0 | PDF |
| `docling-project/docling-models` (TableFormer) | ~342 MB medido (snapshot trae fast 145 + accurate 213) | CDLA-Permissive-2.0 | PDF con tablas |
| reranker (opcional) | 80-570 MB | Apache-2.0 | solo si el piloto lo justifica |

Total medido en sandbox para PDF: ~0.5 GB de cache HuggingFace sobre MiniLM. EPUB/MD/HTML no necesitan
los modelos de layout. Docling se configura **sin OCR, sin VLM, sin ASR, sin enriquecimientos**
(`KNOWLEDGE_RAG_DOCLING_OCR=false`, tablas `fast`). Con el VM al 95% de disco: pre-descargar los pesos
en un volumen con espacio y apuntar `DOCLING_ARTIFACTS_PATH` / `HF_HOME` ahi. Un PDF escaneado sin OCR
falla con "docling extracted no text" en vez de indexar vacio.

`llama-index-core` arrastra 22 paquetes (aiohttp, nltk, tiktoken...). El codigo no usa nltk ni tiktoken
(no se descargan datos en runtime), pero la imagen crece: medir antes de desplegar.

## Configuracion (`app/core/config.py`)

`KNOWLEDGE_RAG_ENABLED`, `_COLLECTION` (`knowledge_rag_v1`, aparte de `portfolio_research_documents`),
`_INBOX_DIR`, `_MAX_FILE_MB` (60), `_MIN_FREE_GB` (3: la ingesta se niega si queda menos), `_CHILD_MAX_TOKENS`
(200), `_CHILD_OVERLAP_TOKENS` (30), `_PARENT_MAX_TOKENS` (900), `_DOCLING_OCR`, `_DOCLING_TABLE_MODE`,
`_RERANKER_MODEL`.

## API (`/api/knowledge-rag`)

`POST /sources` (ruta RELATIVA al inbox + metadatos; sin subir bytes; dedupe por sha256),
`GET /sources`, `GET /sources/{id}`, `POST /query`, `GET /status`.

## Integracion pendiente (la hace el integrador)

1. Migracion `0052_knowledge_rag` (`alembic upgrade head`, paso de deploy).
2. El actor va en la cola **`knowledge`**: ningun worker de `docker-compose.prod.yml` la consume hoy.
   Anadir `knowledge` al `-Q` de un worker de 1 hilo (Docling es pesado en RAM; 12 GB de VM) o un worker
   dedicado. No se ha tocado compose.
3. Montar el inbox (`KNOWLEDGE_RAG_INBOX_DIR`) y activar el flag solo cuando haya disco.
4. Regenerar `openapi.json` / `openapi.generated.ts` (ya hecho en este PR) si cambia la API.

## Plan de piloto (aun no ejecutado)

Objetivo: decidir con datos si el pipeline sirve y si hace falta reranker, antes de ingerir la biblioteca.

1. **Corpus**: 6-10 documentos con licencia clara/uso privado (2 cartas ES, 2 cartas EN, 1-2 libros EPUB,
   1 memo, 1 PDF con tablas fechado como `dated`). ~50-150 MB en disco con vectores.
2. **Preguntas**: 30-50 segun `evals/rag/knowledge_pilot/questions.template.json` (10 factuales, 10
   conceptuales, 6 comparativas entre documentos, 6 con filtro autor/fecha, 6 cruzando ES/EN, 6-8
   sin respuesta). Cada una con `expected_quote` literal copiado del original y el sha256.
3. **Medir** con `app/services/knowledge_rag/pilot.py::score_pilot`: `recall@1/3/6`, `citation_precision`,
   `citation_verifiable_rate` (debe ser 1.0), `abstention_rate` en las sin respuesta.
4. **Umbrales propuestos** (a validar por el usuario): recall@6 >= 0.80, citation_precision >= 0.60,
   verifiable = 1.0, abstencion >= 0.85.
5. **Comparativas baratas**: sin reranker vs ms-marco (EN) vs bge-v2-m3-int8 (ES); child 160 vs 200 tokens;
   pesos RRF dense/sparse 1:1 vs 1:2.
6. Registrar tiempos (Docling s/pagina en el A1 ARM) y disco real antes de escalar.

## Limites declarados

- Sin corpus real ingerido ni piloto ejecutado; las metricas de recall NO existen todavia.
- Extraccion verificada con Docling real en MD, EPUB sintetico y un PDF sintetico de 2 paginas (paginas y
  bbox correctos). No probado con libros reales largos, PDFs escaneados ni el A1 ARM del VM.
- Tablas: se parten por filas sin repetir la cabecera en cada hijo.
- El chunker corta frases con una regex (abreviaturas como "Mr." pueden partir una frase; la cita sigue siendo literal).
- Qdrant local (`:memory:`) en los tests ignora los indices de payload; contra servidor 1.12.5 real no probado.
- La verificacion contra el original exige conservar el fichero; no se guarda copia.
- Embeddings multilingues: MiniLM es principalmente ingles; el recall en ES esta por medir (BM25 compensa en parte).
