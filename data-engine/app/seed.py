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


STUB_TYPE = "research_candidate"
STUB_MODEL = "unassigned"
TAXONOMY_FIELDS = (
    "company_type",
    "valuation_model",
    "special_sources",
    "special_risks",
    "factor_tags",
)


def apply_master_taxonomy_to_stubs(db) -> list[str]:
    """Completa la taxonomia de fichas stub (creadas por buscador/ensure).

    En produccion el seed completo no corre, asi que un ticker del maestro que
    se creo como stub (research_candidate/unassigned) nunca recibia su motor de
    valoracion. Solo se tocan stubs sin asignar: una ficha con modelo o tipo
    ya decididos no se sobrescribe. No crea empresas ni toca datos de usuario.
    """
    updated: list[str] = []
    for payload in COMPANY_MASTER:
        company = db.scalar(select(Company).where(Company.ticker == payload["ticker"]))
        if company is None:
            continue
        if (company.company_type or "") != STUB_TYPE or (company.valuation_model or "") != STUB_MODEL:
            continue
        for key in TAXONOMY_FIELDS:
            if key in payload:
                setattr(company, key, payload[key])
        updated.append(company.ticker)
    return updated


def seed() -> None:
    """Install only the global company taxonomy; user data is never seeded."""
    init_db()
    ensure_company_master()


if __name__ == "__main__":
    seed()
    print("Seed complete: company taxonomy loaded; no user portfolio or evidence was created.")
