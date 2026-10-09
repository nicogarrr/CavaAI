"""Proyecciones anuales de tesis a 5 ejercicios (PR A: calculo determinista).

Cada fila es UN ejercicio proyectado de UN escenario de UNA empresa. Los
valores son siempre INFERIDO (proyeccion propia del modelo) o N/D (input
critico ausente): la etiqueta es parte del esquema via CHECK, igual que en
bottleneck_discovery. Los Numeric son NULL cuando falta el input: nunca un 0
fabricado ni un valor por defecto silencioso.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import TenantOwnedMixin, utcnow

LABEL_INFERIDO = "INFERIDO"
LABEL_ND = "N/D"


class ThesisProjectionYear(TenantOwnedMixin, Base):
    __tablename__ = "thesis_projection_years"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "scenario",
            "fiscal_year",
            "day",
            name="uq_thesis_projection_year_day",
        ),
        CheckConstraint(
            f"label IN ('{LABEL_INFERIDO}', '{LABEL_ND}')",
            name="ck_thesis_projection_year_label",
        ),
        Index(
            "ix_thesis_projection_years_company",
            "company_id",
            "scenario",
            "fiscal_year",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    valuation_model_id: Mapped[int] = mapped_column(
        ForeignKey("valuation_models.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    scenario: Mapped[str] = mapped_column(String(10))
    fiscal_year: Mapped[int] = mapped_column(Integer)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    fcf: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    eps: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    label: Mapped[str] = mapped_column(String(16), default=LABEL_INFERIDO)
    source: Mapped[str] = mapped_column(String(500), default="")
    as_of: Mapped[date] = mapped_column(Date)
    day: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
