from sqlalchemy import select

from app.core.database import SessionLocal, init_db
from app.data.company_master import COMPANY_MASTER
from app.models import Company


def upsert_company(db, payload: dict) -> Company:
    company = db.scalar(select(Company).where(Company.ticker == payload["ticker"]))
    if company is None:
        company = Company(**payload)
        db.add(company)
        db.flush()
    else:
        for key, value in payload.items():
            setattr(company, key, value)
    return company


def ensure_company_master() -> None:
    db = SessionLocal()
    try:
        for payload in COMPANY_MASTER:
            upsert_company(db, payload)
        db.commit()
    finally:
        db.close()


def seed() -> None:
    """Install only the global company taxonomy; user data is never seeded."""
    init_db()
    ensure_company_master()


if __name__ == "__main__":
    seed()
    print("Seed complete: company taxonomy loaded; no user portfolio or evidence was created.")
