"""Ingesta masiva del universo US desde snapshots SEC locales.

Para cada ticker del manifest (ticker -> CIK): ensure company ->
refresh_from_sec (lee los snapshots locales; cero red a la SEC, que bloquea
IPs de datacenter) -> commit por empresa. Los fallos se saltan y se listan al
final; nunca se inventan datos. Idempotente: por defecto salta empresas que
ya tienen facts SEC (reanudación tras corte); --force recalcula todo.

Los nombres salen del snapshot como el propio ticker (entityName del mirror);
la pasada de enriquecimiento (scripts/enrich_company_names.py) pone nombre,
sector y exchange reales despues.

Uso (dentro del contenedor backend, con SEC_SNAPSHOT_DIR configurado):

    python scripts/ingest_universe.py --tenant-external-id <ext> \
        [--manifest data/sec_snapshots/manifest.json] [--limit N] \
        [--start-from TICKER] [--force] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import SessionLocal, init_db
from app.models import Company, FinancialFact, Tenant
from app.services.financial_ingestion_service import FinancialIngestionService


async def ingest(
    tenant_external_id: str,
    manifest_path: Path,
    limit: int | None,
    start_from: str | None,
    force: bool,
    dry_run: bool,
) -> dict:
    init_db()
    manifest = json.loads(manifest_path.read_text())
    tickers = sorted(manifest.get("tickers", {}))
    if start_from:
        start_from = start_from.upper()
        tickers = [t for t in tickers if t >= start_from]
    if limit is not None:
        tickers = tickers[:limit]

    db = SessionLocal()
    stats: dict = {
        "tickers_in_manifest": len(manifest.get("tickers", {})),
        "selected": len(tickers),
        "created": 0,
        "refreshed": 0,
        "skipped_existing": 0,
        "failed": [],
        "facts_imported_total": 0,
        "dry_run": dry_run,
    }
    try:
        tenant = db.scalar(
            select(Tenant).where(Tenant.external_id == tenant_external_id)
        )
        if tenant is None:
            raise SystemExit(
                f"Tenant no encontrado: {tenant_external_id}. "
                "Crea el tenant desde la app antes de la ingesta."
            )
        db.info["tenant_id"] = tenant.id
        service = FinancialIngestionService()
        started = time.monotonic()

        for index, ticker in enumerate(tickers, start=1):
            company = db.scalar(select(Company).where(Company.ticker == ticker))
            created = False
            if company is None:
                company = Company(
                    ticker=ticker,
                    name=ticker,
                    exchange="UNKNOWN",
                    currency="USD",
                    sector="Unknown",
                    industry="Unknown",
                    company_type="research_candidate",
                    valuation_model="unassigned",
                    special_sources=[],
                    special_risks=[],
                    factor_tags=[],
                )
                db.add(company)
                db.flush()
                created = True
                stats["created"] += 1

            if not force and not created:
                has_sec_facts = db.scalar(
                    select(FinancialFact.id)
                    .where(
                        FinancialFact.company_id == company.id,
                        FinancialFact.source_type == "SEC",
                    )
                    .limit(1)
                )
                if has_sec_facts is not None:
                    stats["skipped_existing"] += 1
                    continue

            if dry_run:
                stats["refreshed"] += 1
                db.rollback()
                continue

            try:
                result = await service.refresh_from_sec(db=db, company=company)
                db.commit()
                stats["refreshed"] += 1
                stats["facts_imported_total"] += result.get("facts_imported", 0)
            except Exception as exc:  # noqa: BLE001 - un emisor no frena al universo
                db.rollback()
                stats["failed"].append({"ticker": ticker, "error": str(exc)[:200]})

            if index % 50 == 0:
                elapsed = time.monotonic() - started
                print(
                    f"[{index}/{len(tickers)}] refreshed={stats['refreshed']} "
                    f"failed={len(stats['failed'])} elapsed={elapsed:.0f}s",
                    flush=True,
                )
    finally:
        db.close()

    stats["failed_count"] = len(stats["failed"])
    stats["elapsed_seconds"] = round(time.monotonic() - started, 1)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-external-id", required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "data/sec_snapshots/manifest.json",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start-from", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stats = asyncio.run(
        ingest(
            tenant_external_id=args.tenant_external_id,
            manifest_path=args.manifest,
            limit=args.limit,
            start_from=args.start_from,
            force=args.force,
            dry_run=args.dry_run,
        )
    )
    print("RESULTADO:", json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
