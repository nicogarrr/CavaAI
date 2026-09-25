"""Ingesta del corpus libre de value investing en la biblioteca de conocimiento.

Solo fuentes PUBLICAS y declaradas (division "libre" del corpus aprobada):
- Cartas anuales de Numantia Patrimonio (Emerito Quintana), publicadas por
  la propia gestora en su web (2017-hoy).
- Cartas anuales de Warren Buffett (Berkshire Hathaway), indice publico.

Los libros con copyright (Parames, Rallo, Huerta de Soto...) NO se ingieren:
de ellos solo existiran fichas/notas generadas desde el corpus libre.

Idempotente: la biblioteca deduplica por checksum SHA-256. Los fallos de
descarga se saltan y se listan al final; nunca se inventan contenidos.

Uso (dentro del contenedor backend):
    python scripts/ingest_corpus.py --tenant-external-id <ext> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import KnowledgeCollection, Tenant
from app.services.knowledge_library_service import KnowledgeLibraryService

COLLECTION_NAME = "Corpus libre value investing"
COLLECTION_SLUG = "corpus-libre-value-investing"

NUMANTIA_AUTHOR = "Emérito Quintana (Numantia Patrimonio)"
NUMANTIA_YEARS = range(2017, 2026)

BUFFETT_AUTHOR = "Warren E. Buffett (Berkshire Hathaway)"
BUFFETT_INDEX = "https://www.berkshirehathaway.com/letters/letters.html"

USER_AGENT = "CavaAI research corpus ingest (contact: owner-configured)"


def _declared_numantia_sources() -> list[dict]:
    return [
        {
            "title": f"Numantia Patrimonio - Carta anual {year}",
            "url": f"https://numantiapatrimonio.com/pdfs/Numantia{year}.pdf",
            "filename": f"Numantia{year}.pdf",
            "author": NUMANTIA_AUTHOR,
            "document_type": "fund_letter",
            "language": "es",
        }
        for year in NUMANTIA_YEARS
    ]


def _discover_buffett_sources(client: httpx.Client) -> list[dict]:
    """Lee el indice publico de cartas de Berkshire y declara cada enlace.

    El indice lista las cartas con su año; solo se aceptan enlaces del propio
    dominio (html/htm/pdf). Si el indice no responde, se devuelve lista vacia
    y se reporta - nunca se fabrican URLs.
    """
    try:
        response = client.get(BUFFETT_INDEX)
        response.raise_for_status()
    except Exception:
        return []
    sources: list[dict] = []
    for href, label in re.findall(
        r'href="([^"]+\.(?:html?|pdf))"[^>]*>([^<]*)', response.text, re.IGNORECASE
    ):
        if href.startswith("http") and "berkshirehathaway.com" not in href:
            continue
        url = href if href.startswith("http") else f"https://www.berkshirehathaway.com/letters/{href}"
        year_match = re.search(r"(19|20)\d{2}", label) or re.search(r"(19|20)\d{2}", href)
        if not year_match:
            continue
        year = year_match.group(0)
        ext = href.rsplit(".", 1)[-1].lower()
        sources.append(
            {
                "title": f"Berkshire Hathaway - Carta anual accionistas {year}",
                "url": url,
                "filename": f"Berkshire{year}.{ext}",
                "author": BUFFETT_AUTHOR,
                "document_type": "fund_letter",
                "language": "en",
            }
        )
    return sources


def _get_or_create_collection(db) -> KnowledgeCollection:
    collection = db.scalar(
        select(KnowledgeCollection).where(KnowledgeCollection.slug == COLLECTION_SLUG)
    )
    if collection is None:
        collection = KnowledgeCollection(
            name=COLLECTION_NAME,
            slug=COLLECTION_SLUG,
            description="Corpus público y libre de value investing (cartas de gestores, fuentes declaradas).",
            collection_type="system",
        )
        db.add(collection)
        db.flush()
    return collection


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-external-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stats = {"ingested": 0, "duplicates": 0, "failed": [], "skipped_sources": []}

    db = SessionLocal()
    try:
        tenant = db.scalar(
            select(Tenant).where(Tenant.external_id == args.tenant_external_id)
        )
        if tenant is None:
            print(f"Tenant no encontrado: {args.tenant_external_id}")
            return 1
        db.info["tenant_id"] = tenant.id

        service = KnowledgeLibraryService()
        collection = _get_or_create_collection(db)
        db.commit()

        with httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True
        ) as client:
            sources = _declared_numantia_sources()
            buffett = _discover_buffett_sources(client)
            if not buffett:
                stats["skipped_sources"].append("buffett_index_unreachable")
            sources.extend(buffett)

            for source in sources:
                if args.dry_run:
                    print(f"DRY: {source['title']} <- {source['url']}")
                    continue
                try:
                    response = client.get(source["url"])
                    response.raise_for_status()
                    result = service.ingest_bytes(
                        db,
                        title=source["title"],
                        content=response.content,
                        filename=source["filename"],
                        document_type=source["document_type"],
                        collection_id=collection.id,
                        author=source["author"],
                        source_url=source["url"],
                        language=source["language"],
                    )
                    db.commit()
                    if result["status"] == "duplicate":
                        stats["duplicates"] += 1
                    else:
                        stats["ingested"] += 1
                except Exception as exc:  # noqa: BLE001 - una fuente no frena al corpus
                    db.rollback()
                    stats["failed"].append(
                        {"title": source["title"], "error": str(exc)[:200]}
                    )
                time.sleep(1.0)
    finally:
        db.close()

    print("RESULTADO:", json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
