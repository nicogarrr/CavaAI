"""Conector Form 13F (institutional holdings) sobre SEC EDGAR. Gratis, sin API key.

- submissions JSON de data.sec.gov para listar 13F-HR / 13F-HR/A por CIK de manager.
- index.json del filing para localizar el information table XML.
- parse tolerante del XML con xml.etree (local-name; campos ausentes -> None).
- rate-limit SEC: 10 req/s + User-Agent de contacto (mismo contrato que form4).
  El throttle y el estado NO se redefinen aqui: se importan de ``form4`` /
  ``connectors/base.py`` porque la SEC limita por IP/proceso. Con un reloj
  propio, un fetch 13F y un Form 4 seguidos creerian ambos que ha pasado su
  intervalo y disparar a la vez -> 403 de la SEC en los dos.
- Enmiendas (13F-HR/A): accession propio e inmutable; nunca se reescribe un
  filing previo.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

import httpx

# Unica definicion de la URL de submissions (la de form4) y UN unico estado de
# throttle, el de connectors/base.py.
from app.services.connectors.base import SEC_MIN_INTERVAL_SECONDS, sec_throttle
from app.services.connectors.form4 import SUBMISSIONS_URL, default_headers, filing_index_url

MIN_INTERVAL_SECONDS = SEC_MIN_INTERVAL_SECONDS
FORMS = {"13F-HR", "13F-HR/A"}

# Alias directo al throttle compartido (ver form4._throttle).
_throttle = sec_throttle


def _get(url: str, client: httpx.Client | None) -> httpx.Response:
    # Cabeceras antes del throttle (ver form4.recent_form4_filings): el sello
    # del intervalo debe fijarse lo mas pegado posible a la salida a la red.
    headers = default_headers()
    _throttle()
    if client is not None:
        response = client.get(url, headers=headers)
    else:
        with httpx.Client(timeout=30, headers=headers) as owned:
            response = owned.get(url)
    response.raise_for_status()
    return response


def recent_13f_filings(
    cik: str | int,
    *,
    limit: int = 8,
    client: httpx.Client | None = None,
) -> list[dict]:
    """13F-HR y 13F-HR/A recientes del manager, mas reciente primero."""
    url = SUBMISSIONS_URL.format(cik=str(cik).strip().zfill(10))
    payload = _get(url, client).json()
    recent = (payload.get("filings") or {}).get("recent") or {}
    accessions = recent.get("accessionNumber", []) or []
    items: list[dict] = []

    def _col(name: str, index: int):
        values = recent.get(name, []) or []
        return values[index] if index < len(values) else None

    for index, accession in enumerate(accessions):
        form = str(_col("form", index) or "").strip().upper()
        if form not in FORMS:
            continue
        items.append(
            {
                "accession_number": accession,
                "form": form,
                "is_amendment": form.endswith("/A"),
                "report_date": _col("reportDate", index),
                "filing_date": _col("filingDate", index),
                "primary_document": _col("primaryDocument", index),
            }
        )
        if len(items) >= limit:
            break
    return items


def information_table_url(
    cik: str | int,
    accession_number: str,
    primary_document: str | None,
    *,
    client: httpx.Client | None = None,
) -> str | None:
    """URL del information table XML dentro del filing; None si no se localiza."""
    base = filing_index_url(cik, accession_number)
    payload = _get(f"{base}index.json", client).json()
    items = (payload.get("directory") or {}).get("item") or []
    candidates: list[str] = []
    for item in items:
        name = str(item.get("name") or "")
        if not name.lower().endswith(".xml"):
            continue
        if primary_document and name == primary_document:
            continue
        candidates.append(name)
    if not candidates:
        return None
    preferred = [n for n in candidates if "infotable" in n.lower() or "13f" in n.lower()]
    return base + (preferred[0] if preferred else candidates[0])


def fetch_information_table(url: str, *, client: httpx.Client | None = None) -> list[dict]:
    return parse_information_table(_get(url, client).text)


def parse_information_table(xml_text: str) -> list[dict]:
    """Filas del information table; local-name, tolerante a campos ausentes."""

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def find_text(elem, name: str) -> str | None:
        for child in elem.iter():
            if local(child.tag) == name:
                return (child.text or "").strip() or None
        return None

    root = ET.fromstring(xml_text)
    rows: list[dict] = []
    for info in root.iter():
        if local(info.tag) != "infoTable":
            continue
        rows.append(
            {
                "name_of_issuer": find_text(info, "nameOfIssuer"),
                "title_of_class": find_text(info, "titleOfClass"),
                "cusip": find_text(info, "cusip"),
                "value_usd_thousands": find_text(info, "value"),
                "ssh_prnamt": find_text(info, "sshPrnamt"),
                "ssh_prnamt_type": find_text(info, "sshPrnamtType"),
                "put_call": find_text(info, "putCall"),
                "investment_discretion": find_text(info, "investmentDiscretion"),
                "voting_sole": find_text(info, "Sole"),
                "voting_shared": find_text(info, "Shared"),
                "voting_none": find_text(info, "None"),
            }
        )
    return rows
