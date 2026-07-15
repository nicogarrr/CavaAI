import os
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.llm.base import LLMProvider
from app.llm.factory import create_llm_provider
from app.models import (
    Claim,
    Company,
    Document,
    DocumentChunk,
    EvidenceSuggestion,
    FinancialFact,
    MemoryItem,
    NewsEvent,
    ResearchSession,
    ThesisSection,
    ThesisVersion,
)
from app.schemas import ChatResponse
from app.services.memory_service import MemoryService
from app.services.chat_synthesis_service import ChatSynthesisService
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


def _source_tier(source_type: str | None) -> str:
    return source_tier_key(source_type)


def _short(text: str, limit: int = 420) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


class ChatService:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.memory = MemoryService()
        self.provider = provider or create_llm_provider()

    def _resolve_company(self, db: Session, question: str, scope: str, ticker: str | None) -> Company | None:
        if ticker:
            return db.scalar(select(Company).where(Company.ticker == ticker.upper()))
        if scope == "portfolio":
            return None
        upper = question.upper()
        for candidate in db.scalars(select(Company)).all():
            if candidate.ticker in upper:
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
        facts: list[FinancialFact] = []
        for metric in KEY_FACT_METRICS:
            fact = db.scalar(
                select(FinancialFact)
                .where(FinancialFact.company_id == company.id, FinancialFact.metric == metric)
                .order_by(
                    FinancialFact.fiscal_year.desc().nullslast(),
                    desc(FinancialFact.created_at),
                )
                .limit(1)
            )
            if fact:
                facts.append(fact)
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
        return list(
            db.scalars(
                select(Claim)
                .options(selectinload(Claim.evidence))
                .where(Claim.company_id == company.id)
                .order_by(desc(Claim.materiality_score), desc(Claim.updated_at))
                .limit(limit)
            ).all()
        )

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

            return RAGIndex().search(
                question,
                ticker=company.ticker if company else None,
                limit=limit,
                tenant_id=db.info.get("tenant_id"),
            )
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
        self, db: Session, question: str, scope: str, ticker: str | None
    ) -> ChatResponse:
        baseline = self._deterministic_answer(db, question, scope, ticker)
        return await ChatSynthesisService(self.provider).synthesize(
            question=question,
            ticker=ticker,
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

        sources: list[dict] = []
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
                        source_tier=_source_tier(fact.source_type),
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
                        source_tier=_source_tier(document.source_type),
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
                        source_type=chunk.get("source_type"),
                        source_tier=_source_tier(chunk.get("source_type")),
                        score=chunk.get("score"),
                        text=_short(chunk.get("text", ""), 240),
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
                proposed_actions.append(f"Create first thesis for {company.ticker}")
            if any(claim.status in {"unverified", "contradicted"} for claim in claims):
                proposed_actions.append("Review unverified or contradicted claims")
            if any(event.requires_update for event in news):
                proposed_actions.append("Review material news-driven thesis changes")
            if not facts:
                proposed_actions.append("Ingest SEC/FMP financial facts before quantitative conclusions")

            facts_text = (
                "\n".join(
                    f"- {fact.metric}: {_decimal_to_float(fact.value)} {fact.unit} "
                    f"({fact.period}, {_source_tier(fact.source_type)}) "
                    f"[financial_fact:{fact.id}]"
                    for fact in facts[:5]
                )
                or "- No reliable stored financial facts found for this company."
            )
            calculations_text = (
                "- No new calculation was performed in this answer; stored facts are cited as inputs."
                if facts
                else "- Calculation blocked: missing stored financial facts."
            )
            assumptions_text = (
                "\n".join(
                    f"- {_short(item.item.content, 180)} "
                    f"[memory_item:{item.item.id}]"
                    for item in retrieved_memory[:3]
                )
                or "- No relevant user memory retrieved."
            )
            claim_lines = [
                f"- [{claim.status}] {_short(claim.statement, 180)} "
                f"[claim:{claim.id}]"
                for claim in claims[:5]
                if claim.status != "supported"
            ]
            unverified_text = "\n".join(claim_lines) or "- No unresolved claim surfaced in the retrieved context."
            thesis_text = (
                f"{company.ticker} thesis v{thesis.version} is `{thesis.status}` with rating `{thesis.rating}`. "
                f"Expected value={_decimal_to_float(thesis.expected_value)} vs current price={_decimal_to_float(thesis.current_price)}. "
                f"[thesis_version:{thesis.id}]"
                if thesis
                else f"No stored thesis exists yet for {company.ticker}."
            )
            evidence_text = (
                "\n".join(
                    f"- {_short(chunk.text, 180)} ({document.source_type}) "
                    f"[document_chunk:{chunk.id}]"
                    for chunk, document in db_chunks[:3]
                )
                or "- No local document chunk matched strongly enough; upload/ingest primary sources."
            )
            news_text = (
                "\n".join(
                    f"- {event.title} [{event.impact_direction}, materiality {event.materiality_score}] "
                    f"[news_event:{event.id}]"
                    for event in news[:3]
                )
                or "- No recent stored news for this company."
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
                or "- No contradiction was found in the retrieved claim set."
            )
            found_metrics = {fact.metric for fact in facts}
            missing_metrics = [
                metric for metric in KEY_FACT_METRICS if metric not in found_metrics
            ]
            insufficient_text = (
                f"- Missing stored inputs: {', '.join(missing_metrics)}."
                if missing_metrics
                else "- No key financial input is missing from this retrieval."
            )
            conclusion_text = (
                "- Thesis review is required before changing assumptions."
                if contradiction_claims
                or any(event.requires_update for event in news)
                else "- Retrieved evidence does not require an automatic thesis change; continue monitoring."
            )

            answer = (
                f"FACT\n{facts_text}\n\n"
                f"CALCULATION\n{calculations_text}\n\n"
                f"USER ASSUMPTION / MEMORY\n{assumptions_text}\n\n"
                f"UNVERIFIED CLAIM\n{unverified_text}\n\n"
                f"INFERENCE\n{thesis_text} Based on the retrieved evidence, the safest next step is to review "
                f"claims and primary sources before changing the thesis.\n\n"
                f"EVIDENCE SNAPSHOT\n{evidence_text}\n\n"
                f"NEWS / WHAT CHANGED\n{news_text}\n\n"
                f"CONTRADICTIONS\n{contradictions_text}\n\n"
                f"INSUFFICIENT DATA\n{insufficient_text}\n\n"
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
                    "key": "inferences",
                    "body": thesis_text,
                    "citations": (
                        [f"thesis_version:{thesis.id}"] if thesis else []
                    ),
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
            "FACT\n- Portfolio chat currently has access to stored portfolio memories and research sessions.\n\n"
            "CALCULATION\n- No portfolio calculation was performed in this answer.\n\n"
            "USER ASSUMPTION / MEMORY\n"
            f"{chr(10).join(f'- {_short(item.content, 180)}' for item in portfolio_memories[:5]) or '- No relevant portfolio memory retrieved.'}\n\n"
            "UNVERIFIED CLAIM\n- Ask about a specific ticker to check company claims and evidence.\n\n"
            "INFERENCE\n- For source-aware answers, provide a ticker or ingest portfolio-level evidence first."
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
                    "key": "inferences",
                    "body": "A ticker is required for company-level inference.",
                    "citations": [],
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
