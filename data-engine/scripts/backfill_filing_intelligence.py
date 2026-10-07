"""Analyze existing SEC/CNMV documents, keyset-paged and tenant-scoped. No fetches."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Document, Tenant
from app.services.filing_intelligence import analyze_document, official_document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-external-id", required=True)
    parser.add_argument("--page-size", type=int, default=100, choices=range(1, 501))
    args = parser.parse_args()
    counts = {}
    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.external_id == args.tenant_external_id))
        if tenant is None:
            print("Tenant no encontrado")
            return 1
        db.info["tenant_id"] = tenant.id
        cursor = 0
        while True:
            documents = db.scalars(select(Document).where(
                Document.tenant_id == tenant.id, Document.id > cursor,
                Document.source_type.in_(["SEC", "sec", "CNMV", "cnmv", "primary_official", "esef"]),
            ).order_by(Document.id).limit(args.page_size)).all()
            if not documents:
                break
            for document in documents:
                cursor = document.id
                if not official_document(document):
                    continue
                try:
                    status = analyze_document(db, document)["status"]
                    db.commit()
                except Exception as exc:
                    db.rollback()
                    status = f"failed:{type(exc).__name__}"
                counts[status] = counts.get(status, 0) + 1
            db.expunge_all()
    print(json.dumps(counts))
    return int(any(key.startswith("failed:") for key in counts))


if __name__ == "__main__":
    raise SystemExit(main())
