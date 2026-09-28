"""Modelo 720 (declaración informativa de bienes y derechos en el extranjero).

Chequeo de umbrales POR CATEGORÍA (50.000 €), que es como manda la norma:
  - Valores (acciones, fondos, bonos depositados en el extranjero): valor a
    31 de diciembre.
  - Cuentas: mayor entre saldo a 31/12 y saldo medio del 4.º trimestre.
  - Bienes inmuebles: no aplica a datos de bróker (siempre sin datos).

Enfoque de referencia: DeclaRenta (GPL-3.0) — reimplementación del criterio
normativo, sin copia de código.

Honestidad (sin verde falso), dictamen del auditor incorporado:
- Las posiciones se reconstruyen desde los snapshots diarios del PORTFOLIO
  ACTIVO (``PositionDailySnapshot``) más recientes a 31/12. La antigüedad se
  evalúa PARTIDA A PARTIDA: un snapshot reciente nunca certifica a otro
  antiguo; cada partida con snapshot viejo queda fuera del total y la
  categoría pasa a "desconocido".
- El umbral es en EUR: si la divisa base del portfolio no es EUR no se
  evalúa (sin tipo de cambio oficial a 31/12 no hay conversión fiable) y
  todas las categorías quedan "desconocido".
- La custodia extranjera NO se infiere del origen de importación (IBKR):
  importar de un bróker no acredita dónde está depositado cada valor. Solo
  computa cuando el tenant declara el país de depósito/gestión en
  ``tax_declarant.custody_country`` (dato fiscal personal del tenant); sin
  él, las partidas van a ``foreign_unverified`` y la categoría es
  "desconocido".
- Una posición sin valoración en base queda fuera del total, listada en
  ``unvalued``. Un corto es una deuda, no un bien: no suma (``short_positions``).
- El saldo medio del 4.º trimestre no está disponible: las cuentas se
  evalúan solo por saldo a 31/12 y se marca ``average_q4_missing``.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CashDailySnapshot,
    Company,
    PositionDailySnapshot,
    Tenant,
)
from app.services.portfolio_fx_service import PortfolioFXService

THRESHOLD_720 = Decimal("50000")

# Máxima antigüedad del snapshot aceptable para afirmar el valor a 31/12,
# evaluada PARTIDA A PARTIDA (una posición al 31/12 no certifica a otra de junio).
SNAPSHOT_MAX_LAG_DAYS = 10


def _money(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _latest_snapshots_before(
    db: Session, model, partition_col, year_end: date, portfolio_id
) -> list:
    """Último snapshot por partición (empresa/divisa) DENTRO del portfolio.

    Sin el filtro por portfolio, en multiportfolio el snapshot más reciente
    de un portfolio eclipsa las filas de otro y se mezclan carteras.
    """
    latest_dates = (
        select(partition_col, func.max(model.snapshot_date).label("max_date"))
        .where(model.snapshot_date <= year_end)
        .where(model.portfolio_id == portfolio_id)
        .group_by(partition_col)
        .subquery()
    )
    return list(
        db.scalars(
            select(model)
            .where(model.portfolio_id == portfolio_id)
            .join(
                latest_dates,
                (partition_col == latest_dates.c[0])
                & (model.snapshot_date == latest_dates.c.max_date),
            )
        )
    )


def _declared_custody_country(db: Session, tenant_id) -> str | None:
    """País de depósito/gestión declarado por el tenant (ISO2) o None."""
    if tenant_id is None:
        return None
    tenant = db.get(Tenant, tenant_id)
    declarant = (tenant.metadata_ or {}).get("tax_declarant") if tenant else None
    if not isinstance(declarant, dict):
        return None
    country = str(declarant.get("custody_country") or "").strip().upper()
    return country if len(country) == 2 and country.isalpha() else None


class Modelo720Service:
    """Chequeo de umbrales del Modelo 720 para un ejercicio.

    Tri-estado por categoría: ``exceeds`` es True/False solo con datos
    suficientes; cualquier laguna (partida con snapshot antiguo, valoración
    ausente, custodia extranjera no declarada, base no EUR, saldo medio Q4
    desconocido) lo deja en None con ``status="desconocido"`` — una
    respuesta construida sobre datos parciales sería un falso verde.
    """

    def check_thresholds(self, db: Session, fiscal_year: int) -> dict:
        year_end = date(fiscal_year, 12, 31)
        portfolio = PortfolioFXService().portfolio(db)

        base: dict = {
            "fiscal_year": fiscal_year,
            "threshold_base": _money(THRESHOLD_720),
            "base_currency": None,
            "custody_country": None,
            "unvalued": [],
            "foreign_unverified": [],
            "short_positions": [],
            "stale_snapshots": [],
            "incomplete": False,
        }

        def _unknown_category(reason: str, **extra) -> dict:
            return {
                "exceeds": None,
                "status": "desconocido",
                "total_base": None,
                "snapshot_lag_days": None,
                "reasons": [reason],
                **extra,
            }

        if portfolio is None:
            base["categories"] = {
                "valores": _unknown_category(
                    "Sin portfolio activo: no hay snapshots que evaluar.",
                    positions=[], missing_isin=[],
                    custody="no_verificada",
                ),
                "cuentas": _unknown_category(
                    "Sin portfolio activo: no hay snapshots que evaluar.",
                    balances=[], average_q4_missing=True,
                    custody="no_verificada",
                ),
                "inmuebles": _inmuebles(),
            }
            base["notas"] = _notas()
            return base

        base["base_currency"] = portfolio.base_currency
        if (portfolio.base_currency or "").upper() != "EUR":
            base["categories"] = {
                "valores": _unknown_category(
                    f"La divisa base del portfolio es {portfolio.base_currency}, "
                    "no EUR: sin tipo de cambio oficial a 31/12 no hay "
                    "conversión fiable y el umbral de 50.000 € no se evalúa.",
                    positions=[], missing_isin=[],
                    custody="no_verificada",
                ),
                "cuentas": _unknown_category(
                    f"La divisa base del portfolio es {portfolio.base_currency}, "
                    "no EUR: sin tipo de cambio oficial a 31/12 no hay "
                    "conversión fiable y el umbral de 50.000 € no se evalúa.",
                    balances=[], average_q4_missing=True,
                    custody="no_verificada",
                ),
                "inmuebles": _inmuebles(),
            }
            base["incomplete"] = True
            base["notas"] = _notas()
            return base

        custody_country = _declared_custody_country(db, portfolio.tenant_id)
        base["custody_country"] = custody_country
        custody_state = "declarada" if custody_country else "no_verificada"

        unvalued: list[dict] = []
        foreign_unverified: list[dict] = []
        short_positions: list[dict] = []
        stale_snapshots: list[dict] = []

        def _stale(ticker: str, snap_date: date) -> bool:
            lag = (year_end - snap_date).days
            if lag > SNAPSHOT_MAX_LAG_DAYS:
                stale_snapshots.append({
                    "ticker": ticker,
                    "snapshot_date": snap_date.isoformat(),
                    "lag_days": lag,
                    "reason": (
                        f"Snapshot de {snap_date.isoformat()} ({lag} días antes "
                        "del cierre): demasiado antiguo para afirmar el valor a "
                        "31/12 de ESTA partida; fuera del total."
                    ),
                })
                return True
            return False

        # --- Valores (categoría V) ---
        positions = _latest_snapshots_before(
            db, PositionDailySnapshot, PositionDailySnapshot.company_id,
            year_end, portfolio.id,
        )
        company_ids = [p.company_id for p in positions]
        companies = {
            c.id: c
            for c in db.scalars(select(Company).where(Company.id.in_(company_ids)))
        } if company_ids else {}

        valores_total = Decimal("0")
        valores_rows = []
        missing_isin = []
        valores_max_date: date | None = None
        for position in positions:
            company = companies.get(position.company_id)
            ticker = company.ticker if company else f"company-{position.company_id}"
            if valores_max_date is None or position.snapshot_date > valores_max_date:
                valores_max_date = position.snapshot_date
            if _stale(ticker, position.snapshot_date):
                continue
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
            if custody_country is None:
                foreign_unverified.append({
                    "ticker": ticker,
                    "snapshot_date": position.snapshot_date.isoformat(),
                    "reason": (
                        "Custodia extranjera no verificada: importar del bróker "
                        "no acredita dónde está depositado el valor. Declara el "
                        "país de depósito/gestión en tax_declarant.custody_country "
                        "(metadata del tenant); mientras tanto, fuera del total."
                    ),
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
            db, CashDailySnapshot, CashDailySnapshot.currency,
            year_end, portfolio.id,
        )
        cuentas_total = Decimal("0")
        cuentas_detail = []
        cuentas_max_date: date | None = None
        for cash in cash_rows:
            ticker = f"cash-{cash.currency}"
            if cash.balance_native is None or cash.balance_native <= 0:
                continue
            if cuentas_max_date is None or cash.snapshot_date > cuentas_max_date:
                cuentas_max_date = cash.snapshot_date
            if _stale(ticker, cash.snapshot_date):
                continue
            if cash.fx_rate is None:
                unvalued.append({
                    "ticker": ticker,
                    "snapshot_date": cash.snapshot_date.isoformat(),
                    "reason": "Sin tipo de cambio para el saldo: fuera del total EUR, valorar a mano.",
                })
                continue
            if custody_country is None:
                foreign_unverified.append({
                    "ticker": ticker,
                    "snapshot_date": cash.snapshot_date.isoformat(),
                    "reason": (
                        "Ubicación de la cuenta no verificada (la divisa no es el "
                        "país). Declara tax_declarant.custody_country en la "
                        "metadata del tenant; mientras tanto, fuera del total."
                    ),
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
            total: Decimal,
            max_date: date | None,
            *,
            stale: list[dict],
            huecos: bool,
            q4_missing: bool = False,
        ) -> tuple[bool | None, str, list[str]]:
            reasons: list[str] = []
            if stale:
                tickers = ", ".join(sorted({s["ticker"] for s in stale}))
                reasons.append(
                    f"Partidas con snapshot demasiado antiguo ({tickers}): cada "
                    "valor afirma su 31/12 con SU snapshot; uno reciente no "
                    "certifica a otro viejo. Resultado no concluyente."
                )
                return None, "desconocido", reasons
            if max_date is None and total == 0:
                return None, "desconocido", [
                    "Sin snapshots de valoración a cierre del ejercicio: no se puede afirmar nada sobre esta categoría."
                ]
            if total >= THRESHOLD_720:
                if huecos:
                    reasons.append(
                        "El total computado supera el umbral, pero hay partidas fuera del cómputo: revisarlas igualmente."
                    )
                return True, "supera", reasons
            if huecos:
                reasons.append(
                    "Hay partidas fuera del total (sin valorar, custodia no verificada o snapshot antiguo): un 'por_debajo' sería falso verde."
                )
                return None, "desconocido", reasons
            if q4_missing:
                reasons.append(
                    "El saldo a 31/12 no supera el umbral, pero falta el "
                    "saldo medio del 4.º trimestre (que también puede "
                    "superarlo): resultado no concluyente."
                )
                return None, "desconocido", reasons
            return False, "por_debajo", reasons

        def _is_cash(t: str) -> bool:
            return t.startswith("cash-")

        stale_v = [s for s in stale_snapshots if not _is_cash(s["ticker"])]
        stale_c = [s for s in stale_snapshots if _is_cash(s["ticker"])]
        huecos_v = stale_v or any(
            not _is_cash(u["ticker"]) for u in unvalued
        ) or any(not _is_cash(f["ticker"]) for f in foreign_unverified)
        huecos_c = stale_c or any(
            _is_cash(u["ticker"]) for u in unvalued
        ) or any(_is_cash(f["ticker"]) for f in foreign_unverified)

        valores_exceeds, valores_status, valores_reasons = _status(
            valores_total, valores_max_date, stale=stale_v, huecos=bool(huecos_v)
        )
        cuentas_exceeds, cuentas_status, cuentas_reasons = _status(
            cuentas_total, cuentas_max_date,
            stale=stale_c, huecos=bool(huecos_c), q4_missing=True,
        )

        incomplete = bool(unvalued or foreign_unverified or stale_snapshots)
        base.update({
            "categories": {
                "valores": {
                    "exceeds": valores_exceeds,
                    "status": valores_status,
                    "total_base": _money(valores_total),
                    "positions": sorted(valores_rows, key=lambda r: r["ticker"]),
                    "missing_isin": sorted(missing_isin),
                    "custody": custody_state,
                    "custody_country": custody_country,
                    "snapshot_lag_days": _lag(valores_max_date),
                    "reasons": valores_reasons,
                },
                "cuentas": {
                    "exceeds": cuentas_exceeds,
                    "status": cuentas_status,
                    "total_base": _money(cuentas_total),
                    "balances": sorted(cuentas_detail, key=lambda r: r["currency"]),
                    "average_q4_missing": True,
                    "custody": custody_state,
                    "custody_country": custody_country,
                    "snapshot_lag_days": _lag(cuentas_max_date),
                    "reasons": cuentas_reasons,
                },
                "inmuebles": _inmuebles(),
            },
            "unvalued": unvalued,
            "foreign_unverified": foreign_unverified,
            "short_positions": short_positions,
            "stale_snapshots": stale_snapshots,
            "incomplete": incomplete,
            "notas": _notas(),
        })
        return base


def _inmuebles() -> dict:
    return {
        "exceeds": None,
        "status": "no_evaluable",
        "total_base": None,
        "note": "No computable con datos de bróker: los inmuebles en el extranjero se declaran aparte. No se afirma ni que superan ni que no superan el umbral.",
    }


def _notas() -> list[str]:
    return [
        "El umbral de 50.000 € se evalúa POR CATEGORÍA (valores, cuentas e "
        "inmuebles por separado), no por el total de la cuenta.",
        "Tri-estado: 'supera' / 'por_debajo' solo con datos suficientes; "
        "'desconocido' cuando falta valoración, cobertura de fechas, base "
        "EUR, saldo medio Q4 o custodia declarada. Un 'desconocido' NO es un 'no'.",
        "Cada partida afirma su valor a 31/12 con SU snapshot: uno reciente "
        "no certifica a otro antiguo (partidas antiguas en 'stale_snapshots').",
        "La custodia extranjera no se infiere de la importación: computa "
        "solo cuando el tenant declara el país de depósito/gestión en "
        "tax_declarant.custody_country.",
        "El umbral se evalúa en EUR: con divisa base distinta de EUR la "
        "categoría queda 'desconocido' (sin conversión oficial a 31/12).",
        "Cuentas: falta el saldo medio del 4.º trimestre, así que el "
        "umbral puede superarse aunque el saldo a 31/12 no lo supere "
        "(average_q4_missing).",
        "Chequeo orientativo: la obligación real depende también de "
        "titularidad, cotitulares y variaciones del año; contrastar "
        "con los extractos del bróker.",
    ]
