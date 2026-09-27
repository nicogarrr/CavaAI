"""Tenant-validated evidence for read-only chat and guided review.

Never call the legacy /chat service: it may write memory on trigger phrases.
Never use user text or model output as an instruction to retrieve other tenants.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, Document, DocumentChunk, FinancialFact, NewsEvent, ResearchReview


def _url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value.strip())
        return value.strip() if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username else None
    except ValueError:
        return None


def _company(db: Session, ticker: str) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if not company:
        raise LookupError("Ticker no encontrado")
    return company


def _tenant(db: Session) -> int:
    tenant_id = db.info.get("tenant_id")
    if tenant_id is None:
        raise LookupError("Espacio de trabajo no disponible")
    return tenant_id


def _review(db: Session, review_id: int | None, company_id: int, tenant_id: int) -> ResearchReview | None:
    if review_id is None:
        return None
    review = db.scalar(select(ResearchReview).where(
        ResearchReview.id == review_id, ResearchReview.company_id == company_id,
        ResearchReview.tenant_id == tenant_id,
    ))
    if review is None:
        raise LookupError("Ticket no encontrado para este ticker")
    return review


def guide_context(db: Session, ticker: str) -> dict:
    tenant_id = _tenant(db)
    company = _company(db, ticker)
    reviews = db.scalars(select(ResearchReview).where(
        ResearchReview.tenant_id == tenant_id, ResearchReview.company_id == company.id,
        ResearchReview.status == "open",
    ).order_by(desc(ResearchReview.created_at)).limit(10)).all()
    news = db.scalars(select(NewsEvent).where(
        NewsEvent.tenant_id == tenant_id, NewsEvent.company_id == company.id,
    ).order_by(desc(NewsEvent.date)).limit(10)).all()
    return {
        "ticker": company.ticker, "review_id": reviews[0].id if reviews else None,
        "open_reviews": [{"id": row.id, "status": row.status, "summary": row.summary} for row in reviews],
        "latest_news": [{"id": row.id, "title": row.title, "source": row.source,
                         "source_url": _url(row.url), "date": row.date,
                         "date_source": (row.metadata_ or {}).get("date_source", "unknown")}
                        for row in news],
        "missing_data": [] if news else ["No hay noticias registradas para este ticker."],
    }


def _evidence(db: Session, company: Company, tenant_id: int, question: str) -> list[dict]:
    citations = []
    facts = db.scalars(select(FinancialFact).where(
        FinancialFact.tenant_id == tenant_id, FinancialFact.company_id == company.id,
        FinancialFact.source_id.is_not(None), FinancialFact.is_reported.is_(True),
    ).order_by(desc(FinancialFact.created_at)).limit(12)).all()
    document_ids = {fact.source_id for fact in facts}
    documents = db.scalars(select(Document).where(
        Document.tenant_id == tenant_id, Document.company_id == company.id,
        Document.id.in_(document_ids),
    )).all() if document_ids else []
    by_doc = {doc.id: doc for doc in documents}
    for row in facts:
        document = by_doc.get(row.source_id)
        if document is None or not _url(document.source_url):
            continue
        citations.append({"id": f"financial_fact:{row.id}", "kind": "financial_fact",
                          "source": document.title, "url": _url(document.source_url),
                          "as_of": f"{row.fiscal_year or 'año no indicado'} {row.period}",
                          "excerpt": f"{row.metric}: {row.value} {row.unit}"})
    news = db.scalars(select(NewsEvent).where(
        NewsEvent.tenant_id == tenant_id, NewsEvent.company_id == company.id,
    ).order_by(desc(NewsEvent.date)).limit(12)).all()
    for row in news:
        provenance = row.metadata_ or {}
        date_source = provenance.get("date_source")
        if provenance.get("connector") == "gdelt" and date_source == "source":
            date_source = "gdelt_first_seen"  # legacy GDELT `seendate`
        if not _url(row.url) or date_source not in {"source", "gdelt_first_seen"}:
            continue
        label = "primera detección GDELT" if date_source == "gdelt_first_seen" else "fecha de la fuente"
        citations.append({"id": f"news_event:{row.id}", "kind": "news_event",
                          "source": row.source, "url": _url(row.url),
                          "as_of": f"{row.date.isoformat()} ({label})", "excerpt": row.title})
    terms = {term.lower().strip(".,;?!") for term in question.split() if len(term) > 4}
    chunks = db.execute(select(DocumentChunk, Document).join(Document, DocumentChunk.document_id == Document.id).where(
        DocumentChunk.tenant_id == tenant_id, Document.tenant_id == tenant_id,
        Document.company_id == company.id,
    ).order_by(desc(Document.published_at)).limit(100)).all()
    ranked = sorted(((sum(term in chunk.text.lower() for term in terms), chunk, doc) for chunk, doc in chunks),
                    key=lambda result: result[0], reverse=True)
    for score, chunk, doc in ranked[:4]:
        if score < 1 or not _url(doc.source_url):
            continue
        citations.append({"id": f"document_chunk:{chunk.id}", "kind": "document_chunk",
                          "source": doc.title, "url": _url(doc.source_url),
                          "as_of": doc.published_at.isoformat() if doc.published_at else None,
                          "excerpt": chunk.text[:450]})
    return citations


def answer(db: Session, payload) -> dict:
    tenant_id = _tenant(db)
    if not payload.ticker:
        return _empty(payload.mode, "Indica un ticker para recuperar fuentes verificables del espacio de trabajo.")
    company = _company(db, payload.ticker)
    review = _review(db, payload.review_id, company.id, tenant_id)
    citations = _evidence(db, company, tenant_id, payload.question)
    if not citations:
        response = _empty(payload.mode, f"Sin datos citables para {company.ticker}.")
        response["review_id"] = review.id if review else None
        return response
    # The deterministic baseline quotes only retrieved, tenant-validated rows.
    # It is not an LLM conclusion and does not elevate a headline to a fact.
    selected = citations[:6]
    lines = []
    for citation in selected:
        statement = (f"Dato documentado: {citation['excerpt']}" if citation["kind"] == "financial_fact"
                     else f"Documento: {citation['excerpt']}" if citation["kind"] == "document_chunk"
                     else f"Noticia atribuida a {citation['source']}: {citation['excerpt']}")
        lines.append(f"{statement} [{citation['id']}]")
    note = "Estos son indicios y registros, no una comprobación independiente del titular."
    if payload.mode == "guide":
        note += " Contrasta el documento primario antes de aceptar una conclusión del ticket."
    return {"mode": payload.mode, "status": "answered", "answer": "\n".join([*lines, note]),
            "sections": [{"key": "facts", "body": "\n".join(lines),
                          "citation_ids": [c["id"] for c in selected]},
                         {"key": "insufficient_data", "body": note, "citation_ids": []}],
            "citations": selected, "missing_data": [],
            "suggested_next_steps": ["Abrir las fuentes y contrastar los hechos antes de concluir."],
            "review_id": review.id if review else None, "writeback": False}


def _empty(mode: str, reason: str) -> dict:
    return {"mode": mode, "status": "insufficient_data", "answer": reason,
            "sections": [{"key": "insufficient_data", "body": reason, "citation_ids": []}],
            "citations": [], "missing_data": [reason],
            "suggested_next_steps": ["Aporta o conecta una fuente con fecha y URL para este ticker."],
            "review_id": None, "writeback": False}
