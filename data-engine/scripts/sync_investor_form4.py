"""Sincroniza los Form 4 recientes de un inversor sin 13F (idempotente).

Uso: python scripts/sync_investor_form4.py trump|bezos [--limit 20]
Solo aplica a inversores con CIK de declarante revisado (FORM4_FILER_CIK).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.services.investor_portfolio import FORM4_FILER_CIK, sync_form4


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", choices=sorted(FORM4_FILER_CIK))
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        created = sync_form4(db, args.slug, limit=args.limit)
        print(f"{args.slug}: {created} movimientos nuevos")
    finally:
        db.close()


if __name__ == "__main__":
    main()
