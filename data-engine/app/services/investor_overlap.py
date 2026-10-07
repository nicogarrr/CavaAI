"""Solape derivado por CUSIP exacto, sin emparejar emisores por nombre."""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Position
from app.models.entities import InstrumentReference
from app.services.investors import INVESTORS, _latest_view, _manager, most_bought


def _cusip(company: Company, reference: InstrumentReference | None) -> tuple[str | None, str | None]:
    if reference and reference.cusip and re.fullmatch(r"[A-Z0-9*@#]{9}", reference.cusip):
        return reference.cusip, f"Referencia {reference.source} · {reference.as_of.isoformat()}"
    isin = company.isin or ""
    # Un ISIN US/CA contiene el CUSIP. Validar el checksum ISIN antes de derivarlo.
    if re.fullmatch(r"(?:US|CA)[A-Z0-9]{9}\d", isin):
        digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in isin)
        checksum = sum((n * 2 // 10 + n * 2 % 10) if i % 2 else n
                       for i, n in enumerate(map(int, reversed(digits))))
        if checksum % 10 == 0:
            return isin[2:11], "CUSIP derivado del ISIN registrado"
    return None, None


def portfolio_overlap(db: Session) -> dict:
    tenant = db.info.get("tenant_id")
    empty = {"status": "sin_datos", "kind": "derivado", "positions": [], "not_owned": [],
             "unresolved_positions": 0, "managers_with_data": 0, "managers_without_data": 0, "managers_partial": 0,
             "report_dates": [], "message": "Cartera sin posiciones abiertas."}
    if tenant is None:
        return empty
    companies = list(db.scalars(select(Company).join(Position, Position.company_id == Company.id)
                              .where(Position.tenant_id == tenant, Position.quantity > 0).distinct()).all())
    if not companies:
        return empty
    refs = {r.ticker_normalized: r for r in db.scalars(select(InstrumentReference).where(
        InstrumentReference.ticker_normalized.in_([c.ticker.strip().upper() for c in companies]))).all()}
    positions = []
    for c in companies:
        cusip, source = _cusip(c, refs.get(c.ticker.strip().upper()))
        positions.append({"ticker": c.ticker, "name": c.name, "cusip": cusip,
                          "identity_source": source, "holders": [],
                          "status": "sin_identificador" if cusip is None else "sin_coincidencias"})
    by_cusip = {}
    for p in positions:
        if p["cusip"]:
            by_cusip.setdefault(p["cusip"], []).append(p)
    periods = set()
    available = missing = partial = 0
    for inv in INVESTORS:
        if not inv.cik:
            continue
        manager = _manager(db, inv)
        rows = _latest_view(db, manager) if manager else []
        if not rows:
            missing += 1
            continue
        available += 1
        partial += int(manager.coverage == "partial")
        seen = set()
        for row in rows:
            if row.put_call or row.cusip not in by_cusip or row.cusip in seen:
                continue
            seen.add(row.cusip)
            periods.add(row.report_date.isoformat())
            holder = {"slug": inv.slug, "name": inv.name, "report_date": row.report_date.isoformat(),
                      "filing_date": row.filing_date.isoformat() if row.filing_date else None,
                      "filing_url": row.filing_url, "coverage": manager.coverage}
            for position in by_cusip[row.cusip]:
                position["holders"].append(holder)
                position["status"] = "coincidencia"
    unresolved = sum(p["cusip"] is None for p in positions)
    bought = most_bought(db)
    # Sin identidad completa no se puede afirmar que una compra ajena esté fuera de la cartera.
    candidates = [] if unresolved else [i for i in bought["items"]
                                       if i["cusip"] not in by_cusip and i["buyers_count"] >= 2]
    return {**empty, "status": "ok" if available else "sin_datos", "positions": positions,
            "not_owned": candidates, "unresolved_positions": unresolved,
            "managers_with_data": available, "managers_without_data": missing, "managers_partial": partial,
            "report_dates": sorted(periods | set(bought["report_dates"])),
            "message": None if available else "Sin informes 13F sincronizados.",
            "comparison_complete": unresolved == 0 and missing == 0 and partial == 0,
            "limitations": ["Derivado por CUSIP exacto. Sin coincidencia no significa ausencia en todas sus carteras.",
                            "13F histórico, con hasta 45 días de retraso. Solo posiciones largas declaradas; no opciones."]}
