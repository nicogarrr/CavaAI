import os
import re
from datetime import date
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.llm.factory import create_llm_provider
from app.models import (
    Claim,
    Company,
    Document,
    DocumentChunk,
    EvidenceSuggestion,
    FinancialFact,
    MarketPrice,
    NewsEvent,
    ResearchSession,
    ThesisSection,
    ThesisVersion,
)
from app.schemas import ChatResponse
from app.services.chat_synthesis_service import ChatSynthesisService
from app.services.claim_scope import live_claims
from app.services.company_resolver import resolve_company
from app.services.library_context import retrieve_library_context
from app.services.memory_service import MemoryService
from app.services.source_hierarchy_service import source_tier_key

KEY_FACT_METRICS = [
    "revenue",
    "free_cash_flow",
    "operating_cash_flow",
    "net_income",
    "net_debt",
    "cash",
    "total_debt",
    "shares_diluted",
]

def _decimal_to_float(value: Decimal | int | float | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _short(text: str, limit: int = 420) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."



_SMALL_TALK_RE = re.compile(
    r"^\s*(hola|buenas|buenos dias|buenas tardes|buenas noches|hey|hi|hello|"
    r"que tal|como estas|gracias|muchas gracias|ok|vale|adios|hasta luego)"
    r"[\s!.,¡¿?]*$",
    re.IGNORECASE,
)
_SMALL_TALK_ANSWER = (
    "¡Hola! Soy el asistente de CavaAI. Puedo responder a cualquier tema "
    "y, ademas, tengo acceso a tu cartera, tus tesis, tu research y tus "
    "documentos. Preguntame lo que quieras."
)


_FINANCIAL_INTENT_RE = re.compile(
    r"(?i)\b(cotiza(?:ción|do)?|precio|rentabilidad|dividendo|beneficio|"
    r"sube|baja|cae|earnings|a cuánto|a cuanto|cuánto vale|cuanto vale)\b"
)
_FINANCIAL_ABSTAIN_ANSWER = (
    "No tengo datos de mercado sobre eso en tu research. Si te refieres a "
    "una empresa, dime su nombre o ticker y lo consulto."
)


class ChatService:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.memory = MemoryService()
        self.provider = provider or create_llm_provider()

    def _resolve_company(self, db: Session, question: str, scope: str, ticker: str | None) -> Company | None:
        if ticker:
            return resolve_company(db, ticker)
        if scope == "portfolio":
            return None
        # Índice por ticker + regex de palabra completa: evita falsos
        # positivos por substring ("A" dentro de "APPLE", "IT" en "WITH")
        # y no hace un scan substring por fila.
        companies = list(db.scalars(select(Company)).all())
        by_ticker = {company.ticker.upper(): company for company in companies}
        tokens = re.findall(r"[A-Z0-9][A-Z0-9.\-]*", question.upper())
        for token in tokens:
            if token in by_ticker:
                return by_ticker[token]
        for candidate in companies:
            if re.search(rf"\b{re.escape(candidate.ticker)}\b", question, re.IGNORECASE):
                return candidate
        return None

    def _latest_thesis(self, db: Session, company: Company) -> ThesisVersion | None:
        return db.scalar(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(desc(ThesisVersion.version))
            .limit(1)
        )

    def _key_facts(self, db: Session, company: Company, limit: int = 8) -> list[FinancialFact]:
        # One query instead of one per metric: pick the latest fact per
        # metric in Python, preserving the per-metric ordering contract.
        rows = db.scalars(
            select(FinancialFact)
            .where(
                FinancialFact.company_id == company.id,
                FinancialFact.metric.in_(KEY_FACT_METRICS),
            )
            .order_by(
                FinancialFact.metric,
                FinancialFact.fiscal_year.desc().nullslast(),
                desc(FinancialFact.created_at),
                desc(FinancialFact.id),
            )
        ).all()
        latest: dict[str, FinancialFact] = {}
        for row in rows:
            latest.setdefault(row.metric, row)
        facts = [latest[m] for m in KEY_FACT_METRICS if m in latest]
        return facts[:limit]

    def _sections(self, db: Session, thesis: ThesisVersion | None, limit: int = 6) -> list[ThesisSection]:
        if not thesis:
            return []
        return list(
            db.scalars(
                select(ThesisSection)
                .where(ThesisSection.thesis_version_id == thesis.id)
                .order_by(ThesisSection.order_index, ThesisSection.section_key)
                .limit(limit)
            ).all()
        )

    def _claims(self, db: Session, company: Company, limit: int = 8) -> list[Claim]:
        # The live claims only: the chat answers about the current thesis, so
        # citing a claim from a superseded version answers a different question.
        return live_claims(db, company, limit=limit)

    def _recent_news(self, db: Session, company: Company, limit: int = 4) -> list[NewsEvent]:
        return list(
            db.scalars(
                select(NewsEvent)
                .where(NewsEvent.company_id == company.id)
                .order_by(desc(NewsEvent.date))
                .limit(limit)
            ).all()
        )

    def _recent_sessions(self, db: Session, company: Company | None, limit: int = 4) -> list[ResearchSession]:
        statement = select(ResearchSession).order_by(desc(ResearchSession.updated_at)).limit(limit)
        if company:
            statement = statement.where(ResearchSession.company_id == company.id)
        return list(db.scalars(statement).all())

    def _document_chunks(self, db: Session, company: Company, question: str, limit: int = 4) -> list[tuple[DocumentChunk, Document]]:
        query_terms = [term.lower() for term in question.split() if len(term) >= 4]
        rows = db.execute(
            select(DocumentChunk, Document)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(Document.company_id == company.id)
            .order_by(desc(Document.published_at), DocumentChunk.chunk_index)
            .limit(80)
        ).all()
        scored: list[tuple[int, DocumentChunk, Document]] = []
        for chunk, document in rows:
            lowered = chunk.text.lower()
            overlap = sum(1 for term in query_terms if term in lowered)
            scored.append((overlap, chunk, document))
        scored.sort(key=lambda item: (item[0], item[2].published_at is not None), reverse=True)
        return [(chunk, document) for _, chunk, document in scored[:limit]]

    def _rag_chunks(
        self,
        db: Session,
        question: str,
        company: Company | None,
        limit: int = 4,
    ) -> list[dict]:
        if os.getenv("CAVAAI_ENABLE_VECTOR_CHAT") != "1":
            return []
        try:
            from app.services.rag import RAGIndex

            hits = RAGIndex().search(
                question,
                ticker=company.ticker if company else None,
                limit=limit,
                tenant_id=db.info.get("tenant_id"),
            )
            tenant_id = db.info.get("tenant_id")
            if type(tenant_id) is not int or tenant_id <= 0:
                return []
            rows = []
            seen = set()
            for hit in hits:
                chunk_id = hit.get("entity_id")
                if hit.get("entity_type") != "document_chunk" or type(chunk_id) is not int or chunk_id in seen:
                    continue
                statement = (
                    select(DocumentChunk, Document)
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .where(DocumentChunk.id == chunk_id, DocumentChunk.tenant_id == tenant_id,
                           Document.tenant_id == tenant_id)
                )
                if company:
                    statement = statement.where(Document.company_id == company.id)
                row = db.execute(statement).first()
                if not row:
                    continue
                chunk, document = row
                if not chunk.text.strip() or not chunk.qdrant_point_id or str(hit.get("point_id")) != chunk.qdrant_point_id:
                    continue
                seen.add(chunk_id)
                rows.append({
                    "point_id": chunk.qdrant_point_id, "entity_id": chunk.id,
                    "document_id": document.id, "title": document.title,
                    "source_type": document.source_type, "text": chunk.text,
                    "url": document.source_url, "chunk_index": chunk.chunk_index,
                })
            return rows
        except Exception:
            return []

    def _source_entry(self, kind: str, source_id: int | str | None, title: str, **extra) -> dict:
        payload = {
            "type": kind,
            "id": source_id,
            "title": title,
        }
        payload.update({key: value for key, value in extra.items() if value is not None})
        return payload

    async def answer(
        self,
        db: Session,
        question: str,
        scope: str,
        ticker: str | None,
        *,
        enable_debate: bool | None = None,
        use_jev: bool = True,
    ) -> ChatResponse:
        if _SMALL_TALK_RE.match(question or ""):
            return ChatResponse(
                answer=_SMALL_TALK_ANSWER,
                sources=[],
                model="small-talk",
                prompt_version="small-talk-v1",
                confidence=0.9,
                llm_trace={"path": "small_talk"},
            )
        # Routing por compania RESUELTA del texto, no solo por el parametro
        # ticker: "precio de ASTS" sin campo ticker va igualmente por la
        # ruta estructurada con validacion financiera.
        company = self._resolve_company(db, question, scope, ticker)
        if company is not None and not ticker:
            ticker = company.ticker
        if company is None and not ticker and _FINANCIAL_INTENT_RE.search(question or ""):
            # Intencion financiera sin compania resuelta: abstencion honesta
            # en lugar de texto libre del LLM con cifras no sustentadas.
            return ChatResponse(
                answer=_FINANCIAL_ABSTAIN_ANSWER,
                sources=[],
                model="abstain",
                prompt_version="financial-abstain-v1",
                confidence=0.2,
                llm_trace={"path": "financial_abstain"},
            )
        baseline = self._deterministic_answer(db, question, scope, ticker)
        # Fast-path Jev (4): si la pregunta es una consulta factual simple
        # (baseline_ok, conf >= 0.8), el contexto determinista ya responde y
        # se ahorra la llamada LLM de sintesis. Sin key o ante fallo,
        # sintesis como siempre.
        if use_jev and ticker:
            try:
                from app.services.jev_gates import (
                    CHAT_BASELINE_OK_THRESHOLD,
                    CHAT_NEEDS_LLM_CRITERIA,
                    CHAT_NEEDS_LLM_INSTRUCTIONS,
                    jev_choice_or_none,
                )

                gate = await jev_choice_or_none(
                    name="chat_needs_llm",
                    text=question,
                    instructions=CHAT_NEEDS_LLM_INSTRUCTIONS,
                    criteria=CHAT_NEEDS_LLM_CRITERIA,
                )
                if (
                    gate is not None
                    and gate.label == "baseline_ok"
                    and gate.confidence >= CHAT_BASELINE_OK_THRESHOLD
                ):
                    baseline.model = "deterministic"
                    baseline.llm_trace = {
                        "fast_path": True,
                        "reason": "jev_baseline_ok",
                        "jev_gate": {
                            "label": gate.label,
                            "confidence": gate.confidence,
                        },
                    }
                    return baseline
            except Exception:  # noqa: BLE001 — Jev nunca rompe el chat
                pass
        synthesis = ChatSynthesisService(self.provider)
        if ticker:
            return await synthesis.synthesize(
                question=question,
                ticker=ticker,
                baseline=baseline,
                db=db,
                enable_debate=enable_debate,
            )
        return await synthesis.synthesize_general(
            question=question,
            baseline=baseline,
            db=db,
        )

    def _deterministic_answer(
        self, db: Session, question: str, scope: str, ticker: str | None
    ) -> ChatResponse:
        company = self._resolve_company(db, question, scope, ticker)
        written_memory = self.memory.maybe_write_from_chat(db, question, company, scope)
        retrieved_memory = self.memory.retrieve(db, question, company, scope=scope, limit=6)
        recent_sessions = self._recent_sessions(db, company)

        library_context = (
            retrieve_library_context(db, question)
            if os.getenv("CAVAAI_ENABLE_VECTOR_CHAT") == "1" else []
        )
        library_lines = [
            f"- Investment doctrine, not a company fact: {item['text']} "
            f"[knowledge_chunk:{item['id']}]" for item in library_context
        ]
        sources: list[dict] = list(library_context)
        proposed_actions: list[str] = []

        if company:
            thesis = self._latest_thesis(db, company)
            sections = self._sections(db, thesis)
            facts = self._key_facts(db, company)
            claims = self._claims(db, company)
            news = self._recent_news(db, company)
            db_chunks = self._document_chunks(db, company, question)
            rag_chunks = self._rag_chunks(db, question, company)
            evidence_suggestions = list(
                db.scalars(
                    select(EvidenceSuggestion)
                    .where(
                        EvidenceSuggestion.company_id == company.id,
                        EvidenceSuggestion.status == "pending",
                    )
                    .order_by(
                        desc(EvidenceSuggestion.confidence),
                        desc(EvidenceSuggestion.created_at),
                    )
                    .limit(6)
                ).all()
            )

            if thesis:
                sources.append(
                    self._source_entry(
                        "thesis_version",
                        thesis.id,
                        f"{company.ticker} thesis v{thesis.version}",
                        status=thesis.status,
                    )
                )
            for section in sections:
                sources.append(
                    self._source_entry(
                        "thesis_section",
                        section.id,
                        section.title,
                        section_key=section.section_key,
                        confidence=_decimal_to_float(section.confidence),
                    )
                )
            for fact in facts:
                sources.append(
                    self._source_entry(
                        "financial_fact",
                        fact.id,
                        f"{fact.metric} {fact.period}",
                        metric=fact.metric,
                        value=_decimal_to_float(fact.value),
                        unit=fact.unit,
                        source_type=fact.source_type,
                        source_tier=source_tier_key(fact.source_type),
                        confidence=_decimal_to_float(fact.confidence),
                    )
                )
            for claim in claims:
                sources.append(
                    self._source_entry(
                        "claim",
                        claim.id,
                        _short(claim.statement, 120),
                        status=claim.status,
                        materiality_score=claim.materiality_score,
                        confidence=_decimal_to_float(claim.confidence),
                    )
                )
                for evidence in claim.evidence[:2]:
                    sources.append(
                        self._source_entry(
                            "claim_evidence",
                            evidence.id,
                            _short(evidence.summary, 140),
                            claim_id=claim.id,
                            evidence_type=evidence.evidence_type,
                            document_id=evidence.document_id,
                            document_chunk_id=evidence.document_chunk_id,
                            source_tier=evidence.source_tier,
                            confidence=_decimal_to_float(evidence.confidence),
                        )
                    )
            for chunk, document in db_chunks:
                sources.append(
                    self._source_entry(
                        "document_chunk",
                        chunk.id,
                        document.title,
                        document_id=document.id,
                        source_type=document.source_type,
                        source_tier=source_tier_key(document.source_type),
                        text=_short(chunk.text, 240),
                    )
                )
            for chunk in rag_chunks:
                sources.append(
                    self._source_entry(
                        "rag_chunk",
                        chunk.get("point_id"),
                        chunk.get("title") or "Indexed document chunk",
                        document_id=chunk.get("document_id"),
                        knowledge_document_id=chunk.get("knowledge_document_id"),
                        collection_id=chunk.get("collection_id"),
                        page_number=chunk.get("page_number"),
                        chunk_index=chunk.get("chunk_index"),
                        entity_id=chunk.get("entity_id"),
                        source_type=chunk.get("source_type"),
                        source_tier=source_tier_key(chunk.get("source_type")),
                        score=chunk.get("score"),
                        text=_short(chunk.get("text", ""), 240),
                    )
                )
            latest_price = db.scalars(
                select(MarketPrice)
                .where(MarketPrice.company_id == company.id)
                .where(MarketPrice.date <= date.today())
                .order_by(desc(MarketPrice.date))
                .limit(1)
            ).first()
            if latest_price is not None:
                # adj_close NULL = spot sin ajustar por splits/dividendos
                # (p. ej. intraday): se distingue de cierre diario y se
                # declara el proveedor. Fechas futuras excluidas: una barra
                # de manana no es cotizacion actual.
                adjusted = latest_price.adj_close is not None
                value = latest_price.adj_close if adjusted else latest_price.close
                kind = "cierre" if adjusted else "spot"
                sources.append(
                    self._source_entry(
                        "market_price",
                        latest_price.id,
                        f"{company.ticker} {value} {company.currency} ({kind} {latest_price.date.isoformat()}, {latest_price.source})",
                        date=latest_price.date.isoformat(),
                        price=str(value),
                        currency=company.currency,
                        adjusted=adjusted,
                    )
                )
            for event in news:
                sources.append(
                    self._source_entry(
                        "news_event",
                        event.id,
                        event.title,
                        event_type=event.event_type,
                        materiality_score=event.materiality_score,
                        impact_direction=event.impact_direction,
                        requires_update=event.requires_update,
                    )
                )

            for retrieved in retrieved_memory:
                sources.append(
                    self._source_entry(
                        "memory_item",
                        retrieved.item.id,
                        _short(retrieved.item.content, 140),
                        memory_type=retrieved.item.memory_type,
                        importance=retrieved.item.importance,
                        score=retrieved.score,
                        reason=retrieved.reason,
                    )
                )
            if written_memory:
                sources.append(
                    self._source_entry(
                        "memory_writeback",
                        written_memory.id,
                        "New chat memory stored",
                        memory_type=written_memory.memory_type,
                    )
                )

            if not thesis:
                proposed_actions.append(f"Crear la primera tesis para {company.ticker}")
            if any(claim.status in {"unverified", "contradicted"} for claim in claims):
                proposed_actions.append("Revisar afirmaciones no verificadas o contradichas")
            if any(event.requires_update for event in news):
                proposed_actions.append("Revisar cambios de tesis por noticias materiales")
            if not facts:
                proposed_actions.append("Ingerir hechos financieros SEC/FMP antes de sacar conclusiones cuantitativas")

            facts_text = (
                "\n".join(
                    f"- {fact.metric}: {_decimal_to_float(fact.value)} {fact.unit} "
                    f"({fact.period}, {source_tier_key(fact.source_type)}) "
                    f"[financial_fact:{fact.id}]"
                    for fact in facts[:5]
                )
                or "- No hay hechos financieros fiables almacenados para esta empresa."
            )
            calculations_text = (
                "- No se ha hecho un calculo nuevo en esta respuesta; los hechos almacenados se citan como entradas."
                if facts
                else "- Calculo bloqueado: faltan hechos financieros almacenados."
            )
            assumptions_text = (
                "\n".join(
                    f"- {_short(item.item.content, 180)} "
                    f"[memory_item:{item.item.id}]"
                    for item in retrieved_memory[:3]
                )
                or "- No se recupero memoria relevante del usuario."
            )
            claim_lines = [
                f"- [{claim.status}] {_short(claim.statement, 180)} "
                f"[claim:{claim.id}]"
                for claim in claims[:5]
                if claim.status != "supported"
            ]
            unverified_text = "\n".join(claim_lines) or "- No hay afirmaciones sin resolver en el contexto recuperado."
            thesis_text = (
                f"Tesis {company.ticker} v{thesis.version}: `{thesis.status}` con rating `{thesis.rating}`. "
                f"Valor esperado={_decimal_to_float(thesis.expected_value)} frente a precio actual={_decimal_to_float(thesis.current_price)}. "
                f"[thesis_version:{thesis.id}]"
                if thesis
                else f"Aun no hay tesis almacenada para {company.ticker}."
            )
            rag_evidence_lines = [
                f"- {_short(chunk.get('text', ''), 180)} "
                f"({chunk.get('source_type') or 'indexed'}) "
                f"[rag_chunk:{chunk.get('point_id')}]"
                for chunk in rag_chunks[:3]
                if chunk.get("point_id") and chunk.get("text")
            ] + library_lines
            evidence_text = (
                "\n".join(
                    [
                        *[
                            f"- {_short(chunk.text, 180)} ({document.source_type}) "
                            f"[document_chunk:{chunk.id}]"
                            for chunk, document in db_chunks[:3]
                        ],
                        *rag_evidence_lines,
                    ]
                )
                or "- Ningun fragmento de documento local encajo con fuerza; sube o ingiere fuentes primarias."
            )
            news_text = (
                "\n".join(
                    f"- {event.title} [{event.impact_direction}, materiality {event.materiality_score}] "
                    f"[news_event:{event.id}]"
                    for event in news[:3]
                )
                or "- No hay noticias recientes almacenadas para esta empresa."
            )
            contradiction_claims = [
                claim
                for claim in claims
                if claim.status in {"contradicted", "superseded", "stale"}
            ]
            contradictions_text = (
                "\n".join(
                    f"- [{claim.status}] {_short(claim.statement, 180)} "
                    f"[claim:{claim.id}]"
                    for claim in contradiction_claims
                )
                or "- No se encontraron contradicciones en las afirmaciones recuperadas."
            )
            found_metrics = {fact.metric for fact in facts}
            missing_metrics = [
                metric for metric in KEY_FACT_METRICS if metric not in found_metrics
            ]
            insufficient_text = (
                f"- Faltan entradas almacenadas: {', '.join(missing_metrics)}."
                if missing_metrics
                else "- No falta ninguna entrada financiera clave en esta recuperacion."
            )
            conclusion_text = (
                "- Hay que revisar la tesis antes de cambiar supuestos."
                if contradiction_claims
                or any(event.requires_update for event in news)
                else "- La evidencia recuperada no exige un cambio automatico de tesis; seguir monitorizando."
            )

            answer = (
                f"HECHO\n{facts_text}\n\n"
                f"CALCULO\n{calculations_text}\n\n"
                f"HIPOTESIS / MEMORIA DEL USUARIO\n{assumptions_text}\n\n"
                f"AFIRMACION SIN VERIFICAR\n{unverified_text}\n\n"
                f"INFERENCIA\n{thesis_text} A partir de la evidencia recuperada, el siguiente paso mas seguro es revisar "
                f"las afirmaciones y las fuentes primarias antes de cambiar la tesis.\n\n"
                f"FOTO DE EVIDENCIA\n{evidence_text}\n\n"
                f"NOTICIAS / QUE CAMBIO\n{news_text}\n\n"
                f"CONTRADICCIONES\n{contradictions_text}\n\n"
                f"DATOS INSUFICIENTES\n{insufficient_text}\n\n"
                f"CONCLUSION\n{conclusion_text}"
            )

            sections = [
                {
                    "key": "facts",
                    "body": facts_text,
                    "citations": [
                        f"financial_fact:{fact.id}" for fact in facts[:5]
                    ],
                },
                {
                    "key": "calculations",
                    "body": calculations_text,
                    "citations": [
                        f"financial_fact:{fact.id}" for fact in facts[:5]
                    ],
                },
                {
                    "key": "user_hypotheses",
                    "body": assumptions_text,
                    "citations": [
                        f"memory_item:{item.item.id}"
                        for item in retrieved_memory[:3]
                    ],
                },
                {
                    "key": "unverified_claims",
                    "body": unverified_text,
                    "citations": [
                        f"claim:{claim.id}"
                        for claim in claims[:5]
                        if claim.status != "supported"
                    ],
                },
                {
                    "key": "inferences",
                    "body": "\n".join([thesis_text, *rag_evidence_lines])
                    if rag_evidence_lines
                    else thesis_text,
                    "citations": [
                        *([f"thesis_version:{thesis.id}"] if thesis else []),
                        *[f"knowledge_chunk:{item['id']}" for item in library_context],
                        *[
                            f"rag_chunk:{chunk.get('point_id')}"
                            for chunk in rag_chunks[:3]
                            if chunk.get("point_id") and chunk.get("text")
                        ],
                    ],
                },
                {
                    "key": "contradictions",
                    "body": contradictions_text,
                    "citations": [
                        f"claim:{claim.id}" for claim in contradiction_claims
                    ],
                },
                {
                    "key": "insufficient_data",
                    "body": insufficient_text,
                    "citations": [],
                },
                {
                    "key": "conclusion",
                    "body": conclusion_text,
                    "citations": [
                        *[
                            f"claim:{claim.id}"
                            for claim in contradiction_claims
                        ],
                        *[
                            f"news_event:{event.id}"
                            for event in news
                            if event.requires_update
                        ],
                    ],
                },
            ]

            return ChatResponse(
                answer=answer,
                sections=sections,
                sources=sources,
                blocked=not thesis or not sources,
                proposed_actions=list(dict.fromkeys(proposed_actions)),
                evidence_suggestions=[
                    {
                        "id": suggestion.id,
                        "statement": suggestion.statement,
                        "relation": suggestion.relation,
                        "suggestion_type": suggestion.suggestion_type,
                        "confidence": float(suggestion.confidence),
                        "suggested_claim_id": suggestion.suggested_claim_id,
                        "document_chunk_id": suggestion.document_chunk_id,
                    }
                    for suggestion in evidence_suggestions
                ],
                prompt_version="source-aware-synthesis-v1",
                model="deterministic",
            )

        portfolio_memories = [retrieved.item for retrieved in retrieved_memory]
        for item in portfolio_memories:
            sources.append(
                self._source_entry(
                    "memory_item",
                    item.id,
                    _short(item.content, 140),
                    memory_type=item.memory_type,
                    importance=item.importance,
                )
            )
        for session in recent_sessions:
            sources.append(
                self._source_entry(
                    "research_session",
                    session.id,
                    session.title,
                    status=session.status,
                    summary=_short(session.summary, 180),
                )
            )
        if written_memory:
            sources.append(self._source_entry("memory_writeback", written_memory.id, "New chat memory stored"))

        answer = (
            "CONTEXTO\n- Pregunta general sin ticker: el asistente dispone de memorias de cartera, sesiones de research y contexto documental.\n\n"
            "SIN CALCULOS\n- Sin ticker no hay calculos de cartera en esta respuesta.\n\n"
            "MEMORIAS\n"
            f"{chr(10).join(f'- {_short(item.content, 180)}' for item in portfolio_memories[:5]) or '- No relevant portfolio memory retrieved.'}\n\n"
            "SIN AFIRMACIONES DE EMPRESA\n- Pregunta por un ticker concreto para revisar afirmaciones y evidencia.\n\n"
            "CONTEXTO DOCUMENTAL\n"
            + ("\n".join(library_lines) or "- Para respuestas con fuentes de empresa, indica un ticker o ingiere evidencia primero.")
        )
        return ChatResponse(
            answer=answer,
            sections=[
                {
                    "key": "facts",
                    "body": "Portfolio memory and research-session context only.",
                    "citations": [
                        f"memory_item:{item.id}"
                        for item in portfolio_memories[:5]
                    ],
                },
                {
                    "key": "calculations",
                    "body": "No portfolio calculation was performed.",
                    "citations": [],
                },
                {
                    "key": "user_hypotheses",
                    "body": "Retrieved portfolio memories.",
                    "citations": [
                        f"memory_item:{item.id}"
                        for item in portfolio_memories[:5]
                    ],
                },
                {
                    "key": "unverified_claims",
                    "body": "Ask about a specific ticker to check company claims and evidence.",
                    "citations": [],
                },
                {
                    "key": "inferences",
                    "body": "\n".join(library_lines) or "A ticker is required for company-level inference.",
                    "citations": [f"knowledge_chunk:{item['id']}" for item in library_context],
                },
                {
                    "key": "contradictions",
                    "body": "No company claim set was selected.",
                    "citations": [],
                },
                {
                    "key": "insufficient_data",
                    "body": "Provide a ticker or ingest portfolio-level evidence.",
                    "citations": [],
                },
                {
                    "key": "conclusion",
                    "body": "No company-level conclusion is available.",
                    "citations": [],
                },
            ],
            sources=sources,
            blocked=False,
            proposed_actions=["Ask about a ticker", "Ingest portfolio-level documents"],
            prompt_version="source-aware-synthesis-v1",
            model="deterministic",
        )
