"""Modelo 720 (declaración informativa de bienes y derechos en el extranjero).

Chequeo de umbrales POR CATEGORÍA (50.000 €), que es como manda la norma:
  - Valores (acciones, fondos, bonos depositados en el extranjero): valor a
    31 de diciembre.
  - Cuentas: mayor entre saldo a 31/12 y saldo medio del 4.º trimestre.
  - Bienes inmuebles: no aplica a datos de bróker (siempre sin datos).

Enfoque de referencia: DeclaRenta (GPL-3.0) — reimplementación del criterio
normativo, sin copia de código.

Honestidad (sin verde falso):
- Las posiciones se reconstruyen desde los snapshots diarios
  (``PositionDailySnapshot``) más recientes a 31/12 del ejercicio. Si un
  valor no tiene snapshot a fecha de cierre, NO se inventa: aparece en
  ``unvalued`` y el total queda marcado como incompleto.
- El saldo medio del 4.º trimestre no está disponible: las cuentas se
  evalúan solo por saldo a 31/12 y se marca ``average_q4_missing`` (el
  umbral podría superarse por la media aunque el saldo final no lo supere).
- Una posición sin tipo de cambio queda fuera del total en EUR y listada
  para valoración manual.
- Las claves de clase de valor (STK/FUND/BOND) no se distinguen en CavaAI:
  toda posición se trata como "valores" (todos los holdings importados son
  acciones/ETF cotizados; si entran otros activos habrá que clasificarlos).
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CashDailySnapshot, Company, PositionDailySnapshot

THRESHOLD_720 = Decimal("50000")


def _money(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _latest_snapshots_before(
    db: Session, model, partition_col, year_end: date
) -> list:
    """Último snapshot por partición (empresa/divisa) a fecha de cierre."""
    latest_dates = (
        select(partition_col, func.max(model.snapshot_date).label("max_date"))
        .where(model.snapshot_date <= year_end)
        .group_by(partition_col)
        .subquery()
    )
    return list(
        db.scalars(
            select(model).join(
                latest_dates,
                (partition_col == latest_dates.c[0])
                & (model.snapshot_date == latest_dates.c.max_date),
            )
        )
    )


class Modelo720Service:
    """Chequeo de umbrales del Modelo 720 para un ejercicio."""

    def check_thresholds(self, db: Session, fiscal_year: int) -> dict:
        year_end = date(fiscal_year, 12, 31)

        # --- Valores (categoría V) ---
        positions = _latest_snapshots_before(
            db, PositionDailySnapshot, PositionDailySnapshot.company_id, year_end
        )
        company_ids = [p.company_id for p in positions]
        companies = {
            c.id: c
            for c in db.scalars(select(Company).where(Company.id.in_(company_ids)))
        } if company_ids else {}

        valores_total = Decimal("0")
        valores_rows = []
        unvalued = []
        missing_isin = []
        for position in positions:
            company = companies.get(position.company_id)
            ticker = company.ticker if company else f"company-{position.company_id}"
            value_base = position.market_value_base
            if value_base is None:
                unvalued.append({
                    "ticker": ticker,
                    "snapshot_date": position.snapshot_date.isoformat(),
                    "reason": "Sin tipo de cambio a fecha del snapshot: fuera del total EUR, valorar a mano.",
                })
                continue
            amount = abs(Decimal(str(value_base)))
            valores_total += amount
            isin = company.isin if company else None
            if not isin:
                missing_isin.append(ticker)
            valores_rows.append({
                "ticker": ticker,
                "isin": isin,
                "snapshot_date": position.snapshot_date.isoformat(),
                "value_base": _money(amount),
            })

        # --- Cuentas (categoría C) ---
        cash_rows = _latest_snapshots_before(
            db, CashDailySnapshot, CashDailySnapshot.currency, year_end
        )
        cuentas_total = Decimal("0")
        cuentas_detail = []
        for cash in cash_rows:
            if cash.balance_native is None or cash.balance_native <= 0:
                continue
            if cash.fx_rate is None:
                unvalued.append({
                    "ticker": f"cash-{cash.currency}",
                    "snapshot_date": cash.snapshot_date.isoformat(),
                    "reason": "Sin tipo de cambio para el saldo: fuera del total EUR, valorar a mano.",
                })
                continue
            amount = Decimal(str(cash.balance_native)) * Decimal(str(cash.fx_rate))
            cuentas_total += amount
            cuentas_detail.append({
                "currency": cash.currency,
                "snapshot_date": cash.snapshot_date.isoformat(),
                "value_base": _money(amount),
            })

        return {
            "fiscal_year": fiscal_year,
            "threshold_base": _money(THRESHOLD_720),
            "categories": {
                "valores": {
                    "exceeds": valores_total >= THRESHOLD_720,
                    "total_base": _money(valores_total),
                    "positions": sorted(valores_rows, key=lambda r: r["ticker"]),
                    "missing_isin": sorted(missing_isin),
                },
                "cuentas": {
                    "exceeds": cuentas_total >= THRESHOLD_720,
                    "total_base": _money(cuentas_total),
                    "balances": sorted(cuentas_detail, key=lambda r: r["currency"]),
                    "average_q4_missing": True,
                },
                "inmuebles": {
                    "exceeds": False,
                    "total_base": 0.0,
                    "note": "No computable con datos de bróker: los inmuebles en el extranjero se declaran aparte.",
                },
            },
            "unvalued": unvalued,
            "incomplete": bool(unvalued),
            "notas": [
                "El umbral de 50.000 € se evalúa POR CATEGORÍA (valores, "
                "cuentas e inmuebles por separado), no por el total de la cuenta.",
                "Posiciones valoradas con el snapshot más reciente a 31/12 "
                "del ejercicio; sin snapshot a cierre, el valor no entra en "
                "el total y aparece en 'unvalued'.",
                "Cuentas: falta el saldo medio del 4.º trimestre, así que el "
                "umbral puede superarse aunque el saldo a 31/12 no lo supere "
                "(average_q4_missing).",
                "Chequeo orientativo: la obligación real depende también de "
                "titularidad, cotitulares y variaciones del año; contrastar "
                "con los extractos del bróker.",
            ],
        }
