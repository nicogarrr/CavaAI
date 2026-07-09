from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class ConnectorItem:
    """Provider-neutral item returned by every polling connector."""

    source: str
    title: str
    url: str | None = None
    summary: str = ""
    published_at: datetime | None = None
    ticker: str | None = None
    item_type: str = "news"
    external_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "ticker": self.ticker,
            "item_type": self.item_type,
            "external_id": self.external_id,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class ConnectorResult:
    """Shared polling result that preserves partial failures and diagnostics."""

    source: str
    items: list[ConnectorItem] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def connector(self) -> str:
        return self.source

    @property
    def status(self) -> str:
        if self.errors and self.items:
            return "partial"
        if self.errors:
            return "error"
        return "ok"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat(),
            "items": [item.as_dict() for item in self.items],
            "errors": list(self.errors),
            "metadata": self.metadata,
        }

    @classmethod
    def failed(
        cls,
        source: str,
        error: Exception | str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> ConnectorResult:
        return cls(source=source, errors=[str(error)], metadata=metadata or {})
