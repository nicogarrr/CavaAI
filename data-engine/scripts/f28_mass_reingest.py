"""F28: re-ingesta masiva SEC tras el rebuild de snapshots con `start`.

La re-ingesta por empresa (FinancialIngestionService.refresh_from_sec)
REEMPLAZA todos los facts SEC reportados de la empresa aplicando el filtro
de duracion (anual = 300-380 dias; hechos instantaneos pasan), y recalcula
los derivados. Lo que NO reemplaza son las filas calculadas viejas
(is_reported=False), contaminadas por los segmentos-segun-FY originales:
este script las borra antes de re-ingestar para que se recalculen limpias.

Solo toca facts SEC; las filas de otras fuentes (FMP, ESEF) se respetan.

Uso (contenedor backend):
    PYTHONPATH=/app python3 /app/scripts/f28_mass_reingest.py --tenant 2 --limit 3   # prueba
    PYTHONPATH=/app python3 /app/scripts/f28_mass_reingest.py                        # todo
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import delete, select

from app.models.entities import Company, FinancialFact
from app.services.financial_ingestion_service import FinancialIngestionService
from app.workers.dramatiq_app import _session, tenant_contexts


def _companies_with_sec_facts(db, tenant_id: int, limit: int | None) -> list[Company]:
    company_ids = (
        select(FinancialFact.company_id)
        .where(FinancialFact.source_type == "SEC")
        .distinct()
        .scalar_subquery()
    )
    query = select(Company).where(Company.id.in_(company_ids)).order_by(Company.ticker)
    if limit:
        query = query.limit(limit)
    return list(db.scalars(query).all())


def run_tenant(tenant_id: int, user_id: str, limit: int | None) -> dict:
    db = _session(tenant_id, user_id)
    service = FinancialIngestionService()
    totals = {"companies": 0, "purged_calc": 0, "facts_imported": 0, "errors": 0}
    try:
        companies = _companies_with_sec_facts(db, tenant_id, limit)
        for index, company in enumerate(companies, 1):
            try:
                purged = db.execute(
                    delete(FinancialFact).where(
                        FinancialFact.company_id == company.id,
                        FinancialFact.tenant_id == tenant_id,
                        FinancialFact.is_reported.is_(False),
                    )
                ).rowcount
                result = asyncio.run(
                    service.refresh_from_sec(db=db, company=company)
                )
                db.commit()
                totals["companies"] += 1
                totals["purged_calc"] += purged
                totals["facts_imported"] += result.get("facts_imported", 0)
            except Exception as exc:  # una empresa rota no frena el lote
                db.rollback()
                totals["errors"] += 1
                print(f"ERROR {company.ticker}: {type(exc).__name__} {exc}"[:200], flush=True)
            if index % 100 == 0 or index == len(companies):
                print(
                    f"tenant {tenant_id}: {index}/{len(companies)} "
                    f"purged_calc={totals['purged_calc']} "
                    f"facts={totals['facts_imported']} errors={totals['errors']}",
                    flush=True,
                )
    finally:
        db.close()
    return totals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", type=int, default=None, help="Solo un tenant.")
    parser.add_argument("--limit", type=int, default=None, help="Limitar empresas por tenant (pruebas).")
    args = parser.parse_args()

    contexts = tenant_contexts()
    if args.tenant is not None:
        contexts = [(t, u) for t, u in contexts if t == args.tenant]
        if not contexts:
            print(f"tenant {args.tenant} no existe o no esta activo")
            return 1
    grand = {"companies": 0, "purged_calc": 0, "facts_imported": 0, "errors": 0}
    for tenant_id, user_id in contexts:
        totals = run_tenant(tenant_id, user_id, args.limit)
        print(f"tenant {tenant_id} RESUMEN: {totals}", flush=True)
        for key in grand:
            grand[key] += totals[key]
    print(f"TOTAL: {grand}", flush=True)
    return 0 if grand["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
