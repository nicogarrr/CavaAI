"""RAG de conocimiento profesional de inversion (cartas, libros, memos).

Pipeline: fuente -> checksum/dedupe -> Docling -> chunks por seccion (padre/hijo,
conscientes del tokenizer) -> denso+sparse local -> RRF -> hook de reranker.
Qdrant guarda los hijos cortos; Postgres guarda registro de fuentes y padres.

Este paquete no importa nada pesado al cargarse (docling, fastembed, qdrant).
"""
