"""Proyección mes a mes de dividendos de la cartera, con retenciones.

INFERIDO: réplica mecánica de los dividendos declarados en los últimos 12
meses (misma cantidad por acción, fechas desplazadas +1 año). No modela
crecimientos ni recortes: es la foto de "si repiten lo ya declarado",
etiquetada como inferencia, nunca como compromiso de la empresa.

Retenciones estimadas (etiquetadas, con fuente y fecha de verificación):

- Origen: tabla corta verificada. US 15 % (convenio España-EE.UU., W-8BEN;
  AEAT, Anexo III de límites de imposición en convenios, verificado
  2026-10-11), ES 19 % (retención a cuenta, primer tramo del ahorro) y
  GB 0 % (sin retención interna sobre dividendos ordinarios). Cualquier
  otro domicilio sale como ``None`` ("sin datos"), nunca como 0 %.
- IRPF: escala del ahorro progresiva anual de
  :mod:`app.services.tax_irpf_filing` (Orden HAC/277/2026, Renta 2025).
- Doble imposición: lo retenido en origen es deducible en España hasta la
  cuota española de esa renta; se simplifica como
  ``neto = max(0, irpf - origen)``.

Honestidad de cobertura: posiciones sin dividendos declarados ingeridos
aparecen en ``coverage.sin_datos`` (nunca como 0,00 €), y las cantidades en
moneda sin tipo de cambio se excluyen de los agregados en divisa base y se
listan en ``coverage.fx_missing``.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Company, DividendRecord, Position
from app.services.portfolio_fx_service import PortfolioFXService
from app.services.tax_irpf_filing import calculate_savings_tax

# Retención en origen por país de domicilio (ISO). Verificada 2026-10-11:
# - US: 15 % convenio España-EE.UU. con W-8BEN (AEAT, Anexo III convenios).
# - ES: 19 % retención a cuenta (escala del ahorro, primer tramo).
# - GB: 0 % (Reino Unido no retiene dividendos ordinarios en origen).
# Ausente = tipo no verificado -> None ("sin datos"), jamás 0 inventado.
_SOURCE_WITHHOLDING: dict[str, Decimal] = {
    "US": Decimal("0.15"),
    "ES": Decimal("0.19"),
    "GB": Decimal("0.00"),
}

_METHOD_NOTE = (
    "INFERIDO: réplica mecánica de los dividendos declarados en los últimos 12 "
    "meses desplazados +1 año (sin crecimiento ni recortes). Retención de origen "
    "según convenio (AEAT, verificado 2026-10-11); IRPF con la escala del ahorro "
    "vigente (Orden HAC/277/2026); deducción por doble imposición simplificada "
    "(neto = máx(0, IRPF - origen))."
)


def _shift_year(d: date, years: int = 1) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 de febrero -> 28 en años no bisiestos
        return d.replace(month=2, day=28, year=d.year + years)


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


class DividendProjectionService:
    def project(self, db: Session, months: int = 12) -> dict[str, Any]:
        today = date.today()
        cutoff = date(today.year - 1, today.month, today.day)
        window: list[str] = []
        y, m = today.year, today.month
        for _ in range(months):
            window.append(f"{y:04d}-{m:02d}")
            m += 1
            if m > 12:
                m, y = 1, y + 1
        window_set = set(window)

        fx = PortfolioFXService()
        base_currency = fx.base_currency(db)

        rows = list(
            db.execute(
                select(Position, Company).join(Company, Position.company_id == Company.id)
            ).all()
        )

        per_position: list[dict[str, Any]] = []
        sin_datos: list[str] = []
        fx_missing: list[str] = []
        unknown_country: list[str] = []
        # month -> {"gross_base": Decimal, "source_base": Decimal, "positions": set}
        month_totals: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"gross_base": Decimal("0"), "source_base": Decimal("0")}
        )
        # (year, position_id) -> projected gross_base rows for IRPF progresivo
        yearly_gross: dict[int, list[tuple[str, Decimal]]] = defaultdict(list)

        for position, company in rows:
            records = [
                r
                for r in db.scalars(
                    select(DividendRecord).where(
                        DividendRecord.company_id == company.id,
                        DividendRecord.ex_date >= cutoff,
                    )
                ).all()
                if r.currency == position.currency
            ]
            if not records:
                sin_datos.append(company.ticker)
                continue

            quantity = Decimal(str(position.quantity))
            rate = fx.rate(
                db,
                quote_currency=position.currency,
                base_currency=base_currency,
                as_of=today,
            )
            if rate is None:
                fx_missing.append(company.ticker)

            country = (company.domicile_country or "").upper() or None
            source_rate = _SOURCE_WITHHOLDING.get(country) if country else None
            if country and country not in _SOURCE_WITHHOLDING:
                unknown_country.append(company.ticker)

            month_entries: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
            for record in records:
                projected = _shift_year(record.pay_date or record.ex_date)
                key = _month_key(projected)
                if key in window_set:
                    month_entries[key] += record.amount * quantity

            gross_native_year = sum(month_entries.values(), Decimal("0"))
            gross_base_year: Decimal | None = None
            source_base_year: Decimal | None = None
            if rate is not None:
                gross_base_year = gross_native_year * rate
                if source_rate is not None:
                    source_base_year = gross_base_year * source_rate
                for key, amount_native in month_entries.items():
                    gross_base = amount_native * rate
                    month_totals[key]["gross_base"] += gross_base
                    if source_rate is not None:
                        month_totals[key]["source_base"] += gross_base * source_rate
                    yearly_gross[int(key[:4])].append((key, gross_base))

            per_position.append(
                {
                    "ticker": company.ticker,
                    "currency": position.currency,
                    "quantity": float(quantity),
                    "frequency_last_year": len(records),
                    "gross_year_native": float(gross_native_year),
                    "gross_year_base": (
                        float(gross_base_year) if gross_base_year is not None else None
                    ),
                    "source_withholding_rate": (
                        float(source_rate) if source_rate is not None else None
                    ),
                    "source_withheld_year_base": (
                        float(source_base_year) if source_base_year is not None else None
                    ),
                    "months": {
                        key: float(amount) for key, amount in sorted(month_entries.items())
                    },
                }
            )

        # IRPF progresivo por año natural: el tramo se aplica al acumulado.
        irpf_by_month: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for year, entries in yearly_gross.items():
            monthly: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
            for key, gross_base in entries:
                monthly[key] += gross_base
            cumulative = Decimal("0")
            for key in sorted(monthly):
                prev_tax = calculate_savings_tax(cumulative, year)
                cumulative += monthly[key]
                irpf_by_month[key] += calculate_savings_tax(cumulative, year) - prev_tax

        months_out = []
        for key in window:
            gross = month_totals[key]["gross_base"]
            source = month_totals[key]["source_base"]
            irpf = irpf_by_month.get(key, Decimal("0"))
            net = gross - source - max(Decimal("0"), irpf - source)
            months_out.append(
                {
                    "month": key,
                    "gross_base": float(gross),
                    "source_withheld_base": float(source),
                    "irpf_base": float(irpf),
                    "net_base": float(net),
                }
            )

        return {
            "as_of": today.isoformat(),
            "base_currency": base_currency,
            "horizon_months": months,
            "label": "INFERIDO",
            "method": _METHOD_NOTE,
            "months": months_out,
            "positions": per_position,
            "coverage": {
                "with_data": len(per_position),
                "sin_datos": sorted(sin_datos),
                "fx_missing": sorted(set(fx_missing)),
                "unknown_source_withholding": sorted(set(unknown_country)),
            },
        }
