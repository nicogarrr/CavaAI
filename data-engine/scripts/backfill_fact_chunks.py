"""Backfill de chunks RAG desde financial_facts para todo el universo.

Los Document de fundamentales (SEC/ESEF) no tenian chunks: el RAG solo
indexaba la biblioteca de conocimiento. Este backfill genera los chunks
desde los hechos persistidos (sync_company_fact_chunks, idempotente).
Despues, RAGIndex().ingest_document por documento o rebuild_tenant los
indexa en Qdrant.

Uso (dentro del contenedor backend):
    python scripts/backfill_fact_chunks.py --tenant-external-id <ext>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models import Company, Tenant  # noqa: E402
from app.services.fact_chunk_service import sync_company_fact_chunks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-external-id", required=True)
    args = parser.parse_args()

    db = SessionLocal()
    stats = {"companies": 0, "sources": 0, "chunks": 0}
    try:
        tenant = db.scalar(select(Tenant).where(Tenant.external_id == args.tenant_external_id))
        if tenant is None:
            print(f"Tenant no encontrado: {args.tenant_external_id}")
            return 1
        db.info["tenant_id"] = tenant.id
        companies = list(db.scalars(select(Company).order_by(Company.ticker)).all())
        for index, company in enumerate(companies, 1):
            result = sync_company_fact_chunks(db, company)
            stats["companies"] += 1
            stats["sources"] += result["sources"]
            stats["chunks"] += result["chunks"]
            if index % 200 == 0:
                db.commit()
                print(f"progreso {index}/{len(companies)} {stats}", flush=True)
        db.commit()
    finally:
        db.close()
    print(f"RESULTADO_BACKFILL_CHUNKS: {stats}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
