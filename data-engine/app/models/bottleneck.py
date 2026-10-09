"""Tenant-local, reproducible supply-constraint aggregates."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import TenantOwnedMixin


class BottleneckSignal(TenantOwnedMixin, Base):
    __tablename__ = "bottleneck_signal"
    __table_args__ = (UniqueConstraint("tenant_id", "theme", name="uq_bottleneck_tenant_theme"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    theme: Mapped[str] = mapped_column(String(80))
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    n_sources: Mapped[int] = mapped_column(Integer, default=0)
