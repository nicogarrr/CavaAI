"""Read official ITU notices without inferring a company from a satellite name.

Discovery emits unassigned candidates. Only an independently verified identity
binding may turn one into a tenant's ticker alert. BR date != publication date.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from urllib.parse import quote, urljoin

from lxml import html

from app.services.primary_source_ingestion import _official
from app.services.public_fetch import fetch_public_url

LIST_URL = "https://www.itu.int/ITU-R/space/asreceived/Publication/AsReceived"
DETAIL_PATH = "/ITU-R/space/asreceived/Publication/DisplayPublication/"
TABLE_URL = "https://www.itu.int/ITU-R/space/asreceived/Publication/GetPublicationTable"
COLUMNS = ["Reference", "NTC ID", "Adm.", "Network Org.", "Station/Satellite Name",
           "Long. Nom.", "BR Registry Date", "Type of submission", "Reg", "Act. Code"]


@dataclass(frozen=True)
class ITUCandidate:
    submission_id: str
    reference: str
    notice_id: str
    satellite_name: str
    br_registry_date: str
    type_of_submission: str
    act_code: str
    detail_url: str
    listing_url: str = LIST_URL
    ticker: None = None
    date_source: str = "br_registry_date_not_publication"


def _parse_page(raw: bytes, *, skip: int, take: int = 30) -> tuple[list[ITUCandidate], int]:
    if len(raw) > 1024 * 1024 or skip < 0 or take != 30:
        raise ValueError("ITU listing exceeds bounded parser limits")
    tree = html.fromstring(raw)
    tables = tree.xpath("//table[@id='publication-table']")
    if len(tables) != 1:
        raise ValueError("ITU listing table unavailable")
    table = tables[0]
    headings = [" ".join(th.itertext()).strip() for th in table.xpath("./thead/tr/th")]
    if headings != COLUMNS:
        raise ValueError("ITU listing headings changed")
    try:
        paging = json.loads(table.get("data-paging") or "")
        total = int(table.get("data-total-items") or "")
    except (ValueError, TypeError):
        raise ValueError("ITU listing pagination missing") from None
    if paging != {"Skip": skip, "Take": take} or total < skip or total > 100_000:
        raise ValueError("ITU listing pagination does not match request")
    rows = table.xpath("./tbody/tr")
    if (not rows and skip < total) or len(rows) != min(take, max(0, total - skip)):
        raise ValueError("ITU listing page row count unexpected")
    candidates = []
    seen = set()
    for row in rows:
        sid = row.get("data-submission-id") or ""
        cells = [" ".join(cell.itertext()).strip() for cell in row.xpath("./td")]
        if len(cells) != len(COLUMNS) or not re.fullmatch(r"\d{1,12}", sid):
            raise ValueError("Malformed ITU listing row")
        reference, notice, _, _, satellite, _, registry, submission, _, act = cells
        if (not re.fullmatch(r"[A-Z]{1,5}\d{4}-\d{4,8}", reference)
                or not satellite or not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", registry)
                or not notice.isdigit() or sid in seen):
            raise ValueError("ITU listing row identity unavailable")
        seen.add(sid)
        candidates.append(ITUCandidate(
            submission_id=sid, reference=reference, notice_id=notice,
            satellite_name=satellite, br_registry_date=registry,
            type_of_submission=submission, act_code=act,
            detail_url=urljoin(LIST_URL, f"{DETAIL_PATH}{sid}"),
        ))
    return candidates, total


def parse_listing(raw: bytes, *, max_rows: int = 30) -> list[ITUCandidate]:
    if not 1 <= max_rows <= 30:
        raise ValueError("Initial ITU page limit must be between 1 and 30")
    candidates, _ = _parse_page(raw, skip=0)
    return candidates[:max_rows]


def _page_url(skip: int) -> str:
    # Confirmed against the site's table.component.js: `publication-table.p`
    # carries base64(JSON{Skip,Take}). Plain Skip/Take query keys are ignored.
    payload = base64.b64encode(json.dumps({"Skip": skip, "Take": 30},
                                          separators=(",", ":")).encode()).decode()
    return f"{TABLE_URL}?publication-table.p={quote(payload, safe='')}"


def discover_itu_notices(*, max_pages: int = 20) -> tuple[list[ITUCandidate], dict]:
    """Traverse the bounded current listing; report partial coverage honestly."""
    if not 1 <= max_pages <= 20:
        raise ValueError("ITU scan allows 1-20 pages")
    raw, mime, final_url = fetch_public_url(LIST_URL, max_bytes=1024 * 1024,
                                             timeout=20, allowed_url=_official)
    if final_url != LIST_URL or (mime or "").split(";", 1)[0].lower() != "text/html":
        raise ValueError("Unexpected ITU listing response")
    first, initial_total = _parse_page(raw, skip=0)
    candidates = list(first)
    seen = {item.submission_id for item in first}
    pages = 1
    for skip in range(30, initial_total, 30):
        if pages >= max_pages:
            break
        url = _page_url(skip)
        page, page_mime, page_url = fetch_public_url(url, max_bytes=1024 * 1024,
                                                     timeout=20, allowed_url=_official)
        if (page_url != url or (page_mime or "").split(";", 1)[0].lower() != "text/html"):
            raise ValueError("Unexpected ITU page response")
        rows, page_total = _parse_page(page, skip=skip)
        if page_total != initial_total or any(item.submission_id in seen for item in rows):
            raise ValueError("ITU listing changed during pagination; retry next cycle")
        seen.update(item.submission_id for item in rows)
        candidates.extend(rows)
        pages += 1
    coverage = {"seen": len(candidates), "reported_total": initial_total,
                "pages": pages, "complete": len(candidates) == initial_total}
    return candidates, coverage


def persist_unassigned_notices(db, candidates: list[ITUCandidate], *, observed_at=None) -> dict:
    """Store only registry identity, not ticker/NewsEvent/ResearchAlert."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.models import ITUNotice

    tenant_id = db.info.get("tenant_id")
    if tenant_id is None:
        raise ValueError("Tenant context required")
    observed_at = observed_at or datetime.now(UTC)
    if observed_at.tzinfo is None or len(candidates) > 600:
        raise ValueError("Aware first-seen time and bounded candidate set required")
    created = 0
    seen_batch: set[str] = set()
    for item in candidates:
        if (item.ticker is not None or item.listing_url != LIST_URL or
                not item.detail_url.startswith(f"https://www.itu.int{DETAIL_PATH}") or
                item.detail_url != f"https://www.itu.int{DETAIL_PATH}{item.submission_id}" or
                item.date_source != "br_registry_date_not_publication" or
                item.submission_id in seen_batch):
            raise ValueError("ITU candidate identity or provenance invalid")
        seen_batch.add(item.submission_id)
        existing = db.scalar(select(ITUNotice).where(
            ITUNotice.tenant_id == tenant_id, ITUNotice.submission_id == item.submission_id))
        if existing is None:
            db.add(ITUNotice(tenant_id=tenant_id, submission_id=item.submission_id,
                             reference=item.reference, notice_id=item.notice_id,
                             satellite_name=item.satellite_name,
                             br_registry_date=item.br_registry_date,
                             submission_type=item.type_of_submission,
                             act_code=item.act_code, detail_url=item.detail_url,
                             first_seen_at=observed_at, last_seen_at=observed_at,
                             metadata_={"listing_url": item.listing_url,
                                        "date_source": item.date_source,
                                        "identity_status": "unassigned"}))
            created += 1
        else:
            if existing.reference != item.reference or existing.notice_id != item.notice_id or existing.detail_url != item.detail_url:
                raise ValueError("ITU submission identity drift requires review")
            existing.last_seen_at = observed_at
    db.commit()
    return {"received": len(candidates), "created": created,
            "unassigned": len(candidates), "company_alerts": 0}
