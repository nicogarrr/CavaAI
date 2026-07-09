import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, MemoryItem


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{3,}")
MEMORY_TRIGGERS = (
    "remember",
    "recuerda",
    "memoriza",
    "guarda",
    "watch",
    "vigila",
    "hipotesis",
    "hypothesis",
    "thesis",
    "tesis",
)


@dataclass(frozen=True)
class RetrievedMemory:
    item: MemoryItem
    score: float
    reason: str


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in TOKEN_RE.finditer(text)}


def _normalized(text: str) -> str:
    return " ".join(text.strip().lower().split())


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

    def maybe_write_from_chat(
        self,
        db: Session,
        question: str,
        company: Company | None = None,
        scope: str = "portfolio",
    ) -> MemoryItem | None:
        lowered = question.lower()
        if not any(trigger in lowered for trigger in MEMORY_TRIGGERS):
            return None

        content = question.strip()
        if len(content) < 12:
            return None

        normalized = _normalized(content)
        statement = select(MemoryItem).where(
            MemoryItem.status == "active",
            MemoryItem.scope == ("company" if company else scope),
        )
        if company:
            statement = statement.where(MemoryItem.company_id == company.id)

        for item in db.scalars(statement.limit(100)).all():
            if _normalized(item.content) == normalized:
                item.importance = max(item.importance, 7)
                item.updated_at = datetime.now(UTC)
                db.commit()
                return item

        item = MemoryItem(
            company_id=company.id if company else None,
            scope="company" if company else scope,
            memory_type="chat_memory",
            importance=7,
            content=content,
            source_type="chat",
            metadata_={"write_policy": "triggered_by_user_instruction"},
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item
