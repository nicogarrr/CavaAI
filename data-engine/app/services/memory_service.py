import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, MemoryItem

TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{3,}")


@dataclass(frozen=True)
class RetrievedMemory:
    item: MemoryItem
    score: float
    reason: str


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in TOKEN_RE.finditer(text)}


class MemoryService:
    """Lightweight external memory layer inspired by Mem0's retrieve/consolidate/write flow."""

    def retrieve(
        self,
        db: Session,
        query: str,
        company: Company | None = None,
        scope: str = "portfolio",
        limit: int = 6,
    ) -> list[RetrievedMemory]:
        query_tokens = _tokens(query)
        statement = select(MemoryItem).where(MemoryItem.status == "active")
        if company:
            statement = statement.where(
                (MemoryItem.company_id == company.id) | (MemoryItem.scope == "portfolio")
            )
        else:
            statement = statement.where(MemoryItem.scope == scope)

        items = db.scalars(statement.order_by(desc(MemoryItem.updated_at)).limit(200)).all()
        ranked: list[RetrievedMemory] = []
        now = datetime.now(UTC)
        for item in items:
            content_tokens = _tokens(item.content)
            overlap = len(query_tokens & content_tokens)
            updated_at = item.updated_at
            if updated_at and updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=UTC)
            age_days = max((now - updated_at).days if updated_at else 0, 0)
            recency = max(0.0, 1.0 - min(age_days, 365) / 365)
            company_boost = 2.0 if company and item.company_id == company.id else 0.5
            score = overlap * 2.5 + item.importance * 0.8 + recency + company_boost
            if overlap or item.importance >= 8 or (company and item.company_id == company.id):
                ranked.append(
                    RetrievedMemory(
                        item=item,
                        score=round(score, 3),
                        reason=f"overlap={overlap}; importance={item.importance}; recency={recency:.2f}",
                    )
                )

        return sorted(ranked, key=lambda memory: memory.score, reverse=True)[:limit]
