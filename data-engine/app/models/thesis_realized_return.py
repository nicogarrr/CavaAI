"""D3: el puente persistido entre la tesis y lo que pasó después.

Vive en su propio módulo (no en ``app/models/entities.py``) a propósito: la
tabla es nueva y ``entities.py`` es un fichero que editan muchos procesos en
paralelo. Importa ``Base``, ``TenantOwnedMixin`` y ``TimestampMixin`` del
modelo compartido, así que la tabla se registra en el mismo ``metadata`` y
``Base.metadata.create_all`` la crea igual que cualquier otra.

La fila es una foto *cerrada* de una tesis concreta contra el mercado: precio
de entrada, valoración tal como se veía ese día, el retorno realizado por
horizonte y el veredicto. Reutiliza las GuaranteeNamespaces del repo:
``MarketPrice.adj_close`` (NULL = spot sin serie ajustada, nunca se copia el
``close``), el motor de retornos ``propicks_price_service.momentum_from_series``
y el de drawdown ``tearsheet_service.compute_metrics``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

# Alias para las columnas llamadas `date`. Dentro del cuerpo de una clase,
# `date: Mapped[date]` hace que el anotado se refiera a la propia columna
# mientras se evalua (mismo motivo que en `app/models/entities.py`).
_DateT = date

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import TenantOwnedMixin, TimestampMixin


def utcnow() -> datetime:
    return datetime.now(UTC)


class ThesisRealizedReturn(TenantOwnedMixin, Base, TimestampMixin):
    """Retorno realizado de UNA versión de tesis, con su veredicto.

    Una fila por (tenant, thesis_version): el histórico de lo que el inversor
    dijo y lo que pasó no se sobrescribe, salvo que cambien los precios
    consumidos — y entonces se guarda la revisión anterior en ``revisions``.
    """

    __tablename__ = "thesis_realized_returns"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "thesis_version_id",
            name="uq_thesis_realized_return_tenant_version",
        ),
        Index(
            "ix_thesis_realized_returns_company_outcome",
            "company_id",
            "outcome",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    thesis_version_id: Mapped[int] = mapped_column(
        ForeignKey("thesis_versions.id", ondelete="CASCADE"), index=True
    )
    thesis_version: Mapped[int] = mapped_column(Integer, default=1)
    # Ancla point-in-time: el instante en que la versión existió. No se usa
    # `updated_at` porque es mutable (una regeneration lo mueve) y volvería
    # el recálculo no idempotente.
    thesis_published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    thesis_status: Mapped[str] = mapped_column(String(40), default="draft")

    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    entry_date: Mapped[_DateT | None] = mapped_column(Date, nullable=True)
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    entry_price_status: Mapped[str] = mapped_column(String(40), default="missing")
    entry_price_rule: Mapped[str] = mapped_column(Text, default="")

    fair_value_at_entry: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 6), nullable=True
    )
    fair_value_source: Mapped[str] = mapped_column(String(40), default="absent")
    upside_at_entry: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )

    holding_horizon_days: Mapped[int] = mapped_column(Integer, default=180)
    holding_horizon_source: Mapped[str] = mapped_column(String(40), default="default_6m")
    judgement_horizon: Mapped[str] = mapped_column(String(10), default="6M")
    judgement_status: Mapped[str] = mapped_column(String(20), default="pending")

    horizons: Mapped[list] = mapped_column(JSON, default=list)
    outcome: Mapped[str] = mapped_column(String(20), default="inconclusive")
    outcome_definition_version: Mapped[str] = mapped_column(String(20), default="v1")
    verdict_reason: Mapped[str] = mapped_column(Text, default="")
    # `too_early` e `inconclusive` NO entran en el denominador del hit-rate:
    # un acierto sobre una tesis de ayer no es un acierto.
    counts_toward_hit_rate: Mapped[bool] = mapped_column(Boolean, default=False)

    benchmark_ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    benchmark_status: Mapped[str] = mapped_column(String(40), default="missing")
    base_currency: Mapped[str] = mapped_column(String(10), default="EUR")

    decision_lesson_id: Mapped[int | None] = mapped_column(
        ForeignKey("decision_lessons.id", ondelete="SET NULL"), nullable=True, index=True
    )
    decision_lesson_link: Mapped[str] = mapped_column(String(60), default="none")

    revision: Mapped[int] = mapped_column(Integer, default=1)
    price_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    revisions: Mapped[list] = mapped_column(JSON, default=list)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
