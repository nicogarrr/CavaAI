"""Candidatos de empresa propuestos por el LLM para un cuello de botella.

Todo lo que hay aqui es INFERENCIA: la etiqueta es parte del esquema (CHECK) y
no puede guardarse otra cosa.
"""
from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import TenantOwnedMixin, utcnow

INFERRED_LABEL = "INFERIDO"


class BottleneckDiscovery(TenantOwnedMixin, Base):
    __tablename__ = "bottleneck_discovery"
    __table_args__ = (
        UniqueConstraint("tenant_id", "theme", "ticker", "day", name="uq_bottleneck_discovery_day"),
        CheckConstraint(f"label = '{INFERRED_LABEL}'", name="ck_bottleneck_discovery_label"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    theme: Mapped[str] = mapped_column(String(80))
    ticker: Mapped[str] = mapped_column(String(20))
    reasoning: Mapped[str] = mapped_column(Text)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    label: Mapped[str] = mapped_column(String(16), default=INFERRED_LABEL)
    model: Mapped[str] = mapped_column(String(160))
    day: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    n_sources: Mapped[int] = mapped_column(Integer, default=0)
