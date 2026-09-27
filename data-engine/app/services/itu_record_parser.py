"""Fail-closed field extraction for an actual ITU as-received detail page.

Read server-rendered data-fieldname/data-value, not empty Knockout inputs.
A frequency table is a separate response; never infer it from page furniture.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import parse_qs, urlsplit

from lxml import html

from app.services.document_ingestion_service import ParsedBlock, ParsedDocument

DETAIL_PREFIX = "/ITU-R/space/asreceived/Publication/DisplayPublication/"
FREQ_PATH = "/ITU-R/space/asreceived/Publication/FrequenciesTable"
FIELDS = {
    "SnsNtcId": "Notice ID", "SatName": "Satellite Name",
    "InternalReference": "Submission Reference Number", "ActCode": "Act. Code",
    "TypeOfSubmission": "Type of Submission", "Provision": "Provision",
    "TargetNoticeId": "Target Notice ID", "NonGeoData": "Orbital Position",
    "nbr_plane": "Number of Planes", "BRRegistryDate": "BR registry date",
    "DateOfReceive": "Date of Receipt", "NumberOfSatellites": "Total number of satellites",
}


@dataclass(frozen=True)
class ITURecord:
    submission_id: str
    reference: str
    fields: dict[str, str]
    blocks: list[ParsedBlock]
    registry_date: date | None
    receipt_date: date | None
    frequency_url: str | None
    frequencies_complete: bool


def _submission_id(url: str) -> str:
    path = urlsplit(url).path
    candidate = path.removeprefix(DETAIL_PREFIX) if path.startswith(DETAIL_PREFIX) else ""
    if not re.fullmatch(r"[0-9]{1,12}", candidate):
        raise ValueError("Not an ITU publication detail URL")
    return candidate


def _date(value: str | None) -> date | None:
    if not value or not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", value):
        return None
    try:
        day, month, year = map(int, value.split("."))
        return date(year, month, day)
    except ValueError:
        return None


def parse_itu_record(content: bytes, url: str, *, frequency_html: bytes | None = None) -> ITURecord:
    submission_id = _submission_id(url)
    if len(content) > 15 * 1024 * 1024:
        raise ValueError("ITU detail exceeds document byte cap")
    tree = html.fromstring(content)
    forms = tree.xpath("//form[@id and @action]")
    forms = [form for form in forms if form.get("action", "").rstrip("/").endswith(f"{DETAIL_PREFIX}{submission_id}")]
    if len(forms) != 1:
        raise ValueError("ITU detail form missing or ambiguous")
    form = forms[0]
    ids = form.xpath(".//input[@name='Item.SubmissionId']/@value")
    if not ids or any(item != submission_id for item in ids):
        raise ValueError("ITU submission ID mismatch")
    fields: dict[str, str] = {}
    blocks: list[ParsedBlock] = []
    for name, label in FIELDS.items():
        matches = form.xpath(f".//*[@data-fieldname='{name}']")
        if len(matches) != 1:
            continue
        node = matches[0]
        if node.get("data-submissionid") != submission_id:
            raise ValueError(f"ITU field {name} belongs to another submission")
        value = node.get("data-value", "").strip()
        labels = [" ".join(item.itertext()).strip() for item in node.xpath(".//label")]
        if not value or label not in labels or len(value) > 500:
            continue
        fields[name] = value
        blocks.append(ParsedBlock(text=f"{label}: {value}", metadata={
            "format": "itu_asreceived", "fieldname": name,
            "locator": f"form[Item.SubmissionId={submission_id}] [data-fieldname={name}]@data-value",
            "field_complete": True,
        }))
    reference = fields.get("InternalReference")
    if (not reference or not re.fullmatch(r"D\d{4}-\d{4,8}", reference)
            or not fields.get("SatName") or not fields.get("TypeOfSubmission")):
        raise ValueError("ITU identity fields not parsed")
    # The server-rendered frequency section is a placeholder. Only a linked,
    # separately fetched table with matching submission ID can supply rows.
    frequency_urls = form.xpath(".//*[@data-source-url]/@data-source-url")
    matching = [value for value in frequency_urls
                if urlsplit(value).path == FREQ_PATH and
                parse_qs(urlsplit(value).query).get("submissionId") == [submission_id]]
    frequency_url = matching[0] if len(matching) == 1 else None
    complete = False
    if frequency_html is not None:
        if frequency_url is None or len(frequency_html) > 1024 * 1024:
            raise ValueError("Unlinked or oversized ITU frequency fragment")
        fragment = html.fromstring(frequency_html)
        tables = fragment.xpath("//table[@id='freqs']")
        if len(tables) != 1:
            raise ValueError("ITU frequency table missing")
        table = tables[0]
        heading = [" ".join(th.itertext()).strip() for th in table.xpath("./thead/tr/th")]
        rows = table.xpath("./tbody/tr")
        declared = table.get("data-total-items")
        if heading != ["Freq From (MHz)", "Freq To (MHz)"] or not rows:
            raise ValueError("ITU frequency columns missing")
        for index, row in enumerate(rows, 1):
            cells = [" ".join(cell.itertext()).strip() for cell in row.xpath("./td")]
            if len(cells) != 2 or any(not re.fullmatch(r"\d+(?:\.\d+)?", cell) for cell in cells):
                raise ValueError("Malformed ITU frequency row")
            blocks.append(ParsedBlock(text=f"Freq From (MHz): {cells[0]}; Freq To (MHz): {cells[1]}",
                                      metadata={"format": "itu_asreceived", "row": index,
                                                "locator": f"table#freqs tbody tr:nth-child({index})",
                                                "field_complete": False}))
        complete = declared is not None and declared.isdigit() and int(declared) == len(rows)
    return ITURecord(submission_id=submission_id, reference=reference, fields=fields,
                     blocks=blocks, registry_date=_date(fields.get("BRRegistryDate")),
                     receipt_date=_date(fields.get("DateOfReceive")),
                     frequency_url=frequency_url, frequencies_complete=complete)


def as_parsed_document(record: ITURecord) -> ParsedDocument:
    return ParsedDocument(blocks=record.blocks, parser="itu_asreceived_fields")
