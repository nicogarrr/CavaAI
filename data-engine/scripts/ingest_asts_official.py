"""Ingesta de documentos OFICIALES de una empresa (SEC) como Document ASTS.

Solo originales de sec.gov descargados por el operador (el VM no llega a SEC).
Cada documento queda como Document(source_type="primary_official") con su
URL de filing, fecha de presentacion (la del indice del filing, no inferida),
checksum y chunks con pagina/seccion. Idempotente por (url, checksum).

Manifiesto JSON: lista de {"file", "url", "title", "published_at": "YYYY-MM-DD",
"form"}. Todas las URLs deben ser https://www.sec.gov/Archives/...

Uso (dentro del contenedor backend):
    python scripts/ingest_asts_official.py --tenant-external-id <ext> \
        --ticker ASTS --manifest /tmp/asts/manifest.json [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Company, Document, DocumentChunk, Tenant
from app.services.document_ingestion_service import DocumentIngestionService, _extension
from app.services.document_store import DocumentStore


def _is_sec_filing_url(url: str) -> bool:
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and parts.hostname == "www.sec.gov"
        and parts.path.startswith("/Archives/edgar/data/")
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-external-id", required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    ingestor = DocumentIngestionService()
    with SessionLocal() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.external_id == args.tenant_external_id))
        if tenant is None:
            print(f"Tenant no encontrado: {args.tenant_external_id}")
            return 1
        db.info["tenant_id"] = tenant.id
        company = db.scalar(select(Company).where(Company.ticker == args.ticker.upper()))
        if company is None:
            print(f"Empresa no encontrada: {args.ticker}")
            return 1
        for entry in entries:
            url = entry["url"]
            if not _is_sec_filing_url(url):
                print(f"SALTADO (no es filing SEC): {url}")
                continue
            path = manifest_path.parent / entry["file"]
            content = path.read_bytes()
            checksum = hashlib.sha256(content).hexdigest()
            existing = db.scalar(
                select(Document).where(
                    Document.company_id == company.id,
                    Document.source_url == url,
                    Document.checksum == checksum,
                    Document.source_type == "primary_official",
                )
            )
            if existing is not None:
                print(f"DUPLICADO: {entry['title']} (document {existing.id})")
                continue
            ext = _extension(path.name, "text/html")
            parsed = ingestor._parse(content, path.name, ext, "text/html")
            chunks = ingestor._chunk_blocks(parsed.blocks, checksum, parsed.parser, path.name, url)
            if not chunks:
                print(f"SIN TEXTO: {entry['title']}")
                continue
            published = datetime.fromisoformat(entry["published_at"]).replace(tzinfo=UTC)
            print(f"{'DRY ' if args.dry_run else ''}{entry['title']}: {len(chunks)} chunks, {len(content)} B")
            if args.dry_run:
                continue
            storage_uri = DocumentStore().put_bytes(
                company.ticker, "primary_official", f"{checksum[:12]}-{path.name}", content,
                tenant_id=tenant.id, content_type="text/html",
            )
            document = Document(
                company_id=company.id,
                title=entry["title"],
                source_type="primary_official",
                source_url=url,
                storage_uri=storage_uri,
                published_at=published,
                checksum=checksum,
                metadata_={
                    "form": entry.get("form"),
                    "date_source": "sec_filing_index",
                    "parser": parsed.parser,
                    "warnings": parsed.warnings,
                    "byte_count": len(content),
                    "ingested_by": "scripts/ingest_asts_official.py",
                },
            )
            db.add(document)
            db.flush()
            for index, chunk in enumerate(chunks):
                db.add(
                    DocumentChunk(
                        document_id=document.id,
                        chunk_index=index,
                        text=chunk["text"],
                        token_count=len(chunk["text"].split()),
                        metadata_=chunk["metadata"],
                    )
                )
            db.commit()
            print(f"OK document {document.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
