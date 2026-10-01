"""F365: first IBKR import must snapshot the imported rows (autoflush=False)."""

from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import PortfolioDailySnapshot, Tenant
from app.services.ibkr_import_service import IBKRImportService

XML = """<?xml version="1.0"?>
<FlexQueryResponse><FlexStatements><FlexStatement accountId="U1">
<OpenPosition symbol="AAPL" position="10" markPrice="100" positionValue="1000" costBasisPrice="90" currency="EUR" reportDate="2026-08-20"/>
<CashReport currency="EUR" endingCash="500" reportDate="2026-08-20"/>
</FlexStatement></FlexStatements></FlexQueryResponse>"""


def test_first_import_snapshot_is_not_zero_with_autoflush_off():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        tenant = Tenant(external_id="f365", name="f365")
        db.add(tenant)
        db.commit()
        db.info["tenant_id"] = tenant.id
        result = IBKRImportService().import_flex_xml(db, XML)
        assert result["positions_imported"] == 1
        snapshot = db.query(PortfolioDailySnapshot).one()
        assert snapshot.total_value_base == Decimal("1500")
