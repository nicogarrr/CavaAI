"""Reindexa el indice vectorial Qdrant de un tenant desde Postgres/SQLite.

Usa ``RAGIndex().rebuild_tenant(db)``: borra los puntos del tenant en la
coleccion ``portfolio_research_documents`` y los regenera desde los chunks
persistidos (Document + KnowledgeDocument). Operacion idempotente y acotada
al tenant indicado.

Uso:
    python scripts/reindex_tenant_vectors.py --tenant-external-id <id>
    python scripts/reindex_tenant_vectors.py --tenant-id 1

Variables de entorno relevantes:
    DATABASE_URL  (por defecto la del settings)
    QDRANT_URL    (por defecto http://localhost:6333)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models import Tenant  # noqa: E402
from app.services.rag import RAGIndex  # noqa: E402


def _resolve_tenant(db, tenant_id: int | None, external_id: str | None) -> Tenant:
    if tenant_id is not None:
        tenant = db.get(Tenant, tenant_id)
    elif external_id is not None:
        tenant = db.scalar(
            select(Tenant).where(Tenant.external_id == external_id)
        )
    else:
        raise SystemExit("Indica --tenant-id o --tenant-external-id.")
    if tenant is None:
        raise SystemExit("Tenant no encontrado.")
    return tenant


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconstruye el indice Qdrant de un tenant (RAGIndex.rebuild_tenant)."
    )
    parser.add_argument("--tenant-id", type=int, default=None)
    parser.add_argument("--tenant-external-id", default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        tenant = _resolve_tenant(db, args.tenant_id, args.tenant_external_id)
        db.info["tenant_id"] = tenant.id
        status = RAGIndex().status()
        if not status.get("configured"):
            raise SystemExit(
                f"Qdrant no alcanzable: {status.get('error')}. "
                "Levanta Qdrant primero (docker compose up -d qdrant)."
            )
        result = RAGIndex().rebuild_tenant(db)
        print(json.dumps({"tenant_id": tenant.id, **result}, indent=2, default=str))
        if result.get("errors"):
            raise SystemExit(f"Reindexado con {len(result['errors'])} errores.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
