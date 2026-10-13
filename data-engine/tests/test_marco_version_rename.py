"""La migracion 0060 renombra MARCO_NICO_V* sin chocar con el unique ni dejar duplicados."""
import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import CalculatedMetric, Company
from tests.test_ibkr_import import _tenant_session

_spec = importlib.util.spec_from_file_location(
    "mig0060", Path(__file__).resolve().parents[1] / "alembic/versions/0060_marco_version_rename.py")
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)


def _row(company, metric, period, version):
    return CalculatedMetric(company_id=company.id, metric=metric, period=period,
                            definition_version=version, formula="f")


def test_rename_moves_old_rows_and_drops_old_when_new_exists():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db: Session = _tenant_session(engine)
    co = Company(ticker="MRN", name="Marco Rename Co", exchange="TEST", currency="USD", sector="Software",
                 industry="Application Software", company_type="standard", valuation_model="standard_dcf",
                 special_sources=[], special_risks=[], factor_tags=[])
    db.add(co)
    db.flush()
    db.add_all([
        _row(co, "quality_moat_score_v2", "2025-FY", "MARCO_NICO_V2"),  # solo vieja: se renombra
        _row(co, "quality_moat_score_v2", "2024-FY", "MARCO_NICO_V2"),  # vieja + nueva: se borra la vieja
        _row(co, "quality_moat_score_v2", "2024-FY", "MARCO_V2"),
        _row(co, "other", "2025-FY", "v1"),
    ])
    db.flush()
    for old, new in mig.RENAMES:
        mig.rename_version(db.connection(), old, new)
    db.expire_all()
    rows = sorted((r.period, r.definition_version) for r in db.scalars(select(CalculatedMetric)).all())
    assert rows == [("2024-FY", "MARCO_V2"), ("2025-FY", "MARCO_V2"), ("2025-FY", "v1")]
    db.close()
