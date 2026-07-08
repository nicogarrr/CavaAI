from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, Document, ThesisVersion
from app.schemas import ChatResponse


class ChatService:
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
            source = db.scalar(select(Document).where(Document.company_id == company.id).limit(1))
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
            return ChatResponse(
                answer=(
                    f"For {company.ticker}, latest thesis v{thesis.version} is `{thesis.status}` "
                    f"with rating `{thesis.rating}`. Expected value is {float(thesis.expected_value):.2f} "
                    f"vs current price {float(thesis.current_price):.2f}. "
                    "Use this as a grounded answer only within the stored thesis and source audit."
                ),
                sources=[
                    {
                        "type": "thesis",
                        "id": thesis.id,
                        "title": f"{company.ticker} thesis v{thesis.version}",
                    },
                    {
                        "type": source.source_type if source else "missing_source",
                        "id": source.id if source else None,
                        "title": source.title if source else "No source document yet",
                    },
                ],
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

