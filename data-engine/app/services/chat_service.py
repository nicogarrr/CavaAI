from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, FinancialFact, ThesisVersion
from app.schemas import ChatResponse


class ChatService:
    def _get_key_facts(self, db, company) -> list[dict]:
        facts = []
        for metric in ["revenue", "free_cash_flow", "net_income", "net_debt", "shares_diluted"]:
            fact = db.scalar(
                select(FinancialFact)
                .where(FinancialFact.company_id == company.id, FinancialFact.metric == metric)
                .order_by(FinancialFact.fiscal_year.desc().nullslast(), desc(FinancialFact.created_at))
                .limit(1)
            )
            if fact:
                facts.append({"metric": metric, "value": float(fact.value), "unit": fact.unit, "period": fact.period, "source": fact.source_type})
        return facts

    def answer(self, db: Session, question: str, scope: str, ticker: str | None) -> ChatResponse:
        company = None
        if ticker:
            company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
        elif scope != "portfolio":
            upper = question.upper()
            for candidate in db.scalars(select(Company)).all():
                if candidate.ticker in upper:
                    company = candidate
                    break

        if company:
            thesis = db.scalar(
                select(ThesisVersion)
                .where(ThesisVersion.company_id == company.id)
                .order_by(desc(ThesisVersion.version))
                .limit(1)
            )
            if not thesis:
                return ChatResponse(
                    answer=(
                        f"No thesis exists yet for {company.ticker}. Generate a thesis first so "
                        "the chat can answer from stored evidence instead of memory."
                    ),
                    sources=[],
                    blocked=True,
                    proposed_actions=[f"Generate thesis for {company.ticker}"],
                )

            key_facts = self._get_key_facts(db, company)

            rag_chunks = []
            try:
                from app.services.rag import RAGIndex
                rag_chunks = RAGIndex().search(question, ticker=company.ticker if company else None, limit=4)
            except Exception:
                pass

            facts_text = "; ".join(f"{f['metric']}={f['value']:.0f}{f['unit']} ({f['period']})" for f in key_facts)
            rag_text = rag_chunks[0]["text"][:300] if rag_chunks else "no documents indexed"
            answer = (
                f"For {company.ticker}, thesis v{thesis.version} is `{thesis.status}` rating=`{thesis.rating}`. "
                f"Expected value {float(thesis.expected_value):.2f} vs price {float(thesis.current_price):.2f}. "
                f"Key facts: {facts_text}. "
                f"Evidence: {rag_text}"
            )

            sources = [{"type": "thesis", "id": thesis.id, "title": f"{company.ticker} thesis v{thesis.version}"}]
            for chunk in rag_chunks[:3]:
                sources.append({"type": "rag_chunk", "id": chunk.get("point_id"), "title": chunk.get("title", ""), "text": chunk.get("text", "")[:200]})

            return ChatResponse(
                answer=answer,
                sources=sources,
                blocked=thesis.status == "draft_failed_audit",
                proposed_actions=["Run source audit", "Update thesis"] if thesis.status != "final" else [],
            )

        return ChatResponse(
            answer=(
                "Portfolio scope is available. Ask about a ticker, risk concentration, "
                "cash, catalysts or valuation assumptions. I will block answers that need missing sources."
            ),
            sources=[],
            blocked=False,
            proposed_actions=["Open risk dashboard", "Generate missing thesis versions"],
        )
