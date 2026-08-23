"""Barre companies con datos debiles y las enriquece desde Finnhub."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.services.company_enrichment_service import CompanyEnrichmentService


def main() -> None:
    db = SessionLocal()
    service = CompanyEnrichmentService()
    try:
        result = service.enrich_all(db, sleep_between=0.8)
        print("RESULTADO:", result)
    finally:
        service.close()
        db.close()


if __name__ == "__main__":
    main()