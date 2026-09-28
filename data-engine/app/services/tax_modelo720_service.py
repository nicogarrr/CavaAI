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

from app.models import (
    CashBalance,
    CashDailySnapshot,
    Company,
    Position,
    PositionDailySnapshot,
)

THRESHOLD_720 = Decimal("50000")

# Máxima antigüedad del snapshot aceptable para afirmar el valor a 31/12.
SNAPSHOT_MAX_LAG_DAYS = 10


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
    """Chequeo de umbrales del Modelo 720 para un ejercicio.

    Tri-estado por categoría: ``exceeds`` es True/False solo con datos
    suficientes; cualquier laguna (snapshot antiguo, valoración ausente,
    custodia no verificada como extranjera, saldo medio Q4 desconocido)
    lo deja en None con ``status="desconocido"`` — una respuesta negativa
    construida sobre datos parciales sería un falso verde.
    """

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
        # Custodia: solo posiciones importadas de un bróker EXTRANJERO
        # (source ibkr_flex) cuentan como "valores depositados en el
        # extranjero". Sin rastro de custodia extranjera, no se afirma.
        position_sources = {
            (p.portfolio_id, p.company_id): (p.source or "")
            for p in db.scalars(select(Position))
        }

        valores_total = Decimal("0")
        valores_rows = []
        unvalued = []
        foreign_unverified = []
        short_positions = []
        missing_isin = []
        valores_max_date: date | None = None
        for position in positions:
            company = companies.get(position.company_id)
            ticker = company.ticker if company else f"company-{position.company_id}"
            if valores_max_date is None or position.snapshot_date > valores_max_date:
                valores_max_date = position.snapshot_date
            value_base = position.market_value_base
            if value_base is None:
                unvalued.append({
                    "ticker": ticker,
                    "snapshot_date": position.snapshot_date.isoformat(),
                    "reason": "Sin tipo de cambio a fecha del snapshot: fuera del total EUR, valorar a mano.",
                })
                continue
            amount = Decimal(str(value_base))
            if amount < 0:
                # Un corto es una deuda, no un bien o derecho declarable:
                # no suma al umbral (abs() inflaría el patrimonio).
                short_positions.append({
                    "ticker": ticker,
                    "snapshot_date": position.snapshot_date.isoformat(),
                    "value_base": _money(amount),
                    "reason": "Posición corta (valor negativo): no es un bien en el extranjero a efectos del 720.",
                })
                continue
            source = position_sources.get(
                (position.portfolio_id, position.company_id), ""
            )
            if not source.startswith("ibkr"):
                foreign_unverified.append({
                    "ticker": ticker,
                    "snapshot_date": position.snapshot_date.isoformat(),
                    "reason": "Custodia extranjera no verificada (la posición no procede de una importación de bróker extranjero): fuera del total, revisar a mano.",
                })
                continue
            valores_total += amount
            isin = company.isin if company else None
            if not isin:
                missing_isin.append(ticker)
            valores_rows.append({
                "ticker": ticker,
                "name": company.name if company else ticker,
                "isin": isin,
                "snapshot_date": position.snapshot_date.isoformat(),
                "quantity": _money(Decimal(str(position.quantity))),
                "value_base": _money(amount),
            })

        # --- Cuentas (categoría C) ---
        cash_rows = _latest_snapshots_before(
            db, CashDailySnapshot, CashDailySnapshot.currency, year_end
        )
        cash_sources = {c.currency: (c.source or "") for c in db.scalars(select(CashBalance))}
        cuentas_total = Decimal("0")
        cuentas_detail = []
        cuentas_max_date: date | None = None
        for cash in cash_rows:
            if cash.balance_native is None or cash.balance_native <= 0:
                continue
            if cuentas_max_date is None or cash.snapshot_date > cuentas_max_date:
                cuentas_max_date = cash.snapshot_date
            if cash.fx_rate is None:
                unvalued.append({
                    "ticker": f"cash-{cash.currency}",
                    "snapshot_date": cash.snapshot_date.isoformat(),
                    "reason": "Sin tipo de cambio para el saldo: fuera del total EUR, valorar a mano.",
                })
                continue
            if not cash_sources.get(cash.currency, "").startswith("ibkr"):
                foreign_unverified.append({
                    "ticker": f"cash-{cash.currency}",
                    "snapshot_date": cash.snapshot_date.isoformat(),
                    "reason": "Cuenta en el extranjero no verificada (sin importación de bróker extranjero para esta divisa): fuera del total, revisar a mano.",
                })
                continue
            amount = Decimal(str(cash.balance_native)) * Decimal(str(cash.fx_rate))
            cuentas_total += amount
            cuentas_detail.append({
                "currency": cash.currency,
                "snapshot_date": cash.snapshot_date.isoformat(),
                "value_base": _money(amount),
            })

        def _lag(max_date: date | None) -> int | None:
            return None if max_date is None else (year_end - max_date).days

        def _status(
            total: Decimal, max_date: date | None, *, q4_missing: bool = False
        ) -> tuple[bool | None, str, list[str]]:
            reasons = []
            if max_date is None:
                return None, "desconocido", [
                    "Sin snapshots de valoración a cierre del ejercicio: no se puede afirmar nada sobre esta categoría."
                ]
            lag = (year_end - max_date).days
            if lag > SNAPSHOT_MAX_LAG_DAYS:
                reasons.append(
                    f"El snapshot más reciente es de {max_date.isoformat()} "
                    f"({lag} días antes del cierre): demasiado antiguo para "
                    "afirmar el valor a 31/12; puede omitir adquisiciones "
                    "posteriores."
                )
                return None, "desconocido", reasons
            if total >= THRESHOLD_720:
                return True, "supera", reasons
            if q4_missing:
                reasons.append(
                    "El saldo a 31/12 no supera el umbral, pero falta el "
                    "saldo medio del 4.º trimestre (que también puede "
                    "superarlo): resultado no concluyente."
                )
                return None, "desconocido", reasons
            return False, "por_debajo", reasons

        valores_exceeds, valores_status, valores_reasons = _status(
            valores_total, valores_max_date
        )
        # Con partidas de VALORES fuera del total, un "por_debajo" sería
        # falso verde (las cuentas tienen su propia categoría).
        valores_huecos = any(
            not u["ticker"].startswith("cash-") for u in unvalued
        ) or any(
            not f["ticker"].startswith("cash-") for f in foreign_unverified
        )
        if valores_huecos:
            if valores_status == "por_debajo":
                valores_exceeds, valores_status = None, "desconocido"
            valores_reasons = valores_reasons + [
                "Hay valores sin valorar o sin custodia extranjera verificada fuera del total: el resultado no es concluyente."
            ]
        cuentas_huecas = any(
            u["ticker"].startswith("cash-") for u in unvalued
        ) or any(
            f["ticker"].startswith("cash-") for f in foreign_unverified
        )
        cuentas_exceeds, cuentas_status, cuentas_reasons = _status(
            cuentas_total, cuentas_max_date, q4_missing=True
        )
        if cuentas_huecas and cuentas_status == "por_debajo":
            cuentas_exceeds, cuentas_status = None, "desconocido"
            cuentas_reasons = cuentas_reasons + [
                "Hay saldos sin valorar o sin ubicación extranjera verificada fuera del total: el resultado no es concluyente."
            ]

        incomplete = bool(unvalued or foreign_unverified)
        return {
            "fiscal_year": fiscal_year,
            "threshold_base": _money(THRESHOLD_720),
            "categories": {
                "valores": {
                    "exceeds": valores_exceeds,
                    "status": valores_status,
                    "total_base": _money(valores_total),
                    "positions": sorted(valores_rows, key=lambda r: r["ticker"]),
                    "missing_isin": sorted(missing_isin),
                    "snapshot_lag_days": _lag(valores_max_date),
                    "reasons": valores_reasons,
                },
                "cuentas": {
                    "exceeds": cuentas_exceeds,
                    "status": cuentas_status,
                    "total_base": _money(cuentas_total),
                    "balances": sorted(cuentas_detail, key=lambda r: r["currency"]),
                    "average_q4_missing": True,
                    "snapshot_lag_days": _lag(cuentas_max_date),
                    "reasons": cuentas_reasons,
                },
                "inmuebles": {
                    "exceeds": None,
                    "status": "no_evaluable",
                    "total_base": None,
                    "note": "No computable con datos de bróker: los inmuebles en el extranjero se declaran aparte. No se afirma ni que superan ni que no superan el umbral.",
                },
            },
            "unvalued": unvalued,
            "foreign_unverified": foreign_unverified,
            "short_positions": short_positions,
            "incomplete": incomplete,
            "notas": [
                "El umbral de 50.000 € se evalúa POR CATEGORÍA (valores, "
                "cuentas e inmuebles por separado), no por el total de la cuenta.",
                "Tri-estado: 'supera' / 'por_debajo' solo con datos "
                "suficientes; 'desconocido' cuando falta valoración, "
                "cobertura de fechas, FX, saldo medio Q4 o verificación de "
                "custodia extranjera. Un 'desconocido' NO es un 'no'.",
                "Solo computan posiciones y saldos con custodia en bróker "
                "extranjero verificada por su importación (IBKR); el resto "
                "queda en 'foreign_unverified'.",
                "Cuentas: falta el saldo medio del 4.º trimestre, así que el "
                "umbral puede superarse aunque el saldo a 31/12 no lo supere "
                "(average_q4_missing).",
                "Chequeo orientativo: la obligación real depende también de "
                "titularidad, cotitulares y variaciones del año; contrastar "
                "con los extractos del bróker.",
            ],
        }
