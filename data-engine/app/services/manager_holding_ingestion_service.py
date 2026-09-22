"""Per-manager 13F holdings ingestion from SEC EDGAR (tier_1 official, free).

Decision value: what reviewed institutional managers hold, add and trim is
real evidence for theses and watchlists. Boundaries (parent-approved):
- only managers in REVIEWED_MANAGERS (exact CIK <-> official EDGAR name,
  reviewed one by one); unreviewed CIKs are refused, never guessed;
- holdings are stored as filed: CUSIP + issuer name, tickers never inferred;
- amendments (13F-HR/A) are separate immutable accessions; prior filings are
  never rewritten;
- 13F is quarterly, up to a 45-day lag, long-only US-listed - consumers must
  show these limits; per-company ownership is out of scope until an
  authoritative CUSIP mapping exists.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FundManager, ManagerHolding
from app.services.connectors import form13f
from app.services.provenance import Coverage, SourceKind, provenance

SOURCE = "sec_edgar_13f"

# Reviewed one by one before adding: exact CIK <-> official EDGAR name.
# Small by design; Nico extends this table explicitly.
REVIEWED_MANAGERS: dict[str, str] = {
    "0001067983": "Berkshire Hathaway Inc",
}

LIMITATIONS = [
    "Quarterly cadence with up to a 45-day reporting lag",
    "Long-only US-listed positions; no shorts, no non-13F securities",
    "Holdings as filed: CUSIP + issuer name; tickers never inferred",
    "Amendments are separate immutable filings",
]


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class ManagerHoldingIngestionService:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client

    def sync_manager(self, db: Session, *, cik: str) -> dict[str, Any]:
        cik = str(cik).strip().zfill(10)
        if cik not in REVIEWED_MANAGERS:
            return {
                "cik": cik,
                "status": "unreviewed_manager",
                "provenance": provenance(
                    SOURCE, SourceKind.OFFICIAL, coverage=Coverage.UNAVAILABLE,
                    note="CIK not in the reviewed manager table",
                ),
            }

        manager = db.scalar(select(FundManager).where(FundManager.cik == cik))
        if manager is None:
            manager = FundManager(cik=cik, name=REVIEWED_MANAGERS[cik])
            db.add(manager)
            db.flush()

        try:
            filings = form13f.recent_13f_filings(cik, client=self.client)
        except Exception as exc:  # noqa: BLE001 - honest unavailable, never break
            manager.coverage = Coverage.UNAVAILABLE.value
            manager.synced_at = datetime.now(UTC)
            db.add(manager)
            db.commit()
            return {
                "cik": cik,
                "manager": manager.name,
                "status": "unavailable",
                "reason": f"{type(exc).__name__}: {exc}",
                "provenance": provenance(SOURCE, SourceKind.OFFICIAL, coverage=Coverage.UNAVAILABLE),
            }

        if not filings:
            manager.coverage = Coverage.UNAVAILABLE.value
            manager.synced_at = datetime.now(UTC)
            db.add(manager)
            db.commit()
            return {
                "cik": cik,
                "manager": manager.name,
                "status": "unavailable",
                "reason": "no 13F-HR filings found",
                "provenance": provenance(SOURCE, SourceKind.OFFICIAL, coverage=Coverage.UNAVAILABLE),
            }

        # Latest two report periods (base filings + their amendments), so a
        # quarter-over-quarter comparison is computable from stored rows.
        report_dates = list(dict.fromkeys(f["report_date"] for f in filings))[:2]
        latest_report = report_dates[0]
        group = [f for f in filings if f["report_date"] in report_dates]
        ingested = 0
        errors: list[dict] = []
        fetched_at = datetime.now(UTC)

        for filing in group:
            accession = filing["accession_number"]
            try:
                url = form13f.information_table_url(
                    cik, accession, filing["primary_document"], client=self.client
                )
                if url is None:
                    errors.append({"accession": accession, "error": "information_table_not_found"})
                    continue
                rows = form13f.fetch_information_table(url, client=self.client)
            except Exception as exc:  # noqa: BLE001 - partial coverage, keep going
                errors.append({"accession": accession, "error": f"{type(exc).__name__}: {exc}"})
                continue
            existing = {
                (row.cusip, row.title_of_class, row.put_call)
                for row in db.scalars(
                    select(ManagerHolding).where(
                        ManagerHolding.manager_id == manager.id,
                        ManagerHolding.accession_number == accession,
                    )
                )
            }
            for row in rows:
                cusip = (row.get("cusip") or "").strip()
                if not cusip:
                    continue  # a row without CUSIP is unusable; never invent one
                title = (row.get("title_of_class") or "").strip()
                put_call = (row.get("put_call") or "").strip()
                if (cusip, title, put_call) in existing:
                    continue
                db.add(
                    ManagerHolding(
                        manager_id=manager.id,
                        accession_number=accession,
                        report_date=_date(filing["report_date"]),
                        filing_date=_date(filing["filing_date"]),
                        is_amendment=filing["is_amendment"],
                        name_of_issuer=(row.get("name_of_issuer") or "").strip(),
                        title_of_class=title,
                        cusip=cusip,
                        value_usd_thousands=_decimal(row.get("value_usd_thousands")),
                        shares=_decimal(row.get("ssh_prnamt")),
                        share_type=(row.get("ssh_prnamt_type") or "SH").strip(),
                        put_call=put_call,
                        investment_discretion=(row.get("investment_discretion") or "").strip(),
                        voting_sole=_decimal(row.get("voting_sole")),
                        voting_shared=_decimal(row.get("voting_shared")),
                        voting_none=_decimal(row.get("voting_none")),
                        filing_url=url,
                        source=SOURCE,
                        fetched_at=fetched_at,
                    )
                )
                ingested += 1

        manager.last_report_date = _date(latest_report)
        manager.coverage = Coverage.PARTIAL.value if errors else Coverage.OK.value
        manager.synced_at = fetched_at
        db.add(manager)
        db.commit()

        coverage = Coverage.PARTIAL if errors else Coverage.OK
        return {
            "cik": cik,
            "manager": manager.name,
            "status": "ok",
            "report_date": latest_report,
            "report_window": report_dates,
            "filings": [
                {
                    "accession_number": f["accession_number"],
                    "form": f["form"],
                    "is_amendment": f["is_amendment"],
                }
                for f in group
            ],
            "ingested_rows": ingested,
            "errors": errors,
            "limitations": LIMITATIONS,
            "provenance": provenance(
                SOURCE, SourceKind.OFFICIAL, fetched_at=fetched_at, coverage=coverage
            ),
        }

    def sync_all(self, db: Session) -> dict[str, Any]:
        return {
            "results": [self.sync_manager(db, cik=cik) for cik in REVIEWED_MANAGERS],
            "limitations": LIMITATIONS,
        }

    def changes(self, db: Session, *, cik: str) -> dict[str, Any]:
        """Quarter-over-quarter position changes for a reviewed manager.

        Compares the latest accession per report period (amendments supersede
        base filings in this view; every filing stays stored immutably).
        Keys are (cusip, title_of_class, put_call) - tickers never inferred.
        """
        cik = str(cik).strip().zfill(10)
        manager = db.scalar(select(FundManager).where(FundManager.cik == cik))
        if manager is None:
            return {
                "cik": cik,
                "status": "unavailable",
                "changes": [],
                "provenance": provenance(SOURCE, SourceKind.OFFICIAL, coverage=Coverage.UNAVAILABLE),
            }
        report_dates = [
            row[0]
            for row in db.execute(
                select(ManagerHolding.report_date)
                .where(ManagerHolding.manager_id == manager.id)
                .group_by(ManagerHolding.report_date)
                .order_by(ManagerHolding.report_date.desc())
            )
            if row[0] is not None
        ]
        if len(report_dates) < 2:
            return {
                "cik": cik,
                "manager": manager.name,
                "status": "insufficient_history",
                "detail": "need two stored 13F report periods to compare; re-sync after the next quarter",
                "changes": [],
                "provenance": provenance(SOURCE, SourceKind.INTERNAL, coverage=Coverage.UNAVAILABLE),
            }
        latest_date, previous_date = report_dates[0], report_dates[1]

        def period_rows(period: date) -> tuple[str, dict]:
            rows = db.scalars(
                select(ManagerHolding).where(
                    ManagerHolding.manager_id == manager.id,
                    ManagerHolding.report_date == period,
                )
            ).all()
            # Latest accession wins (amendments supersede base filings).
            accession = max(
                {row.accession_number for row in rows},
                key=lambda acc: (
                    max(
                        (r.filing_date or date.min)
                        for r in rows
                        if r.accession_number == acc
                    ),
                    acc,
                ),
            )
            view = {
                (row.cusip, row.title_of_class, row.put_call): row
                for row in rows
                if row.accession_number == accession
            }
            return accession, view

        latest_accession, latest = period_rows(latest_date)
        previous_accession, previous = period_rows(previous_date)

        changes: list[dict] = []
        for key in sorted(set(latest) | set(previous)):
            now, before = latest.get(key), previous.get(key)
            if now is not None and before is None:
                change = "new"
            elif now is None and before is not None:
                change = "closed"
            else:
                assert now is not None and before is not None
                now_shares = now.shares or Decimal(0)
                before_shares = before.shares or Decimal(0)
                if now_shares > before_shares:
                    change = "increased"
                elif now_shares < before_shares:
                    change = "decreased"
                else:
                    change = "unchanged"
            subject = now or before
            assert subject is not None
            changes.append(
                {
                    "change": change,
                    "name_of_issuer": subject.name_of_issuer,
                    "title_of_class": subject.title_of_class,
                    "cusip": subject.cusip,
                    "put_call": subject.put_call or None,
                    "shares_latest": float(now.shares) if now and now.shares is not None else None,
                    "shares_previous": (
                        float(before.shares) if before and before.shares is not None else None
                    ),
                    "value_usd_thousands_latest": (
                        float(now.value_usd_thousands)
                        if now and now.value_usd_thousands is not None
                        else None
                    ),
                    "value_usd_thousands_previous": (
                        float(before.value_usd_thousands)
                        if before and before.value_usd_thousands is not None
                        else None
                    ),
                }
            )

        return {
            "cik": cik,
            "manager": manager.name,
            "status": "ok",
            "latest_report": latest_date.isoformat(),
            "previous_report": previous_date.isoformat(),
            "compared_accessions": {
                "latest": latest_accession,
                "previous": previous_accession,
                "rule": "latest accession per period; amendments supersede base filings in this view, every filing stays stored immutably",
            },
            "changes": changes,
            "limitations": LIMITATIONS,
            "provenance": provenance(SOURCE, SourceKind.INTERNAL, coverage=Coverage.OK),
        }

    def latest_holdings(self, db: Session, *, cik: str) -> dict[str, Any]:
        cik = str(cik).strip().zfill(10)
        manager = db.scalar(select(FundManager).where(FundManager.cik == cik))
        if manager is None or manager.last_report_date is None:
            return {
                "cik": cik,
                "status": "unavailable",
                "holdings": [],
                "provenance": provenance(SOURCE, SourceKind.OFFICIAL, coverage=Coverage.UNAVAILABLE),
            }
        rows = db.scalars(
            select(ManagerHolding)
            .where(
                ManagerHolding.manager_id == manager.id,
                ManagerHolding.report_date == manager.last_report_date,
            )
            .order_by(ManagerHolding.value_usd_thousands.desc().nulls_last())
        ).all()
        return {
            "cik": cik,
            "manager": manager.name,
            "status": "ok",
            "report_date": manager.last_report_date.isoformat(),
            "coverage": manager.coverage,
            "holdings": [
                {
                    "accession_number": row.accession_number,
                    "is_amendment": row.is_amendment,
                    "name_of_issuer": row.name_of_issuer,
                    "title_of_class": row.title_of_class,
                    "cusip": row.cusip,
                    "value_usd_thousands": (
                        float(row.value_usd_thousands)
                        if row.value_usd_thousands is not None
                        else None
                    ),
                    "shares": float(row.shares) if row.shares is not None else None,
                    "share_type": row.share_type,
                    "put_call": row.put_call or None,
                    "investment_discretion": row.investment_discretion,
                    "filing_url": row.filing_url,
                }
                for row in rows
            ],
            "limitations": LIMITATIONS,
            "provenance": provenance(
                SOURCE,
                SourceKind.OFFICIAL,
                fetched_at=manager.synced_at,
                coverage=Coverage(manager.coverage),
            ),
        }
