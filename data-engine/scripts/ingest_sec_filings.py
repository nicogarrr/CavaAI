"""Ingesta de filings SEC verificados contra su indice como Document oficial.

Entrada: el directorio que deja scripts/build_sec_evidence.py (manifest.json,
indices y documentos). Cada documento se verifica con
app.services.sec_filing_evidence.verify_entry (CIK de la empresa, accession,
Filing Date del indice, nombre/tipo listados, sha256 y tamano acotado) ANTES
de crear un Document(source_type="primary_official"). Si una entrada falla, no
se ingiere y se informa; nunca se etiqueta como oficial por declaracion.

Idempotente por (empresa, url, sha256). --dry-run no escribe.

Uso (dentro del contenedor backend):
    python scripts/ingest_sec_filings.py --tenant-external-id <ext> \
        --ticker ASTS --dir /tmp/asts [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Company, Document, DocumentChunk, Tenant
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.document_store import DocumentStore
from app.services.sec_filing_evidence import EvidenceError, derive_index_url, parse_index, verify_entry


def ingest_filings(db, company: Company, entries: list[dict], base_dir: Path, *, dry_run: bool) -> list[dict]:
    tenant_id = db.info.get("tenant_id")
    ingestor = DocumentIngestionService()
    results: list[dict] = []
    for entry in entries:
        try:
            filing = verify_entry(entry, base_dir, company.cik, company.ticker)
        except (EvidenceError, OSError, KeyError) as exc:
            results.append({"url": entry.get("url"), "status": "rejected", "reason": str(exc)})
            continue
        existing = db.scalar(
            select(Document).where(
                Document.company_id == company.id,
                Document.source_url == filing.url,
                Document.checksum == filing.sha256,
                Document.source_type == "primary_official",
            )
        )
        if existing is not None:
            results.append({"url": filing.url, "status": "duplicate", "document_id": existing.id})
            continue
        parsed = ingestor._parse(filing.body, filing.filename, ".htm", "text/html")
        chunks = ingestor._chunk_blocks(parsed.blocks, filing.sha256, parsed.parser, filing.filename, filing.url)
        if not chunks:
            results.append({"url": filing.url, "status": "rejected", "reason": "sin texto"})
            continue
        if dry_run:
            results.append({"url": filing.url, "status": "dry_run", "chunks": len(chunks)})
            continue
        storage_uri = DocumentStore().put_bytes(
            company.ticker, "primary_official", f"{filing.sha256[:12]}-{filing.filename}", filing.raw,
            tenant_id=tenant_id, content_type="text/html",
        )
        index_evidence = parse_index((base_dir / entry["index_file"]).read_text(encoding="utf-8"))
        parent_form = "8-K" if any(form == "8-K" for form, _ in index_evidence.documents.values()) else None
        document = Document(
            company_id=company.id,
            title=f"{company.ticker} {filing.form_type} {filing.filing_date.isoformat()} ({filing.filename})",
            source_type="primary_official",
            source_url=filing.url,
            storage_uri=storage_uri,
            published_at=datetime(filing.filing_date.year, filing.filing_date.month, filing.filing_date.day, tzinfo=UTC),
            checksum=filing.sha256,
            metadata_={
                "form": filing.form_type,
                "parent_form": parent_form,
                "accession": filing.accession,
                "cik": filing.cik,
                "period_of_report": filing.period.isoformat() if filing.period else None,
                "date_source": "sec_filing_index",
                "index_url": derive_index_url(filing.cik, filing.accession),
                "index_sha256": entry["index_sha256"],
                "size_delta_vs_index": filing.size_delta,
                "raw_sha256": filing.sha256,
                "body_sha256": filing.body_sha256,
                "checksum_semantics": "Document.checksum y storage = bytes servidos por sec.gov (raw, con envoltorio SGML si lo trae); body_sha256 = raw sin envoltorio, usado para parsear",
                "origin_verification": "captura con cruce vivo contra sec.gov (indice, submissions, doble descarga); no es una firma criptografica de la SEC",
                "capture": entry["capture"],
                "parser": parsed.parser,
                "warnings": parsed.warnings,
            },
        )
        db.add(document)
        db.flush()
        for index, chunk in enumerate(chunks):
            db.add(DocumentChunk(
                document_id=document.id, chunk_index=index, text=chunk["text"],
                token_count=len(chunk["text"].split()), metadata_=chunk["metadata"],
            ))
        db.commit()
        from app.services.filing_intelligence import analyze_document

        analysis = analyze_document(db, document)
        db.commit()
        results.append({"url": filing.url, "status": "ingested", "document_id": document.id, "chunks": len(chunks), "filing_analysis": analysis})
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-external-id", required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--dir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    base = Path(args.dir)
    entries = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
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
        for result in ingest_filings(db, company, entries, base, dry_run=args.dry_run):
            print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
