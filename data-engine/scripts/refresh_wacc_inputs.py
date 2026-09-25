"""Refresca los inputs de mercado de WACC para todo el universo.

Para cada empresa: risk_free_rate (FRED, con fallback CSV sin clave),
premiums de policy declarados, beta y market_cap (Yahoo Finance, fuente
declarada). Yahoo limita peticiones: hay pausa entre tickers y los
fallos se cuentan, nunca se inventan datos.

Uso:
    python scripts/refresh_wacc_inputs.py --tenant-external-id <ext> [--limit N] [--sleep 0.7]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Company, Tenant
from app.services.wacc_input_service import WaccInputService


async def _run(args) -> dict:
    db = SessionLocal()
    stats = {"refreshed": 0, "completos": 0, "con_missing": 0, "errores": 0, "missing_top": {}}
    try:
        tenant = db.scalar(select(Tenant).where(Tenant.external_id == args.tenant_external_id))
        if tenant is None:
            print(f"Tenant no encontrado: {args.tenant_external_id}")
            return stats
        db.info["tenant_id"] = tenant.id
        companies = list(db.scalars(select(Company).order_by(Company.ticker)).all())
        if args.limit:
            companies = companies[: args.limit]
        service = WaccInputService()
        for index, company in enumerate(companies, start=1):
            try:
                result = await service.refresh(db, company)
                stats["refreshed"] += 1
                if result["missing"]:
                    stats["con_missing"] += 1
                    for metric in result["missing"]:
                        stats["missing_top"][metric] = stats["missing_top"].get(metric, 0) + 1
                else:
                    stats["completos"] += 1
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                stats["errores"] += 1
                print(f"ERROR {company.ticker}: {str(exc)[:160]}")
            if index % 100 == 0:
                print(f"progreso: {index}/{len(companies)}")
            time.sleep(args.sleep)  # cortesia con Yahoo
    finally:
        db.close()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-external-id", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=0.7)
    args = parser.parse_args()
    stats = asyncio.run(_run(args))
    print("RESULTADO:", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
