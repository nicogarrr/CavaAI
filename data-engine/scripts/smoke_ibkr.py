"""Smoke test sintetico del IBKRImportService (pipeline completo)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Forzar DB en memoria si el entorno lo permite; si no, usar sqlite temporal
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import CashBalance, Company, Position, Transaction
from app.services.ibkr_import_service import IBKRImportService

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)

xml = """<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse queryName="test">
  <FlexStatements>
    <FlexStatement accountId="U123456">
      <OpenPosition symbol="AAPL" position="10" markPrice="180.5" positionValue="1805" costBasisPrice="150" currency="USD" reportDate="2026-08-20"/>
      <OpenPosition symbol="MSFT" position="5" markPrice="400" positionValue="2000" costBasisPrice="350" currency="USD" reportDate="2026-08-20"/>
      <CashReport currency="USD" endingCash="1234.56" settledCash="1000" reportDate="2026-08-20"/>
      <Trade symbol="AAPL" tradeID="T1" buySell="BUY" quantity="10" tradePrice="150" ibCommission="1" tradeDate="2026-06-01" currency="USD"/>
      <CashTransaction type="Dividends" trxID="D1" amount="15.5" dateTime="2026-07-01" currency="USD"/>
      <CashTransaction type="Other Fees" trxID="F1" amount="-3.2" dateTime="2026-07-02" currency="USD"/>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>"""

with Session(engine) as db:
    from app.models import Tenant

    tenant = Tenant(external_id="smoke-tenant", name="Smoke")
    db.add(tenant)
    db.flush()
    db.info["tenant_id"] = tenant.id
    tenant_id = tenant.id
    result = IBKRImportService().import_flex_xml(db, xml)
    print("RESULT:", result)

with Session(engine) as db:
    print("positions:", db.query(Position).count(),
          "| cash:", db.query(CashBalance).count(),
          "| tx:", db.query(Transaction).count(),
          "| companies:", db.query(Company).count())
    for t in db.query(Transaction).all():
        print("  tx:", t.action, t.quantity, t.price, t.company_id, t.external_id)
    p = db.query(Position).first()
    print("sample position:", p.company_id, p.quantity, p.average_cost, p.market_value, p.fx_rate, p.market_value_base)

# Idempotencia: importar 2 veces no debe duplicar
with Session(engine) as db:
    db.info["tenant_id"] = tenant_id
    result2 = IBKRImportService().import_flex_xml(db, xml)
    print("RESULT2 (re-import):", result2)
with Session(engine) as db:
    print("after re-import -> positions:", db.query(Position).count(), "| tx:", db.query(Transaction).count())
print("OK")