"""Ingesta del corpus libre de value investing en la biblioteca de conocimiento.

Solo fuentes PUBLICAS y declaradas (division "libre" del corpus aprobada):
- Cartas anuales de Numantia Patrimonio (Emerito Quintana), publicadas por
  la propia gestora en su web (2017-hoy).
- Cartas anuales de Warren Buffett (Berkshire Hathaway), indice publico.
Las siguientes fuentes se anaden tras la peticion del usuario del 2026-09-25
de ampliar la ingesta con mas fuentes gratuitas hacia el RAG; misma politica:
solo documentos publicos publicados por la propia gestora:
- Cartas a inversores de Azvalor AM (indice publico de la gestora; cada
  anuncio enlaza la "carta en PDF" oficial).
Cobas AM queda fuera por ahora: sus comentarios se publican como paginas
HTML con mucho chrome de sitio y sin enlace PDF estable; candidata a una
futura ingesta de contenido HTML con extraccion de cuerpo.
- Cartas trimestrales de Magallanes Value Investors (seccion #cartas de su
  pagina de noticias; PDFs publicos).

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

BUFFETT_AUTHOR = "Warren E. Buffett (Berkshire Hathaway)"
BUFFETT_INDEX = "https://www.berkshirehathaway.com/letters/letters.html"

USER_AGENT = "CavaAI research corpus ingest (contact: owner-configured)"

AZVALOR_AUTHOR = "Azvalor Asset Management"
AZVALOR_INDEX = "https://www.azvalor.com/categorias_anuncios/cartas-a-inversores/"

MAGALLANES_AUTHOR = "Magallanes Value Investors"
MAGALLANES_NOTICIAS = "https://magallanesvalue.com/noticias/"

MAX_LETTER_PAGES_PER_SOURCE = 40


def _slug_title(slug: str) -> str:
    return slug.strip("/").rsplit("/", 1)[-1].replace("-", " ").strip()


def _extract_azvalor_pages(html: str) -> list[str]:
    """Enlaces a anuncios de cartas en el indice publico de Azvalor."""
    found = re.findall(
        r'href="(https://www\.azvalor\.com/anuncios-y-comunicados/carta-[^"]+/?)"',
        html,
        re.IGNORECASE,
    )
    return sorted(set(found))


def _extract_azvalor_gateway(html: str) -> str | None:
    """En cada anuncio, el enlace oficial a la carta en PDF: los recientes usan
    una pagina pasarela /azvalor-carta-* (redirect al PDF) y los antiguos un
    PDF directo en wp-content/uploads con "Carta" en el nombre."""
    match = re.search(r'href="(https://www\.azvalor\.com/azvalor-carta-[^"]+/?)"', html, re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(
        r'href="(https://www\.azvalor\.com/wp-content/uploads/[^"]*Carta[^"]*\.pdf)"',
        html,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def _discover_azvalor_sources(client: httpx.Client) -> list[dict]:
    try:
        response = client.get(AZVALOR_INDEX)
        response.raise_for_status()
    except Exception:
        return []
    sources: list[dict] = []
    for page_url in _extract_azvalor_pages(response.text)[:MAX_LETTER_PAGES_PER_SOURCE]:
        try:
            page = client.get(page_url)
            page.raise_for_status()
        except Exception:
            continue
        gateway = _extract_azvalor_gateway(page.text)
        if not gateway:
            continue
        slug = _slug_title(page_url)
        sources.append(
            {
                "title": f"Azvalor - {slug}",
                "url": gateway,
                "filename": f"Azvalor-{slug.replace(' ', '_')}.pdf",
                "author": AZVALOR_AUTHOR,
                "document_type": "fund_letter",
                "language": "es",
            }
        )
        time.sleep(0.5)
    return sources


def _extract_magallanes_pdfs(html: str) -> list[str]:
    found = re.findall(
        r'href="(https://magallanesvalue\.com/wp-content/uploads/MAGALLANES-(?:CARTA|LETTER)-[^"#]+\.pdf)',
        html,
        re.IGNORECASE,
    )
    return sorted(set(found))


def _discover_magallanes_sources(client: httpx.Client) -> list[dict]:
    try:
        response = client.get(MAGALLANES_NOTICIAS)
        response.raise_for_status()
    except Exception:
        return []
    sources: list[dict] = []
    for pdf_url in _extract_magallanes_pdfs(response.text):
        filename = pdf_url.rsplit("/", 1)[-1]
        label = filename.replace("MAGALLANES-", "").replace(".pdf", "").replace("-", " ")
        label = label.removeprefix("CARTA ").removeprefix("LETTER ")
        sources.append(
            {
                "title": f"Magallanes Value Investors - Carta {label}",
                "url": pdf_url,
                "filename": filename,
                "author": MAGALLANES_AUTHOR,
                "document_type": "fund_letter",
                "language": "es",
            }
        )
    return sources



NUMANTIA_HOME = "https://numantiapatrimonio.com/"


def _discover_numantia_sources(client: httpx.Client) -> list[dict]:
    """Descubre las cartas publicadas en la web de la gestora (home lista los
    PDFs vigentes: anuales + semestrales sueltas). Si la home no responde,
    se devuelve lista vacia y se reporta - nunca se fabrican URLs."""
    try:
        response = client.get(NUMANTIA_HOME)
        response.raise_for_status()
    except Exception:
        return []
    sources: list[dict] = []
    seen: set[str] = set()
    for href in re.findall(r'href="(pdfs/[^"]+\.pdf)"', response.text, re.IGNORECASE):
        if href in seen:
            continue
        seen.add(href)
        filename = href.rsplit("/", 1)[-1]
        label = filename.replace("Numantia", "").replace(".pdf", "").strip("_") or "?"
        sources.append(
            {
                "title": f"Numantia Patrimonio - Carta {label}",
                "url": f"https://numantiapatrimonio.com/{href}",
                "filename": filename,
                "author": NUMANTIA_AUTHOR,
                "document_type": "fund_letter",
                "language": "es",
            }
        )
    return sources


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



def _ingest_from_dir(db, service, collection, directory: Path, dry_run: bool) -> dict:
    """Ingiere ficheros locales declarados en <dir>/manifest.json.

    Formato del manifest: [{"file": "Berkshire2023.pdf", "title": "...",
    "author": "...", "source_url": "https://...", "document_type":
    "fund_letter", "language": "en"}, ...]. La URL de origen se declara
    siempre: descargar a mano no convierte la procedencia en implicita.
    """
    stats = {"ingested": 0, "duplicates": 0, "failed": [], "skipped_sources": []}
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        stats["failed"].append({"title": str(manifest_path), "error": "manifest.json no encontrado"})
        return stats
    entries = json.loads(manifest_path.read_text())
    for entry in entries:
        file_path = directory / entry["file"]
        if dry_run:
            print(f"DRY: {entry['title']} <- {file_path.name} (origen: {entry.get('source_url')})")
            continue
        try:
            result = service.ingest_bytes(
                db,
                title=entry["title"],
                content=file_path.read_bytes(),
                filename=entry["file"],
                document_type=entry.get("document_type", "fund_letter"),
                collection_id=collection.id,
                author=entry.get("author"),
                source_url=entry.get("source_url"),
                language=entry.get("language", "en"),
            )
            db.commit()
            if result["status"] == "duplicate":
                stats["duplicates"] += 1
            else:
                stats["ingested"] += 1
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            stats["failed"].append({"title": entry.get("title"), "error": str(exc)[:200]})
    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-external-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--from-dir",
        help="Ingiere ficheros locales con manifest.json (para fuentes que bloquean "
        "la IP del servidor; el manifest declara titulo, autor y URL de origen).",
    )
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

        if args.from_dir:
            stats.update(_ingest_from_dir(db, service, collection, Path(args.from_dir), args.dry_run))
            print("RESULTADO:", json.dumps(stats, indent=2, ensure_ascii=False))
            return 0

        with httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True
        ) as client:
            sources = _discover_numantia_sources(client)
            if not sources:
                stats["skipped_sources"].append("numantia_home_unreachable")
            buffett = _discover_buffett_sources(client)
            if not buffett:
                stats["skipped_sources"].append("buffett_index_unreachable")
            sources.extend(buffett)
            for name, discoverer in (
                ("azvalor", _discover_azvalor_sources),
                ("magallanes", _discover_magallanes_sources),
            ):
                found = discoverer(client)
                if not found:
                    stats["skipped_sources"].append(f"{name}_unreachable_or_empty")
                sources.extend(found)

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
